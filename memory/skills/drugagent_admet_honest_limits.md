# Skill: ADMET en DrugAgent — límites honestos del modelo

## Qué es `MLADMETPredictor` en este proyecto
- Modelo **local** (Random Forest sobre fingerprints + descriptores) entrenado con un **conjunto pequeño** de ejemplos en código (`utils/ml_admet.py`).
- Sirve para **orden relativo** y señales gross dentro de una corrida, no para etiquetas regulatorias (AMES, hERG cuantitativo, DILI, etc.).

## Cómo hablar de los números
- Evitar: “toxicidad baja certificada por el modelo”.
- Preferir: “toxicidad **proxy** coherente con el entrenamiento actual; requiere ensayo experimental”.

## Coherencia con el gate del analyzer
- El pipeline puede marcar “alta calidad” con umbrales estrictos de tox **proxy**; si el RF está mal calibrado para kinasas, el gate puede **subestimar o sobreestimar** calidad real.
- Cualquier cambio de umbral debe ir en `config/config.yaml` y reflejarse en informes / MLflow.

## Mejora científica real (fuera de una skill .md)
- Sustituir o ampliar el training set con datos tabulares públicos versionados (CSV en `data/`), documentar versión del modelo en MLflow (`log_param`).

## MD proxy
- El nodo MD del grafo **no** ejecuta OpenMM/GROMACS en producción: es **proxy determinista**. No confundir con RMSD de trayectoria real.
