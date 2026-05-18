# Skill: Preparación de receptor EGFR (4HJO) y caja de docking — alineado con DrugAgent

## Fuente de verdad (este repo)
Las coordenadas de la caja para la misión **EGFR / 4HJO** deben coincidir con **`catalog/therapeutic_areas.yaml`** (entrada `oncology_lung_egfr` → `docking_params`), que usa el simulador al hacer match por `pdb_id`.

### Parámetros actuales en catálogo (4HJO)
```
center_x = 21.0
center_y = 11.5
center_z = -0.5
size_x = size_y = size_z = 20.0
```

**Nota:** `config/config.yaml` puede tener otro bloque `docking:` como fallback cuando el PDB no está en el catálogo; para EGFR en misiones del menú/catálogo, prima el YAML terapéutico.

## Preparación en Windows (este proyecto)
- Receptor PDB: `data/receptors/4HJO.pdb` (u otro `data/receptors/{PDB}.pdb`).
- La preparación **PDBQT** y el flujo Vina están centralizados en **`core/docking.py`** (Meeko / herramientas locales); no hace falta ADFRsuite para el camino feliz del agente.
- Ejecutable Vina: `tools/vina/vina.exe`.

### Descargar PDB (PowerShell)
```powershell
Invoke-WebRequest -Uri "https://files.rcsb.org/download/4HJO.pdb" -OutFile "data/receptors/4HJO.pdb"
```

### Limpieza mínima (opcional, manual)
Si necesitas un PDB solo proteína para inspección, puedes filtrar líneas `ATOM` en un editor o script; el pipeline del proyecto prepara desde el PDB según `core/docking.py`.

## Test manual de Vina (ajusta rutas a tu ligando .pdbqt)
Usa **las mismas** `center_*` y `size_*` que el catálogo anterior para comparar con una corrida del agente.

```powershell
.\tools\vina\vina.exe --receptor data\receptors\4HJO.pdbqt --ligand data\dock_tmp\ligands\tu_ligando.pdbqt `
  --center_x 21 --center_y 11.5 --center_z -0.5 `
  --size_x 20 --size_y 20 --size_z 20 `
  --exhaustiveness 4 --num_modes 3
```

## Contexto biológico (resumen)
- Dominio quinasa EGFR; bisagra **Met793** en inhibidores tipo I; referencias químicas típicas: erlotinib/gefitinib (benchmarks literarios, no prescripción).

## Errores comunes
- **Caja desalineada** con el catálogo → docking incomparable con el resto del equipo / MLflow.
- Mezclar coordenadas de tutoriales antiguos (p. ej. `-43, -2, 38`) con el **catálogo actual** del repo.
