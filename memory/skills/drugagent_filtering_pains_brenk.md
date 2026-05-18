# Skill: Filtros PAINS, Brenk y guardrails (con matices)

## Qué hace el código hoy
- **PAINS / Brenk**: catálogos RDKit `FilterCatalog` en el nodo analyzer (alertas estructurales).
- **Guardrails propios**: `utils/guardrails.py` (SMARTS de alto riesgo / misuse); rechazo duro por seguridad y cumplimiento.

## PAINS: no es “todo lo malo”
- PAINS detecta **patrones que a menudo dan falsos positivos** en ensayos biofísicos; **no** son una lista de venenos.
- Fármacos aprobados pueden contener subestructuras “PAINS-like” en contexto optimizado. Uso en el agente: **filtrar candidatos tempranos**, no dogma absoluto sin revisión.

## Brenk
- Señala **funcionalidades** asociadas a riesgo sintético, reactividad o PK desfavorable según la literatura compilada en RDKit. Tratar como **señal amarilla** salvo política explícita del proyecto.

## Guardrails vs PAINS
- **Guardrail** = política ético-legal del producto (bloqueo).
- **PAINS** = calidad científica de screening in silico (advertencia o rechazo según umbral del pipeline).

## Recomendación operativa para el reflector
- Si muchos hits caen en PAINS: priorizar **cambio de scaffold** o generación condicionada, no solo “bajar umbral”.
- Si Brenk dispara pero química medicinal justifica el grupo: documentar excepción en el informe de misión (no silenciar).

## Referencias de estudio (externas al repo)
- TeachOpenCADD (Volkamer): tutoriales de filtrado y subestructuras no deseadas.
- Blog y docs oficiales de RDKit sobre curación de filtros PAINS.
