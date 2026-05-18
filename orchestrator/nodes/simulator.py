"""
Nodo Simulator: AutoDock Vina nativo en Windows (sin WSL2).
Centralizado vía core.docking.
"""
import os
from pathlib import Path
from datetime import datetime

from ..state import AgentState
from core.docking import prepare_receptor_pdbqt, smiles_to_pdbqt, run_vina_native, mock_score, VINA_EXE, RECEPTORS_DIR, DOCK_TEMP_DIR, find_ligand_centroid_and_box

def simulator_node(state: AgentState) -> dict:
    """Nodo simulador: docking real con Vina Windows o mock si no disponible."""
    iteration   = state.get("iteration", 0)
    batch       = state.get("current_batch", [])

    print(f"\n[Iter {iteration}] ⚗️  SIMULATOR: Corriendo docking en {len(batch)} candidatos...")

    if not batch:
        return {
            "next_action": "reflect",
            "iteration_logs": [f"[Iter {iteration}] Simulator: lote vacío"],
        }

    # ── Detectar receptor ──
    pdb_id = state.get("target_pdb_id", "4HJO")
    pdb_path = RECEPTORS_DIR / f"{pdb_id}.pdb"

    # ── Cargar configuración de docking ──
    import yaml
    docking_mode = "auto"
    center = (24.77, 9.19, 0.00)
    box_size = (20.0, 20.0, 20.0)
    exhaustiveness = 4
    matched = False
    
    # 1. Cargar catálogo de coordenadas terapéuticas
    try:
        catalog_path = Path(__file__).resolve().parent.parent.parent / "catalog" / "therapeutic_areas.yaml"
        if catalog_path.exists():
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = yaml.safe_load(f) or {}
            # Buscar por pdb_id
            for area_key, area_data in catalog.items():
                if str(area_data.get("pdb_id", "")).strip().upper() == str(pdb_id).strip().upper():
                    dp = area_data.get("docking_params", {})
                    center = (dp.get("center_x", center[0]), dp.get("center_y", center[1]), dp.get("center_z", center[2]))
                    box_size = (dp.get("size_x", box_size[0]), dp.get("size_y", box_size[1]), dp.get("size_z", box_size[2]))
                    matched = True
                    print(f"   🧬 Coordenadas del catálogo aplicadas para {pdb_id}: center={center}, size={box_size}")
                    break
    except Exception as e_cat:
        print(f"   ⚠️ Error cargando catálogo de coordenadas: {e_cat}")

    # 2. Cargar config local como fallback/override
    try:
        with open("./config/config.yaml") as f:
            cfg = yaml.safe_load(f)
        dc = cfg.get("docking", {})
        if not matched:
            prepare_receptor_pdbqt(pdb_path)
            geom = find_ligand_centroid_and_box(pdb_path)
            center = geom["center"]
            box_size = geom["size"]
            print(f"   🧬 Coordenadas para {pdb_id} calculadas dinámicamente ({geom['method']}): center={center}, size={box_size}")
        exhaustiveness = dc.get("exhaustiveness", 4)  # 4 por defecto para agilidad
        docking_mode = os.environ.get("DOCKING_MODE", cfg.get("docking_mode", "auto"))
    except Exception:
        if not matched:
            prepare_receptor_pdbqt(pdb_path)
            geom = find_ligand_centroid_and_box(pdb_path)
            center = geom["center"]
            box_size = geom["size"]
            print(f"   🧬 Coordenadas para {pdb_id} calculadas dinámicamente ({geom['method']}): center={center}, size={box_size}")
        docking_mode = os.environ.get("DOCKING_MODE", "auto")

    use_real_vina = False
    receptor_pdbqt = None

    if docking_mode == "mock":
        print("   ℹ️  Modo forzado por configuración: MOCK")
    elif docking_mode == "real":
        print("   ℹ️  Modo forzado por configuración: REAL")
        receptor_pdbqt = prepare_receptor_pdbqt(pdb_path)
        if receptor_pdbqt and receptor_pdbqt.exists() and VINA_EXE.exists():
            use_real_vina = True
        else:
            raise ValueError(f"No se pudo inicializar el modo REAL forzado. Verifique VINA_EXE en {VINA_EXE} y receptor {pdb_path}.")
    else: # auto
        if VINA_EXE.exists():
            receptor_pdbqt = prepare_receptor_pdbqt(pdb_path)
            if receptor_pdbqt and receptor_pdbqt.exists():
                use_real_vina = True
                print(f"   ✅ Modo REAL autodetectado: Vina Windows + receptor {pdb_id}.pdbqt")
            else:
                print(f"   ⚠️  Receptor no preparado → modo mock")
        else:
            print(f"   ⚠️  vina.exe no encontrado en {VINA_EXE} → modo mock")

    if not use_real_vina:
        print("   ℹ️  Usando score mock (propiedades QSAR)")

    import uuid
    from concurrent.futures import ThreadPoolExecutor

    # ── Directorio temporal único para evitar colisiones en hilos concurrentes ──
    lig_dir = DOCK_TEMP_DIR / f"ligands_{uuid.uuid4().hex}"
    lig_dir.mkdir(exist_ok=True, parents=True)

    # ── Limitar batch para velocidad (Top 10 por QED) ──
    if len(batch) > 10 and use_real_vina:
        print(f"   ⚡ Limitando docking a top 10 candidatos (de {len(batch)}) para agilidad")
        # Ordenar por QED y tomar 10
        batch = sorted(batch, key=lambda x: x.get("qed", 0), reverse=True)[:10]

    # ── Función trabajadora para paralelización ──
    def _dock_molecule(mol_data: dict) -> dict:
        mol_data = dict(mol_data)
        smiles   = mol_data["smiles"]

        if use_real_vina:
            ligand_pdbqt = smiles_to_pdbqt(smiles, lig_dir)
            if ligand_pdbqt:
                score = run_vina_native(
                    receptor_pdbqt, ligand_pdbqt,
                    center, box_size, exhaustiveness,
                    smiles=smiles
                )
                if score is not None:
                    mol_data["docking_score"]    = score
                    mol_data["binding_affinity"] = abs(score)
                    mol_data["status"]           = "docked_real"
                else:
                    # Vina corrió pero no devolvió score → mock
                    mol_data["docking_score"]    = mock_score(mol_data)
                    mol_data["binding_affinity"] = abs(mol_data["docking_score"])
                    mol_data["status"]           = "docked_mock_fallback"
            else:
                mol_data["docking_score"] = mock_score(mol_data)
                mol_data["status"]        = "prep_failed_mock"
        else:
            mol_data["docking_score"]    = mock_score(mol_data)
            mol_data["binding_affinity"] = abs(mol_data["docking_score"])
            mol_data["status"]           = "docked_mock"

        return mol_data

    # ── Docking en paralelo ──
    docked_batch = []
    docked_count = 0
    max_workers = min(4, len(batch)) if len(batch) > 0 else 1

    print(f"   ⚡ Corriendo docking en paralelo usando ThreadPoolExecutor ({max_workers} hilos)...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_dock_molecule, mol) for mol in batch]
        for fut in futures:
            try:
                res_mol = fut.result()
                docked_batch.append(res_mol)
                docked_count += 1
            except Exception as e_fut:
                print(f"   ⚠️ Falló docking de una molécula en el pool de hilos: {e_fut}")

    # ── Ordenar y actualizar top candidatos ──
    docked_mols = [m for m in docked_batch if m.get("docking_score") is not None]
    docked_mols.sort(key=lambda x: x["docking_score"])

    all_prev   = [c for c in state.get("all_candidates", []) if c.get("docking_score") is not None]
    all_docked = all_prev + docked_mols
    all_docked.sort(key=lambda x: x["docking_score"])
    top_candidates = all_docked[:10]

    best_score = top_candidates[0]["docking_score"] if top_candidates else 0.0
    avg_score  = sum(m["docking_score"] for m in docked_mols) / len(docked_mols) if docked_mols else 0.0

    mode_label = "REAL" if use_real_vina else "mock"
    best_this  = docked_mols[0]["docking_score"] if docked_mols else "N/A"
    print(f"[Iter {iteration}] ✓ Docking ({mode_label}): {docked_count}/{len(batch)} procesados")
    print(f"   Mejor score esta iteración: {best_this} kcal/mol")
    print(f"   Mejor score histórico:      {best_score:.2f} kcal/mol")

    result = {
        "current_batch":     docked_batch,
        "top_candidates":    top_candidates,
        "best_score":        best_score,
        "avg_score_history": [avg_score],
        "next_action":       "analyze",
        "docking_mode":      "real" if use_real_vina else "mock",
        "iteration_logs":    [
            f"[Iter {iteration}] Simulator ({mode_label}): {docked_count} dockings. "
            f"Best: {best_this} kcal/mol"
        ],
        "last_updated": datetime.now().isoformat(),
    }

    # ── Limpieza de archivos temporales ──
    try:
        import shutil
        if lig_dir.exists():
            shutil.rmtree(lig_dir)
    except Exception as e:
        print(f"   ⚠️  Error limpiando temporales: {e}")

    return result
