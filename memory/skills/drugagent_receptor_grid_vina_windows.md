# Skill: Receptor, grid y Vina en DrugAgent (Windows)

## Objetivo
Alinear preparación de receptor, caja de docking y ejecución con el **código real** del proyecto (`core/docking.py`, `orchestrator/nodes/simulator.py`), no con tutoriales genéricos de Linux.

## Fuente de verdad para la caja
1. **`catalog/therapeutic_areas.yaml`**: si existe una entrada cuyo `pdb_id` coincide con la misión, sus `docking_params` (center_x/y/z, size_x/y/z) tienen **prioridad conceptual** sobre el bloque genérico de `config/config.yaml`.
2. **`config/config.yaml`**: bloque `docking:` como respaldo o cuando el PDB no está en el catálogo.
3. **Fallback dinámico**: si no hay match en catálogo, el simulador puede estimar centro/tamaño desde HETATM del PDB (`find_ligand_centroid_and_box`).

## Rutas y binarios (Windows)
- Receptores: `data/receptors/{PDB_ID}.pdb` y receptor preparado `.pdbqt` en el mismo árbol según `core/docking.py`.
- Vina: `tools/vina/vina.exe` (variable interna `VINA_EXE`).
- Poses guardadas: `data/docked_poses/` (ligandos acoplados persistentes).

## Modos de docking (`DOCKING_MODE` / `docking_mode`)
- **`auto`**: usa Vina real si `vina.exe` existe y el receptor se prepara bien; si no, cae a score mock.
- **`real`**: exige Vina + receptor válido; falla explícito si no se puede (mejor que fingir ciencia).
- **`mock`**: score determinista/QSAR; útil para CI o máquinas sin Vina — **no comparar** numéricamente con corridas reales.

## Checklist antes de una misión nueva (nuevo PDB)
- [ ] PDB descargado en `data/receptors/`.
- [ ] Entrada en `therapeutic_areas.yaml` con `docking_params` revisados (PyMOL/ChimeraX: sitio activo vs todo el HETATM).
- [ ] Probar una corrida corta (`--iterations 1`) y revisar log: `REAL` vs `mock` y mensajes de preparación.

## Errores frecuentes
- Caja centrada en agua o en cofactor equivocado → scores engañosos.
- Mezclar coordenadas de un tutorial EGFR con otro PDB → siempre validar contra el YAML de esa misión.

## Qué no hace esta skill
No sustituye revisión cristalográfica ni elección de estado protonación; documenta el contrato del **pipeline actual** del repo.
