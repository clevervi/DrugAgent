# Skill: Lenguaje honesto para “descubrimientos” in silico

## Principios
1. **Candidato computacional** ≠ fármaco ≠ resultado clínico.
2. **Breakthrough** en este repo = umbral heurístico + registro en `data/breakthroughs.json`; no es validación FDA/EMA ni ensayo in vivo.
3. **Docking + filtros** = priorización de química para siguiente paso (síntesis, ensayo, más modelos).

## Frases permitidas (ejemplos)
- “Top pose in silico con Vina bajo estas suposiciones de receptor.”
- “Candidato pasa filtros PAINS/Brenk/guardrail del pipeline versión X.”
- “Requiere síntesis y ensayo biológico para confirmar actividad.”

## Frases a evitar
- “Cura”, “fármaco aprobado”, “seguro para humanos”, “selectivo” sin datos off-target.
- “MD confirmó estabilidad” cuando el nodo es **proxy** (ver skill ADMET / código `md_simulator.py`).

## Alineación con disclaimers del catálogo
- Respetar textos de `catalog/therapeutic_areas.yaml` en comunicaciones al usuario (UI, PDF, Rich).

## Rol del LLM (local o nube)
- El LLM **narra** y **prioriza**; la evidencia cuantitativa viene de RDKit/Vina/DB. Si chocan, gana la medición reproducible.
