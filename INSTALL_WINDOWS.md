# Instalación en Windows (DrugAgent)

Guía verificada para **Windows 10/11** con Python 3.10+.

## 1. Dependencias base

```powershell
cd DrugAgent
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
npx prisma db push
```

Copia la plantilla de entorno:

```powershell
copy .env.example .env
```

Edición recomendada para demo **local-first** (LinkedIn / sin cloud):

```env
OFFLINE_MODE=False
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3.2
LOCAL_LLM_TIMEOUT=300
DATABASE_URL=file:./data/drugagent.db
MLFLOW_TRACKING_URI=sqlite:///./data/mlflow.db
```

Comprueba el modelo con `ollama list` y usa el **nombre exacto** en `LOCAL_LLM_MODEL`.

## 2. Ollama (LLM local)

1. Instala [Ollama para Windows](https://ollama.com/download).
2. `ollama pull llama3.2` (o el modelo que prefieras).
3. Deja Ollama en ejecución antes de `python run_agent.py`.

Opcional cloud: define `GROQ_API_KEY` o `GEMINI_API_KEY` y deja `LOCAL_LLM_BASE_URL` vacío.

## 3. AutoDock Vina (docking real)

El repo **no incluye** el binario por licencia/tamaño.

1. Descarga Vina para Windows desde [AutoDock Vina releases](https://github.com/ccsb-scripps/AutoDock-Vina/releases) o el paquete que uses habitualmente.
2. Coloca el ejecutable en:

   ```
   tools\vina\vina.exe
   ```

3. Verifica:

   ```powershell
   .\tools\vina\vina.exe --version
   python scripts\test_docking_real.py
   ```

Sin `vina.exe`, el pipeline usa **modo mock** (QSAR determinista). MLflow registrará `docking_mode: mock`.

### Meeko (ligandos PDBQT)

Ya está en `requirements.txt`. El simulador prepara ligandos con RDKit/Meeko cuando Vina está activo.

## 4. Primera corrida

```powershell
python run_agent.py --target EGFR --pdb 4HJO --iterations 3
```

Modo autónomo:

```powershell
python run_autonomous.py
```

## 5. Paneles

```powershell
mlflow ui --backend-store-uri sqlite:///./data/mlflow.db --port 5000
npx prisma studio --url file:./data/drugagent.db
streamlit run ui/dashboard.py
```

## 6. Evidencia ChEMBL (opcional, requiere internet)

```powershell
python scripts/fetch_chembl_evidence.py --target EGFR --pdb 4HJO
```

## Solución de problemas

| Síntoma | Acción |
|---------|--------|
| `No API Key` | Configura `LOCAL_LLM_BASE_URL` o keys Groq/Gemini, o `OFFLINE_MODE=True` (solo heurísticas). |
| Docking siempre mock | Instala `tools\vina\vina.exe` o fuerza `DOCKING_MODE=real` solo si Vina existe. |
| Unicode en consola | Ya se redirige stdout a UTF-8 en `run_agent.py`; usa terminal Windows moderna. |
| PDB inválido | Usa pares del catálogo: `catalog/therapeutic_areas.yaml`. |

Ver también [DISCLAIMER.md](DISCLAIMER.md).
