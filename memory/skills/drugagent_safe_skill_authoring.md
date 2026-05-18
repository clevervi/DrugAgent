# Skill: Cómo escribir skills para este repo (seguro y útil)

## Cómo las consume el generador
- El nodo generator carga `memory/skills/*.md`. Solo ejecuta bloques **```python** de skills cuyo nombre (stem del archivo) figure en **`config/config.yaml` → `skills.exec_allowlist`**. Si la lista está vacía, no hay `exec` (solo markdown como guía).

## Reglas recomendadas
1. **Skills de política / química / procedimiento**: usar **solo Markdown**, sin bloques `python`, salvo revisión explícita de un humano del laboratorio.
2. **Ejecución de código**: solo los stems listados en **`config/config.yaml` → `skills.exec_allowlist`** pueden contener ` ```python ` ejecutable por el generator. Lista vacía = **ningún** `exec`.
3. Si se incluye código: **función única**, firma **`(batch_size: int, scaffolds: list) -> list[str]`** (solo SMILES), sin efectos laterales fuera del retorno.

## Qué debe contener una skill “oro”
- **Cuándo usarla** (precondiciones).
- **Referencias a archivos reales** del repo (`catalog/...`, `config/...`, `core/docking.py`).
- **Límites** (“esto no hace selectividad”).
- **Checklist** verificable.

## Anti-patrón
- Párrafo vago: “usamos ML para optimizar afinidad” sin datos, sin métricas, sin enlace al código — no mejora al agente y puede confundir al reflector.
