# DrugAgent — Aviso legal y científico

**DrugAgent** es software de investigación y demostración para **descubrimiento de fármacos *in silico***. No es un producto sanitario, no diagnostica, no prescribe y no sustituye el juicio de profesionales cualificados.

## Alcance

- Los candidatos generados son **hipótesis computacionales**, no fármacos aprobados.
- Las métricas de docking (kcal/mol) **no son equivalentes** a IC50/Ki/EC50 de ensayos experimentales.
- El paso de “dinámica molecular” en el pipeline es un **proxy de estabilidad**, no una simulación termodinámica completa (OpenMM/GROMACS).
- Los modelos ADMET son **aproximaciones** (ML o heurísticas), no estudios *in vivo*.
- La capa de evidencia ChEMBL usa **datos públicos** con fines de contexto químico; no implica validez clínica del candidato.

## Modos de ejecución

| Modo | Descripción |
|------|-------------|
| **Docking real** | Requiere AutoDock Vina instalado localmente (`tools/vina/vina.exe` en Windows). |
| **Docking mock** | Score QSAR determinista cuando Vina no está disponible — útil para demos, no para publicaciones sin etiquetar. |
| **LLM local** | Ollama / API compatible OpenAI en `LOCAL_LLM_BASE_URL`. |
| **LLM cloud** | Groq/Gemini opcionales si configuras API keys. |
| **Evidencia ChEMBL** | Requiere internet; consulta la API REST de EBI ChEMBL. |

## Uso responsable

- No uses DrugAgent para sintetizar o adquirir sustancias controladas.
- Los guardrails SMARTS bloquean algunos esqueletos de alto riesgo; **no son exhaustivos**.
- Revisa siempre estructuras, patentes y normativa antes de cualquier trabajo de laboratorio.

## Sin garantía

El software se proporciona “tal cual”, bajo licencia MIT. Los autores no asumen responsabilidad por decisiones científicas, legales o clínicas tomadas a partir de los resultados.

Para instalación en Windows y Vina, ver [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md).
