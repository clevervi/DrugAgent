# Skill: Reproducibilidad de corridas (Prisma + MLflow + config)

## Identificadores
- **Run Prisma**: `Run.id` en SQLite; enlazado a MLflow vía `mlflow_run_id` cuando el entrypoint lo persiste.
- **MLflow**: experimento `DrugAgent/{therapeutic_area}/{target_name}` (según `utils/mlflow_logger.py`) y métricas por iteración desde el analyzer cuando hay run activo.

## Qué congelar para comparar dos corridas
- Snapshot de CLI ya guardado en `config_snapshot` del run (JSON).
- Copia lógica de `config/config.yaml` relevante: `docking`, `thresholds`, `pipeline`, `scoring_weights`, `mlflow`.
- Modo efectivo: `docking_mode` final (`real` / `mock`) y variable de entorno `DOCKING_MODE` si se forzó desde UI/CLI.

## Artefactos
- CSV de candidatos y poses en rutas bajo `mlruns/` y `data/docked_poses/` según configuración.
- Log de consola duplicado en `output/agent.log` (se trunca al iniciar `run_agent.py`).

## Buenas prácticas
- Un cambio científico = un run nuevo; no reutilizar el mismo `run_id` mental para resultados distintos.
- Si comparas autónomo vs manual, etiquetar en `config_snapshot.mode` o en notas MLflow.

## Límite conocido
- `MemorySaver` de LangGraph en memoria: **no** hay checkpoint durable del grafo entre procesos salvo que se implemente otro checkpointer.
