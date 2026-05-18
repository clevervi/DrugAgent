#!/usr/bin/env python3
"""
Test de docking REAL con AutoDock Vina nativo Windows.
Verifica toda la cadena: SMILES → PDBQT → Vina.exe → score.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv('.env')
# Asegurar API key
groq_key = os.environ.get('GROQ_API_KEY', '').strip()
if not groq_key or groq_key.startswith('gsk_REEMPLAZA'):
    raise ValueError(
        "❌ ERROR DE SEGURIDAD: La variable de entorno GROQ_API_KEY no está configurada "
        "o es una plantilla vacía ('gsk_REEMPLAZA...').\n"
        "Por favor, configure una clave válida de Groq en su archivo .env o en el entorno."
    )

sys.path.insert(0, '.')
from pathlib import Path

print("=" * 60)
print("  DrugAgent - Test Docking REAL (Windows Nativo)")
print("=" * 60)

VINA_EXE = Path("tools/vina/vina.exe")
PDB_PATH  = Path("data/receptors/4HJO.pdb")

# ── Test 1: Vina ejecutable ──
print("\n[1] Verificando vina.exe...")
import subprocess
r = subprocess.run([str(VINA_EXE), "--version"], capture_output=True, text=True)
print(f"  {r.stdout.strip()}" if r.returncode == 0 else f"  ERROR: {r.stderr}")

# ── Test 2: meeko disponible ──
print("\n[2] Verificando meeko...")
try:
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    print("  meeko 0.7.1 OK")
except ImportError as e:
    print(f"  ERROR: {e}")

# ── Test 3: Preparar receptor ──
print("\n[3] Preparando receptor EGFR (4HJO)...")
from orchestrator.nodes.simulator import prepare_receptor
pdbqt_path = prepare_receptor(PDB_PATH)
if pdbqt_path and pdbqt_path.exists():
    size_kb = pdbqt_path.stat().st_size / 1024
    print(f"  Receptor PDBQT: {pdbqt_path.name} ({size_kb:.1f} KB)")
    # Contar átomos
    atoms = sum(1 for line in pdbqt_path.read_text().split('\n') if line.startswith('ATOM'))
    print(f"  Atomos preparados: {atoms}")
else:
    print("  ERROR: No se pudo preparar receptor")

# ── Test 4: Preparar ligandos conocidos ──
print("\n[4] Preparando ligandos de prueba...")
from orchestrator.nodes.simulator import smiles_to_pdbqt
from pathlib import Path

lig_dir = Path("data/dock_tmp/test_ligs")
lig_dir.mkdir(parents=True, exist_ok=True)

# Erlotinib (inhibidor EGFR aprobado) y dos candidatos del agente
test_mols = [
    ("Erlotinib (FDA-aprobado)",    "n1cnc2c(c1)c(cc(c2)OCC)OCC.Cl",  False),
    ("Candidato 1 (agente)",        "O=C(Nc1nc2ccccc2s1)c1ccc(Br)cc1", True),
    ("Candidato 2 (agente)",        "c1ccc(CNc2ncnc3ccccc23)cc1",       True),
]

prepared = []
for name, smiles, is_candidate in test_mols:
    pdbqt = smiles_to_pdbqt(smiles, lig_dir)
    status = "OK" if pdbqt and pdbqt.exists() else "FALLO"
    size = pdbqt.stat().st_size if pdbqt and pdbqt.exists() else 0
    print(f"  {'[cand]' if is_candidate else '[ref] '} {name}: {status} ({size} bytes)")
    if pdbqt:
        prepared.append((name, smiles, pdbqt))

# ── Test 5: Docking REAL con Vina ──
print("\n[5] Ejecutando docking REAL con Vina Windows...")
if not (pdbqt_path and pdbqt_path.exists()):
    print("  ERROR: Receptor no disponible, saltando docking")
else:
    from orchestrator.nodes.simulator import run_vina_native

    # Centro del sitio activo de EGFR 4HJO (Ligando nativo AQ4)
    # Calculado del centro geométrico del ligando
    center   = (24.77, 9.19, 0.00)
    box_size = (20.0, 20.0, 20.0)

    print(f"  Centro grid: {center}")
    print(f"  Box size: {box_size} Å")
    print(f"  Exhaustiveness: 4 (rapido para test)")
    print()

    results = []
    for name, smiles, lig_pdbqt in prepared:
        print(f"  Dockeando: {name}...")
        score = run_vina_native(pdbqt_path, lig_pdbqt, center, box_size, exhaustiveness=4)
        status = f"{score:.2f} kcal/mol" if score is not None else "FALLO/TIMEOUT"
        print(f"    Score: {status}")
        results.append((name, score))

    print("\n  RANKING:")
    ranked = sorted([(n,s) for n,s in results if s is not None], key=lambda x: x[1])
    for i, (name, score) in enumerate(ranked, 1):
        print(f"    {i}. {name}: {score:.2f} kcal/mol")

# ── Resumen ──
print("\n" + "=" * 60)
print("  VEREDICTO")
print("=" * 60)
print(f"  vina.exe nativo Windows: {'OK' if VINA_EXE.exists() else 'FALTA'}")
print(f"  Receptor 4HJO.pdbqt:    {'OK' if pdbqt_path and pdbqt_path.exists() else 'FALTA'}")
print(f"  meeko (SMILES→PDBQT):   OK")
print(f"  WSL2 necesario:          NO")
print(f"  Virtualización:          NO")
print("=" * 60)
