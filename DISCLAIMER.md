# DrugAgent — Aviso Legal y Científico

**DrugAgent** es software de investigación y demostración para **descubrimiento de fármacos *in silico***. No es un producto sanitario, no diagnostica enfermedades, no prescribe tratamientos y no sustituye el juicio de profesionales cualificados en medicina, farmacología o química.

---

## Alcance y limitaciones científicas

### Candidatos moleculares

Los compuestos generados son **hipótesis computacionales**, no fármacos aprobados ni compuestos con actividad biológica demostrada. Un SMILES generado por DrugAgent requiere, como mínimo, las siguientes fases de validación experimental antes de poder atribuirle utilidad clínica:

1. Síntesis química y caracterización estructural (RMN, espectrometría de masas)
2. Ensayos de unión biofísica (SPR, ITC, fluorescencia)
3. Estudios de actividad celular (IC50 en líneas celulares relevantes)
4. Evaluación ADMET experimental (DMPK, hepatotoxicidad, hERG patch clamp)
5. Estudios in vivo en modelos animales
6. Ensayos clínicos en fases I–III

### Docking molecular

Las métricas de docking (kcal/mol) son **estimaciones de energía libre de unión**, no equivalentes a IC50, Ki, EC50 ni Kd medidos experimentalmente. AutoDock Vina tiene un error cuadrático medio de aproximadamente 1–2 kcal/mol frente a datos cristalográficos. Los rankings relativos dentro de una misma corrida son más informativos que los valores absolutos.

### Proxy de dinámica molecular

El nodo `md_simulator` usa la mecánica molecular MMFF94 (energía de strain conformacional) como **proxy de estabilidad estructural**. No es una simulación termodinámica completa (OpenMM, GROMACS, AMBER). No captura la dinámica del receptor, efectos de solvatación, conformaciones inducidas por el ligando, ni contribuciones entrópicas al binding.

### Modelos ADMET

Las predicciones de hERG, permeabilidad en BHE, inhibición de CYP3A4, toxicidad y absorción son **aproximaciones basadas en random forests** entrenados con datos públicos (ChEMBL, literatura). No sustituyen estudios DMPK experimentales ni perfiles farmacocinéticos in vivo.

### Evidencia ChEMBL

Los datos de actividad biológica recuperados de ChEMBL se utilizan únicamente como **contexto químico de referencia**. La presencia de compuestos con actividad reportada frente a un blanco no implica validez clínica de los candidatos generados por DrugAgent.

### Literatura PubMed

Los resúmenes recuperados vía PubMed E-utilities se inyectan en el contexto del reflector para mejorar la dirección de la búsqueda química. No constituyen una revisión sistemática de la evidencia científica.

---

## Modos de ejecución

| Modo | Descripción |
|---|---|
| **Docking real (Vina)** | Requiere `tools/vina/vina.exe`. Scores: energías de unión calculadas por AutoDock Vina 1.x. |
| **Docking mock** | Score QSAR determinista (función de propiedades fisicoquímicas). Útil para demos y pruebas; los resultados deben etiquetarse explícitamente como "mock". |
| **LLM local (Ollama)** | Inferencia local vía API compatible con OpenAI. La calidad de los SMILES generados depende del modelo. |
| **LLM cloud (Groq/Gemini)** | APIs de terceros opcionales. Sujetos a sus propias condiciones de uso y políticas de privacidad. |
| **OFFLINE_MODE** | Sin LLM: solo heurísticas RDKit + scaffold hopping. No requiere internet. |
| **ChEMBL** | Consultas a la API REST de EBI ChEMBL. Requiere conexión a internet. |

---

## Uso responsable

- No utilices DrugAgent para sintetizar, adquirir, distribuir ni suministrar sustancias controladas o de potencial abuso.
- Los guardrails estructurales (patrones SMARTS en `utils/guardrails.py`) bloquean algunos esqueletos de alto riesgo conocidos. **No son exhaustivos** y no sustituyen la supervisión humana.
- Revisa siempre las estructuras generadas, el estado de patentes y la normativa regulatoria vigente antes de cualquier trabajo de laboratorio.
- En entornos académicos o industriales, consulta con tu comité de ética y departamento legal antes de usar DrugAgent en proyectos de investigación formales.

---

## Sin garantía

El software se proporciona "tal cual" (AS IS), bajo licencia MIT, sin garantía de ningún tipo, expresa o implícita. Los autores y colaboradores no asumen responsabilidad por:

- Decisiones científicas, comerciales, legales o clínicas tomadas a partir de los resultados
- Inexactitudes en las predicciones de docking, ADMET u otras métricas computacionales
- Daños directos o indirectos derivados del uso del software

---

Para instalación detallada: [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)  
Para arquitectura técnica: [ARCHITECTURE.md](ARCHITECTURE.md)  
Para políticas de seguridad: [SECURITY.md](SECURITY.md)
