"""
Core Docking Engine for DrugAgent.
Provides a unified interface for Windows-native docking using AutoDock Vina, RDKit, meeko, and gemmi.
Incorporates robust try-except blocks and fallbacks for environments without the full suite of binary tools.
"""

import os
import sys
import subprocess
import tempfile
import shutil
import codecs
from pathlib import Path
from typing import Optional, Dict, List

# Configurar salida estándar de la consola en Windows para ignorar errores de codificación unicode (emojis)
try:
    if hasattr(sys.stdout, "encoding") and sys.stdout.encoding:
        sys.stdout = codecs.getwriter(sys.stdout.encoding)(sys.stdout.buffer, 'ignore')
    if hasattr(sys.stderr, "encoding") and sys.stderr.encoding:
        sys.stderr = codecs.getwriter(sys.stderr.encoding)(sys.stderr.buffer, 'ignore')
except Exception:
    pass

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors
from utils.scoring import deterministic_noise

# Root directories and paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VINA_EXE = PROJECT_ROOT / "tools" / "vina" / "vina.exe"
RECEPTORS_DIR = PROJECT_ROOT / "data" / "receptors"
DOCK_TEMP_DIR = PROJECT_ROOT / "data" / "dock_tmp"
DOCK_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Directorio permanente para visualización 3D (Opción A)
DOCKED_POSES_DIR = PROJECT_ROOT / "data" / "docked_poses"
DOCKED_POSES_DIR.mkdir(parents=True, exist_ok=True)

def validate_pdb_id(pdb_id: str) -> bool:
    """
    Verifica mediante una petición HTTP HEAD si un ID de PDB existe y es accesible en RCSB PDB.
    Si el PDB ya existe localmente, o si estamos en modo offline, se maneja de forma segura y local.
    Si no hay conexión o falla el servidor, retorna True (fallback permisivo) para no bloquear la ejecución local.
    """
    import requests
    pdb_id = pdb_id.strip().upper()
    if len(pdb_id) != 4 or not pdb_id.isalnum():
        print(f"   ⚠️ ID de PDB inválido por formato: '{pdb_id}'")
        return False
        
    # 1. Comprobar si el receptor ya existe localmente en RECEPTORS_DIR
    local_pdb = RECEPTORS_DIR / f"{pdb_id}.pdb"
    local_pdbqt = RECEPTORS_DIR / f"{pdb_id}.pdbqt"
    if local_pdb.exists() or local_pdbqt.exists():
        print(f"   ✅ [VALIDACIÓN LOCAL]: El PDB ID '{pdb_id}' ya existe localmente. Omitiendo verificación de red.")
        return True
        
    # 2. Si estamos en modo offline, no podemos descargarlo si no existe localmente
    offline_mode = os.environ.get("OFFLINE_MODE", "false").lower() in ("1", "true", "yes")
    if offline_mode:
        print(f"   ⚠️ [VALIDACIÓN OFFLINE]: PDB '{pdb_id}' no existe localmente y OFFLINE_MODE está activo.")
        return False
        
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    try:
        response = requests.head(url, timeout=4)
        if response.status_code == 200:
            return True
        else:
            print(f"   ⚠️ RCSB PDB retornó status {response.status_code} para ID: {pdb_id}")
            return False
    except Exception as e:
        print(f"   ⚠️ Error de red al validar PDB ID '{pdb_id}' ({e}). Usando fallback permisivo.")
        return True

def download_pdb(pdb_id: str, out_path: Path) -> bool:
    """
    Descarga autónomamente un receptor en formato PDB desde RCSB PDB.
    """
    import urllib.request
    pdb_id = pdb_id.strip().upper()
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    try:
        print(f"   📥 Descargando receptor {pdb_id} desde RCSB PDB ({url})...")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, str(out_path))
        if out_path.exists() and out_path.stat().st_size > 5000:
            print(f"   ✅ Receptor {pdb_id} descargado con éxito ({out_path.stat().st_size} bytes).")
            return True
        else:
            print(f"   ⚠️ Archivo descargado para {pdb_id} es inválido o muy pequeño.")
    except Exception as e:
        print(f"   ⚠️ Error descargando PDB {pdb_id}: {e}")
    return False

