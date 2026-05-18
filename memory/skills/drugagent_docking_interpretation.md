# Skill: Interpretar resultados de docking in silico

## Marco honesto
- **Docking rigid-body** (Vina clásico) estima **afinidad aproximada** en un modelo de receptor fijo; no predice permeabilidad, metabolismo, selectividad ni validez clínica.
- **Score más negativo** = mejor afinidad estimada **bajo** esa geometría de receptor, esa caja y esa preparación de ligando.

## Mock vs real
- Si el estado o log indica **mock**, el número **no es** energía de Vina experimental: es un proxy coherente para ranking interno. No informes mock como “kcal/mol Vina” sin calificar.
- Si es **real**, igualmente: reproducibilidad depende de semilla de Vina, exhaustividad y preparación PDBQT.

## Parámetros que cambian la historia
- **`exhaustiveness`**: más costo CPU, más exploración del espacio de poses; subir si el top pose salta entre corridas con la misma molécula.
- **`num_modes` / `energy_range`**: revisar si el mejor modo es estable o un outlier de alta energía relativa.

## Ligand efficiency y lectura cruzada
- Usar **LE** (score / átomos pesados) para comparar series de tamaño distinto; un dock “muy bueno” en molécula gigante puede ser menos impresionante en LE.

## Cuándo re-dockar
- Cambio de caja, de protonación del receptor, o ligando con **varios tautómeros razonables**: re-dockar explícitamente y versionar en MLflow / `config_snapshot`.

## Anti-patterns
- Afirmar “inhibidor selectivo” solo por un score en un único pocket.
- Promediar scores **mock** y **real** en la misma métrica de MLflow sin etiquetar.
