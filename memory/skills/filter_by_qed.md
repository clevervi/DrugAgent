# Skill: Filtrar candidatos por QED (guía)

## Rol en DrugAgent
El **generator** no recibe una lista de candidatos con QED ya calculado: produce SMILES nuevos. Por tanto **no** uses aquí una función tipo `filter_by_qed(candidatos, umbral)` como hook de generación.

## Dónde aplicar QED
- Tras **RDKit** en el generator (`compute_properties` / `QED.qed`).
- En el **analyzer** para ranking y gates (según `config/config.yaml` → `thresholds.min_qed`).

## Umbral orientativo
- QED alto (p. ej. > 0.7) suele correlacionar con drug-likeness; es heurístico, no evidencia clínica.

## Si el reflector sugiere “skill con código”
- La firma requerida para código ejecutable en `memory/skills/` es: **`(batch_size, scaffolds) -> list[str]`** de SMILES.
- Para solo filtrar por QED, mejor **ajustar YAML** o el flujo del analyzer, no `exec` desde markdown.
