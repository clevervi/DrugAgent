# Installation Guide — Windows 10/11

This guide covers a complete local installation of DrugAgent on Windows, including optional components (Ollama, AutoDock Vina, cloud LLM keys). Follow the sections relevant to your setup.

---

## Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| Windows | 10 (21H2) or 11 | 64-bit only |
| Python | 3.10 | 3.12 recommended; 3.13 not yet tested |
| Git | Any recent | For cloning and version control |
| Node.js | 18 LTS | Required for `npx prisma` |
| RAM | 8 GB | 16 GB recommended when running Ollama locally |
| Disk | 5 GB free | More if downloading multiple Ollama models |

**Python:** Install from [python.org](https://www.python.org/downloads/). During installation, check **Add Python to PATH**.

**Node.js:** Install from [nodejs.org](https://nodejs.org/). The LTS version is sufficient.

**Git:** Install from [git-scm.com](https://git-scm.com/download/win).

---

## Step 1 — Clone the repository

```powershell
git clone https://github.com/clevervi/DrugAgent.git
cd DrugAgent
```

---

## Step 2 — Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\activate
```

Your prompt should show `(venv)` after activation. All subsequent commands in this guide assume the virtual environment is active.

---

## Step 3 — Install Python dependencies

```powershell
pip install -r requirements.txt
```

This installs RDKit, LangGraph, LangChain, Prisma client, ChromaDB, MLflow, Streamlit, scikit-learn, FPDF2, and all other dependencies. Expect 3–8 minutes depending on your connection speed.

**If you see RDKit errors:** RDKit requires a compatible C++ runtime. On clean Windows installations you may need to install the [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

---

## Step 4 — Initialize the database

```powershell
npx prisma db push
```

This creates `data/drugagent.db` (SQLite) with the full schema — runs, candidates, ADMET fields, generated skills. You must run this before the first launch.

If `npx` is not recognized, verify that Node.js is installed and on PATH (`node --version`).

---

## Step 5 — Configure the environment

```powershell
copy .env.example .env
```

Open `.env` in any text editor and configure the sections relevant to your setup:

### Option A — Fully local, no API keys (simplest)

```env
OFFLINE_MODE=True
DATABASE_URL=file:./data/drugagent.db
MLFLOW_TRACKING_URI=sqlite:///./data/mlflow.db
DOCKING_MODE=auto
```

The reflector and generator will use deterministic heuristics. No internet required. Good for testing the pipeline end-to-end.

### Option B — Local LLM via Ollama (recommended)

```env
OFFLINE_MODE=False
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3.2
LOCAL_LLM_TIMEOUT=300
LOCAL_LLM_CONNECT_TIMEOUT=15
DATABASE_URL=file:./data/drugagent.db
MLFLOW_TRACKING_URI=sqlite:///./data/mlflow.db
DOCKING_MODE=auto
```

See [Step 6](#step-6--ollama-local-llm-optional) for Ollama setup.

### Option C — Cloud LLM (Groq or Gemini)

```env
OFFLINE_MODE=False
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=AIzaSy_your_key_here
DATABASE_URL=file:./data/drugagent.db
MLFLOW_TRACKING_URI=sqlite:///./data/mlflow.db
DOCKING_MODE=auto
```

Leave `LOCAL_LLM_BASE_URL` blank. The pipeline tries Gemini first, then falls back to Groq.

---

## Step 6 — Ollama (local LLM, optional)

Skip this step if using cloud keys or `OFFLINE_MODE=True`.

1. Download and install [Ollama for Windows](https://ollama.com/download/windows).
2. Pull a model. Recommended options:

   ```powershell
   ollama pull llama3.2          # 2 GB — good balance of quality and speed
   ollama pull qwen2.5-coder:7b  # 4.7 GB — stronger at structured JSON output
   ollama pull llama3.1:8b       # 4.7 GB — good for reasoning
   ```

3. Verify Ollama is running:

   ```powershell
   ollama list
   ```

4. Set `LOCAL_LLM_MODEL` in `.env` to the **exact** name shown by `ollama list` (e.g. `llama3.2`, not `llama3`).
5. Leave Ollama running in the background before starting DrugAgent.

---

## Step 7 — AutoDock Vina (real docking, optional)

Skip this step if you want to use mock scoring for demos or testing.

1. Download the Windows binary from [AutoDock-Vina releases on GitHub](https://github.com/ccsb-scripps/AutoDock-Vina/releases). Choose the latest stable release; download `vina_1.x.x_win.exe`.

2. Create the tools directory and place the binary:

   ```powershell
   mkdir tools\vina
   copy C:\path\to\downloaded\vina_win.exe tools\vina\vina.exe
   ```

3. Verify the installation:

   ```powershell
   tools\vina\vina.exe --version
   ```

   Expected output: `AutoDock Vina 1.x.x`

4. Run the connectivity test:

   ```powershell
   python scripts\test_docking_real.py
   ```

5. Set docking mode in `.env`:

   ```env
   DOCKING_MODE=auto    # auto-detects vina.exe; falls back to mock if missing
   ```

   Or force real mode (will raise an error if Vina is missing):

   ```env
   DOCKING_MODE=real
   ```

**Receptor files:** PDB structures are downloaded from RCSB automatically on first run. If you are running air-gapped, pre-download the relevant PDB files into `data/receptors/` naming them `<PDB_ID>.pdb` (e.g. `4HJO.pdb`).

**Meeko (ligand preparation):** Already included in `requirements.txt`. DrugAgent uses Meeko to convert RDKit molecules to PDBQT format for Vina input.

---

## Step 8 — First run

### Interactive menu (recommended for first time)

```powershell
python cli\interactive_menu.py
```

This walks you through target selection, workflow mode, and number of iterations interactively.

### Direct command-line launch

```powershell
# Quick test — 3 iterations, EGFR, mock or real docking depending on your setup
python run_agent.py --target EGFR --pdb 4HJO --iterations 3

# Lead optimization example
python run_agent.py ^
  --target EGFR --pdb 4HJO ^
  --workflow lead_opt ^
  --parent-smiles "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1" ^
  --iterations 5

# Autonomous loop (cycles through all 18 targets)
python run_autonomous.py
```

---

## Step 9 — Dashboards

### Streamlit (primary dashboard)

```powershell
streamlit run ui\dashboard.py
```

Opens at `http://localhost:8501`. Shows live logs, UMAP chemical space, Pareto-front candidates, ADMET tables, and full run history. Keep the terminal running while the agent is active.

### MLflow experiment tracker

```powershell
mlflow ui --backend-store-uri sqlite:///./data/mlflow.db --port 5000
```

Opens at `http://localhost:5000`. Tracks metrics, parameters, and artifacts across all runs for experiment comparison.

### Prisma Studio (database browser)

```powershell
npx prisma studio
```

Opens at `http://localhost:5555`. Direct read/write access to the SQLite database for inspecting candidates, runs, and skills.

---

## Step 10 — Verify the installation

Run the full test suite to confirm everything is wired up correctly:

```powershell
python scripts\test_all.py
python scripts\test_guardrails.py
```

All tests should pass. The guardrails test in particular verifies that the structural safety blocklist is working correctly.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ValueError: No API Key` | Neither `LOCAL_LLM_BASE_URL`, `GROQ_API_KEY`, nor `GEMINI_API_KEY` is set | Set `OFFLINE_MODE=True` or configure at least one LLM option |
| `UnicodeDecodeError: charmap` | YAML config opened without encoding | Already fixed in codebase; update to latest commit |
| Docking always mock | `vina.exe` not found | Place binary at `tools\vina\vina.exe` |
| Docking scores all 0.0 | Docking box doesn't overlap the protein | Use a target from the catalog — custom PDBs without catalog entries use dynamic box detection |
| `prisma: command not found` | Node.js or npx not on PATH | Install Node.js and restart your terminal |
| Ollama timeout / connection refused | Ollama not running | Start Ollama, confirm with `ollama list` |
| `LOCAL_LLM_MODEL` not recognized | Wrong model name | Use exact name from `ollama list`, e.g. `llama3.2` not `llama3` |
| `ModuleNotFoundError: rdkit` | RDKit not installed or wrong Python | Activate the virtual environment; reinstall `pip install -r requirements.txt` |
| Streamlit dashboard blank | Agent not run yet | Run at least one iteration first to populate the database |
| PDF not generated | `fpdf2` not installed or output folder missing | `pip install fpdf2`; the folder is created automatically by `run_agent.py` |
| `PDB ID not found` | Invalid or non-existent PDB entry | Use an ID from `catalog/therapeutic_areas.yaml` or verify at rcsb.org |
| `skill exec blocked` | Skill name not in `exec_allowlist` | Add the skill filename (without `.md`) to `config.yaml → skills.exec_allowlist` |
| High memory usage | Large batch + Ollama running | Reduce `batch_size` in `config.yaml → resources` |

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `OFFLINE_MODE` | `False` | `True` = heuristics only, no LLM, no internet |
| `LOCAL_LLM_BASE_URL` | _(empty)_ | OpenAI-compatible endpoint (e.g. Ollama at `http://localhost:11434/v1`) |
| `LOCAL_LLM_MODEL` | `llama3` | Exact model tag from `ollama list` |
| `LOCAL_LLM_TIMEOUT` | `300` | Request timeout in seconds |
| `GROQ_API_KEY` | _(empty)_ | Groq cloud API key |
| `GEMINI_API_KEY` | _(empty)_ | Google Gemini API key |
| `DATABASE_URL` | `file:./data/drugagent.db` | Prisma SQLite connection string |
| `MLFLOW_TRACKING_URI` | `sqlite:///./data/mlflow.db` | MLflow backend |
| `DOCKING_MODE` | `auto` | `auto` / `real` / `mock` |
| `DEFAULT_TARGET` | `EGFR` | Default target for CLI shortcuts |
| `DEFAULT_PDB_ID` | `4HJO` | Default PDB ID for CLI shortcuts |

---

## Updating

```powershell
git pull
pip install -r requirements.txt   # pick up new dependencies
npx prisma db push                 # apply any schema changes
```

Always run `prisma db push` after pulling updates that touch `prisma/schema.prisma`.

---

## Uninstalling

```powershell
# Deactivate and delete the virtual environment
deactivate
rmdir /s /q venv

# Optionally remove generated data
rmdir /s /q data
rmdir /s /q output
rmdir /s /q memory\chroma
```

The repository folder itself can then be deleted or kept.