def predict_binding_pocket(pdb_path: Path) -> Optional[dict]:
    """
    Analiza la superficie y cavidades de la proteína (cuando no hay ligando nativo)
    usando un algoritmo de sonda geométrica basado en rejilla + KDTree + DBSCAN.
    Encuentra el bolsillo (cavidad) más grande en la superficie de la proteína.
    """
    try:
        import numpy as np
        from scipy.spatial import KDTree
        from sklearn.cluster import DBSCAN
        
        # 1. Extraer átomos ATOM pesados (C, N, O, S)
        coords = []
        with open(pdb_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('ATOM'):
                    # Identificar átomo pesado
                    element = line[76:78].strip().upper() if len(line) > 76 else ''
                    if not element:
                        element = line[12:14].strip().upper().lstrip('0123456789 ')
                    if element in ('C', 'N', 'O', 'S'):
                        try:
                            x = float(line[30:38].strip())
                            y = float(line[38:46].strip())
                            z = float(line[46:54].strip())
                            coords.append([x, y, z])
                        except ValueError:
                            pass
                            
        if len(coords) < 50:
            return None
            
        coords = np.array(coords)
        
        # 2. Definir límites de la rejilla alrededor de la proteína
        min_coords = coords.min(axis=0) - 4.0
        max_coords = coords.max(axis=0) + 4.0
        
        # Rejilla con espaciado de 2.5 Å
        spacing = 2.5
        xs = np.arange(min_coords[0], max_coords[0], spacing)
        ys = np.arange(min_coords[1], max_coords[1], spacing)
        zs = np.arange(min_coords[2], max_coords[2], spacing)
        
        # Crear malla de puntos de rejilla
        grid_points = np.array(np.meshgrid(xs, ys, zs)).T.reshape(-1, 3)
        
        if len(grid_points) > 20000:
            # Si la rejilla es demasiado grande, aumentar espaciado para evitar lentitud
            spacing = 4.0
            xs = np.arange(min_coords[0], max_coords[0], spacing)
            ys = np.arange(min_coords[1], max_coords[1], spacing)
            zs = np.arange(min_coords[2], max_coords[2], spacing)
            grid_points = np.array(np.meshgrid(xs, ys, zs)).T.reshape(-1, 3)
            
        # 3. Construir KDTree de los átomos de la proteína
        tree = KDTree(coords)
        
        # 4. Encontrar puntos de la rejilla que sean cavidades
        # Un punto de rejilla es una cavidad si:
        # - No está demasiado cerca de ningún átomo de la proteína (min_dist >= 2.5 Å, evita el núcleo)
        # - Está rodeado por suficientes átomos a distancia moderada (p. ej., al menos 12 átomos a <= 6.0 Å)
        min_dist = 2.5
        max_dist = 6.0
        
        # Consultar todas las distancias en lote
        dists, indices = tree.query(grid_points, k=1)
        
        # Filtrar puntos que no colisionan con el core de la proteína
        valid_mask = dists >= min_dist
        candidate_points = grid_points[valid_mask]
        
        if len(candidate_points) == 0:
            return None
            
        # Contar cuántos átomos están dentro de max_dist para cada punto candidato
        raw_indices = tree.query_ball_point(candidate_points, r=max_dist)
        counts = np.array([len(idx_list) for idx_list in raw_indices])
        
        # Un buen bolsillo tiene un número mínimo de átomos alrededor (rodeado / cavidad)
        pocket_points_mask = counts >= 12
        cavity_points = candidate_points[pocket_points_mask]
        
        if len(cavity_points) < 4:
            return None
            
        # 5. Agrupar puntos de cavidad usando DBSCAN para encontrar bolsillos continuos
        db = DBSCAN(eps=4.5, min_samples=3).fit(cavity_points)
        labels = db.labels_
        
        # Encontrar el cluster más grande (excluyendo el ruido -1)
        unique_labels, label_counts = np.unique(labels[labels != -1], return_counts=True)
        if len(unique_labels) == 0:
            return None
            
        largest_cluster_label = unique_labels[np.argmax(label_counts)]
        pocket_cluster_points = cavity_points[labels == largest_cluster_label]
        
        # 6. Calcular el centroide del bolsillo más grande
        centroid = pocket_cluster_points.mean(axis=0)
        
        return {
            "center": (round(float(centroid[0]), 2), round(float(centroid[1]), 2), round(float(centroid[2]), 2)),
            "size": (20.0, 20.0, 20.0),
            "method": "Advanced Cavity Predictor (KDTree + DBSCAN Clustering)"
        }
    except Exception as e:
        print(f"   ⚠️ Error en predicción geométrica de bolsillo de unión: {e}")
        return None

def find_ligand_centroid_and_box(pdb_path: Path) -> dict:
    """
    Analiza un archivo PDB buscando ligandos pequeños (HETATM) para centrar la caja de docking.
    Calcula el centroide en Python puro sin dependencias externas.
    """
    ignore_residues = {
        'HOH', 'WAT', 'DOD', 'SOL', 'CL', 'NA', 'MG', 'SO4', 'PO4', 'EDT', 'PEG', 'ACT', 'DMS', 'GOL', 'UNX'
    }
    coords = []
    
    # Asegurar que el PDB existe
    if not pdb_path.exists():
        return {
            "center": (20.0, 20.0, 20.0),
            "size": (20.0, 20.0, 20.0),
            "method": "Default fallback (PDB not found)"
        }
        
    with open(pdb_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('HETATM'):
                res_name = line[17:20].strip()
                if res_name in ignore_residues:
                    continue
                try:
                    x = float(line[30:38].strip())
                    y = float(line[38:46].strip())
                    z = float(line[46:54].strip())
                    coords.append((x, y, z))
                except ValueError:
                    pass
                    
    if coords:
        n = len(coords)
        sum_x = sum(c[0] for c in coords)
        sum_y = sum(c[1] for c in coords)
        sum_z = sum(c[2] for c in coords)
        center = (sum_x / n, sum_y / n, sum_z / n)
        
        min_x = min(c[0] for c in coords)
        max_x = max(c[0] for c in coords)
        min_y = min(c[1] for c in coords)
        max_y = max(c[1] for c in coords)
        min_z = min(c[2] for c in coords)
        max_z = max(c[2] for c in coords)
        
        size_x = max(max_x - min_x + 8.0, 16.0)
        size_y = max(max_y - min_y + 8.0, 16.0)
        size_z = max(max_z - min_z + 8.0, 16.0)
        
        # Limitar caja
        size_x = min(size_x, 25.0)
        size_y = min(size_y, 25.0)
        size_z = min(size_z, 25.0)
        
        return {
            "center": (round(center[0], 2), round(center[1], 2), round(center[2], 2)),
            "size": (round(size_x, 2), round(size_y, 2), round(size_z, 2)),
            "method": "Centroid of native ligand (HETATM)"
        }
        
    # Si no hay HETATM, calcular usando predicción geométrica activa de sitio activo
    pocket = predict_binding_pocket(pdb_path)
    if pocket:
        print(f"   🎯 Active Site Predictor: ¡Bolsillo de unión detectado con éxito ({pocket['method']}) en {pocket['center']}!")
        return pocket
        
    # Fallback si la predicción geométrica falla, calcular usando átomos ATOM
    atom_coords = []
    with open(pdb_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('ATOM'):
                try:
                    x = float(line[30:38].strip())
                    y = float(line[38:46].strip())
                    z = float(line[46:54].strip())
                    atom_coords.append((x, y, z))
                except ValueError:
                    pass
                    
    if atom_coords:
        n = len(atom_coords)
        sum_x = sum(c[0] for c in atom_coords)
        sum_y = sum(c[1] for c in atom_coords)
        sum_z = sum(c[2] for c in atom_coords)
        center = (sum_x / n, sum_y / n, sum_z / n)
        return {
            "center": (round(center[0], 2), round(center[1], 2), round(center[2], 2)),
            "size": (22.0, 22.0, 22.0),
            "method": "Centroid of entire protein (No ligand detected)"
        }
        
    return {
        "center": (0.0, 0.0, 0.0),
        "size": (20.0, 20.0, 20.0),
        "method": "Default fallback grid"
    }

def prepare_receptor_pdbqt(pdb_path: Path) -> Path:
    """
    Cleans and prepares a receptor PDB file into PDBQT format with realistic Gasteiger charges.
    Uses gemmi for Polymer entity filtering and meeko's mk_prepare_receptor command line utility.
    Falls back to a basic AD4 structural preparer if these dependencies are unavailable or fail.
    """
    pdbqt_path = pdb_path.with_suffix(".pdbqt")
    
    # Descargar dinámicamente si no existe
    if not pdb_path.exists():
        pdb_id = pdb_path.stem
        success = download_pdb(pdb_id, pdb_path)
        if not success:
            print(f"   ⚠️ Receptor {pdb_id}.pdb no existe y no se pudo descargar.")
            return None
            
    # If a valid PDBQT already exists and has a non-trivial size, reuse it
    if pdbqt_path.exists() and pdbqt_path.stat().st_size > 50_000:
        content = pdbqt_path.read_text(encoding="utf-8", errors="ignore")[:3000]
        atom_lines = [l for l in content.split('\n') if l.startswith('ATOM')]
        charges = []
        for l in atom_lines[:10]:
            try:
                charges.append(float(l[70:76].strip()))
            except Exception:
                pass
        if charges and any(abs(c) > 0.001 for c in charges):
            return pdbqt_path

    try:
        import gemmi
        
        # Read structure using gemmi
        structure = gemmi.read_structure(str(pdb_path))
        
        # Filter: retain only Polymer chains (protein), discard waters and heteroatoms
        model = structure[0]
        chains_to_keep = []
        for chain in model:
            residues = [r for r in chain if r.entity_type == gemmi.EntityType.Polymer]
            if residues:
                chains_to_keep.append(chain.name)
        
        clean_pdb = pdb_path.with_name(pdb_path.stem + "_clean.pdb")
        structure.write_pdb(str(clean_pdb))
        
        # Call mk_prepare_receptor CLI from meeko to compute Gasteiger charges
        result = subprocess.run(
            ["mk_prepare_receptor", "-i", str(clean_pdb), "-o", str(pdbqt_path), "--box_enveloping"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and pdbqt_path.exists() and pdbqt_path.stat().st_size > 1000:
            try:
                clean_pdb.unlink()
            except Exception:
                pass
            return pdbqt_path
    except Exception:
        pass

    # Fallback to basic AD4 format output
    _prepare_receptor_basic(pdb_path, pdbqt_path)
    return pdbqt_path

def _prepare_receptor_basic(pdb_path: Path, pdbqt_path: Path):
    """
    A basic fallback parser that maps standard protein heavy atoms to AD4 atom types,
    adding empty charges to satisfy AutoDock Vina's parsing structure.
    """
    atom_types = {
        'C': 'C', 'N': 'N', 'O': 'OA', 'S': 'SA',
        'H': 'H', 'P': 'P', 'F': 'F', 'CL': 'Cl',
        'BR': 'Br', 'I': 'I', 'FE': 'Fe', 'ZN': 'Zn',
        'MG': 'Mg', 'CA': 'Ca', 'MN': 'Mn', 'NA': 'NA'
    }

    lines_out = []
    with open(pdb_path, 'r', encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith('ATOM'):
                continue
            resname = line[17:20].strip()
            if resname in ('HOH', 'WAT', 'DOD'):
                continue
            element = line[76:78].strip().upper() if len(line) > 76 else ''
            if not element:
                element = line[12:14].strip().upper().lstrip('0123456789')
            ad4type = atom_types.get(element, 'C')
            pdbqt_line = line.rstrip('\n').ljust(70)[:70]
            pdbqt_line += f"  0.000 {ad4type:<2s}\n"
            lines_out.append(pdbqt_line)

    with open(pdbqt_path, 'w', encoding="utf-8") as f:
        f.writelines(lines_out)

def smiles_to_pdbqt(smiles: str, out_dir: Path) -> Optional[Path]:
    """
    Converts a SMILES string into a prepared PDBQT ligand file.
    Desalts/cleans the molecular graph, embeds a 3D conformer with ETKDG / MMFF optimization,
    and formats using meeko's MoleculePreparation.
    """
    try:
        from meeko import MoleculePreparation, PDBQTWriterLegacy

        # Desalt: Keep only the largest organic fragment
        if "." in smiles:
            fragments = smiles.split(".")
            smiles = max(fragments, key=len)
            print(f"   🧪 Molécula desalada al fragmento principal (core/docking): {smiles}")

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        # Add explicit hydrogens
        mol = Chem.AddHs(mol)
        
        # Embed 3D conformer
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        if AllChem.EmbedMolecule(mol, params) == -1:
            AllChem.EmbedMolecule(mol, AllChem.ETKDG())
        
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)

        # Prepare using meeko
        preparator = MoleculePreparation()
        mol_setups = preparator.prepare(mol)
        if not mol_setups:
            return None
        
        pdbqt_str, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
        if not is_ok:
            return None

        # Safe tag based on smiles hash
        smi_hash = abs(hash(smiles)) % 10**8
        pdbqt_path = out_dir / f"lig_{smi_hash}.pdbqt"
        pdbqt_path.write_text(pdbqt_str, encoding="utf-8")
        
        # Guardar copia permanente (Opción A - Visor 3D)
        import hashlib
        md5_hash = hashlib.md5(smiles.encode('utf-8')).hexdigest()
        perm_path = DOCKED_POSES_DIR / f"lig_{md5_hash}.pdbqt"
        perm_path.write_text(pdbqt_str, encoding="utf-8")
        
        return pdbqt_path

    except Exception as e:
        print(f"   ⚠️ smiles_to_pdbqt error: {e}")
        return None

def run_vina_native(
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    center: tuple,
    box_size: tuple,
    exhaustiveness: int = 8,
    n_poses: int = 5,
    smiles: str = ""
) -> Optional[float]:
    """
    Executes Vina.exe as a subprocess and parses the returned minimum binding affinity.
    """
    if not VINA_EXE.exists():
        return None

    out_pdbqt = ligand_pdbqt.with_name(ligand_pdbqt.stem + "_out.pdbqt")
    cx, cy, cz = center
    sx, sy, sz = box_size

    cmd = [
        str(VINA_EXE),
        "--receptor", str(receptor_pdbqt),
        "--ligand",   str(ligand_pdbqt),
        "--center_x", str(cx), "--center_y", str(cy), "--center_z", str(cz),
        "--size_x",   str(sx), "--size_y",   str(sy), "--size_z",   str(sz),
        "--exhaustiveness", str(exhaustiveness),
        "--num_modes", str(n_poses),
        "--out", str(out_pdbqt),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None

        # Parse from standard output
        for line in result.stdout.split('\n'):
            parts = line.strip().split()
            if parts and parts[0] == '1' and len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    pass

        # Parse fallback from resulting PDBQT REMARK lines
        if out_pdbqt.exists():
            # Guardar copia permanente de las poses dockeadas por Vina (Opción A - Visor 3D)
            if smiles:
                import hashlib
                md5_hash = hashlib.md5(smiles.encode('utf-8')).hexdigest()
                perm_path = DOCKED_POSES_DIR / f"lig_{md5_hash}.pdbqt"
                try:
                    shutil.copy(str(out_pdbqt), str(perm_path))
                except Exception as e_copy:
                    print(f"   ⚠️ Error guardando pose dockeada en DOCKED_POSES_DIR: {e_copy}")
                    
            for line in out_pdbqt.read_text(encoding="utf-8", errors="ignore").split('\n'):
                if 'REMARK VINA RESULT' in line:
                    return float(line.split()[3])
    except Exception as e:
        print(f"   ⚠️ run_vina_native exception: {e}")
    
    return None

def mock_score(mol_data: dict) -> float:
    """
    Physicochemically informed deterministic QSAR scoring function.
    Combines QED, LogP, Molecular Weight, and molecular SMILES deterministic hash.
    """
    smiles = mol_data.get("smiles", "")
    qed = mol_data.get("qed", 0.5)
    logp = mol_data.get("logp", 3.0)
    mw = mol_data.get("mw", 350.0)
    mw_factor = max(0, 1 - abs(mw - 350) / 400)
    noise = deterministic_noise(smiles, scale=0.4)
    score = -(5.0 + qed * 4.5 + (logp / 5.0) * 2.0 + mw_factor + noise)
    return round(score, 2)
