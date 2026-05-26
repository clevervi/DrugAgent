# DrugAgent

**Autonomous closed-loop drug discovery platform** — generates, docks, filters, and iteratively optimizes small-molecule candidates against protein targets using a self-correcting multi-agent pipeline that runs entirely on your local machine.

> **Scientific disclaimer:** DrugAgent produces computational *in silico* candidates. All results require experimental validation (in vitro assays, crystallography, in vivo studies) before any scientific or clinical interpretation. Docking scores are binding-affinity estimates, not measured Kd values. This is a research and educational tool, not a medical device or clinical decision system. See [DISCLAIMER.md](DISCLAIMER.md).

---

## What it does

The pipeline runs a continuous five-stage loop without human intervention, accumulating SAR knowledge across iterations:

| Stage | Node | Method |
|---|---|---|
| **Plan** | `planner` | LLM generates target-specific pharmacophore guidance to seed the search |
| **Generate** | `generator` | RDKit BRICS fragment recombination + scaffold hopping; LLM-directed in cloud/local mode |
| **Dock** | `simulator` | AutoDock Vina (Windows-native, no WSL2); physics-based mock scoring when Vina unavailable |
| **Filter** | `analyzer` | Multi-label ADMET random-forest (hERG, BBB, CYP3A4, toxicity, absorption) + Lipinski / PAINS / Brenk |
| **Refine** | `md_simulator` | MMFF94 conformational strain energy + rotatable-bond flexibility classification |
| **Reflect** | `reflector` | LLM extracts SAR insights, proposes next scaffold strategy, autonomously writes and deploys Python skills |

ChromaDB stores vector-indexed insights from each iteration so later generations benefit from the full accumulated SAR knowledge base.

---

## Architecture

```
 Entry points
 ┌────────────────┬───────────────────┬────────────────────┐
 │ run_agent.py   │ interactive_menu  │ run_autonomous.py  │
 └───────┬────────┴─────────┬─────────┴──────────┬─────────┘
         │                  │                     │
         └──────────────────▼─────────────────────┘
                    orchestrator/graph.py
                    (LangGraph StateGraph)
                            │
          ┌─────────────────┼─────────────────────┐
          ▼                 ▼                      ▼
      planner          generator              simulator
          │            RDKit BRICS           AutoDock Vina
          │            LLM prompt            mock fallback
          │                 │                      │
          │            analyzer               md_simulator
          │            ADMET RF               MMFF94 strain
          │            PAINS/Brenk                  │
          │                 └──────────┬────────────┘
          │                         reflector
          │                         LLM + skills
          │                            │
          └────────────── loop ─────────┘

 Persistence layer
 ├── ChromaDB    (RAG vector memory — scientific insights across iterations)
 ├── SQLite      (Prisma ORM — candidates, runs, generated skills)
 └── MLflow      (experiment tracking — metrics, parameters, artifacts)
```

Full technical breakdown: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Feature matrix

| Feature | Detail |
|---|---|
| **Three generation modes** | `de_novo` (BRICS from scratch), `lead_opt` (bioisosteric optimization of a parent SMILES), `repurposing` (ChEMBL-seeded active analogs) |
| **18 pre-configured targets** | EGFR, KRAS G12C, PD-L1, ABL1, CDK2, BRAF V600E, PARP1, JAK2, HDAC1, DPP-4, AChE, HIV-1 Integrase, SARS-CoV-2 Mpro, Dengue NS3, Zika NS2B-NS3, RSV-F — plus any valid RCSB PDB entry |
| **Custom target support** | Any `--pdb` ID is validated against RCSB at runtime; receptor downloaded automatically |
| **Dynamic skills** | Reflector LLM writes Python generation functions that persist to `memory/skills/` and self-heal when they raise errors |
| **Autonomous loop** | `run_autonomous.py` cycles through all targets indefinitely; agent chooses the next mission |
| **ADMET profiling** | Per-candidate predictions for hERG cardiotoxicity, blood-brain barrier permeability, CYP3A4 inhibition, multi-endpoint toxicity |
| **Conformational stability** | MMFF94 strain energy (kcal/mol, true conformational tension) + `rigid` / `flexible` / `highly_flexible` classification |
| **RAG memory** | ChromaDB retrieves SAR context from previous iterations to guide each generation cycle |
| **Full telemetry** | MLflow tracks every run's metrics, parameters, and top-candidate artifacts |
| **Hard safety guardrails** | Non-configurable SMARTS blocklist rejects opioid cores, organophosphate threats, mustard-gas derivatives, and controlled-substance scaffolds |
| **Skill execution allowlist** | LLM-generated Python only runs if the skill filename appears in `config.yaml → skills.exec_allowlist` |
| **Dashboard** | Streamlit UI with live logs, UMAP chemical space, Pareto-front viewer, ADMET tables, full run history |
| **PDF reports** | Candidate cards with docking scores, ADMET profiles, strain energy, PubMed literature context |
| **SDF export** | Top candidates exported as 3D SDF for downstream visualization or further computation |
| **MMP/SAR analysis** | Murcko scaffold grouping and matched molecular pairs injected into reflector context every 5 iterations |

---

## Quick start

**Requirements:** Python 3.10–3.12 · Git · Windows 10/11 (Linux/macOS work with minor path adjustments)

```bash
# 1. Clone
git clone https://github.com/clevervi/DrugAgent.git
cd DrugAgent

# 2. Virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Linux / macOS

# 3. Dependencies
pip install -r requirements.txt

# 4. Database schema
npx prisma db push

# 5. Environment (edit .env to set your LLM and docking options)
copy .env.example .env

# 6. Launch — interactive menu guides you through everything
python cli/interactive_menu.py
```

For a fully local run with no API keys needed:

```env
OFFLINE_MODE=True
```

Complete setup guide: [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)

---

## Running missions

### Interactive menu

```bash
python cli/interactive_menu.py
```

Guides you through target selection, workflow mode, and iteration count with a full terminal UI. Recommended for first-time use.

### Command line

```bash
# De novo design — EGFR kinase, 20 iterations
python run_agent.py --target EGFR --pdb 4HJO --iterations 20

# Lead optimization — start from erlotinib core, find bioisosteres
python run_agent.py \
  --target EGFR --pdb 4HJO \
  --workflow lead_opt \
  --parent-smiles "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1" \
  --iterations 15

# Drug repurposing — seed generation from ChEMBL active compounds
python run_agent.py --target DPP4 --pdb 3HAJ --workflow repurposing --iterations 10

# KRAS G12C — switch-II pocket, export SDF for visualization
python run_agent.py \
  --target KRAS --pdb 6VXX \
  --area "Oncología" --indication "Adenocarcinoma de Pulmón (KRAS G12C)" \
  --iterations 25 --export-sdf

# SARS-CoV-2 main protease
python run_agent.py --target MPRO --pdb 6LU7 --iterations 30
```

### Autonomous multi-target loop

```bash
# Cycles through 18 targets indefinitely; agent picks the next mission
python run_autonomous.py
```

### Dashboards

```bash
# Streamlit — live metrics, chemical space, ADMET, run history
streamlit run ui/dashboard.py

# MLflow — experiment comparison, parameter tuning history
mlflow ui --backend-store-uri sqlite:///./data/mlflow.db --port 5000

# Prisma Studio — direct database browsing
npx prisma studio
```

---

## AutoDock Vina (real docking)

Without Vina the pipeline uses a deterministic physics-based mock score (useful for testing and offline demos). To enable real 3D docking:

1. Download the Windows binary from the [AutoDock Vina releases page](https://github.com/ccsb-scripps/AutoDock-Vina/releases)
2. Place the executable at `tools/vina/vina.exe`
3. Verify: `tools\vina\vina.exe --version`
4. Set `DOCKING_MODE=auto` (default) or `DOCKING_MODE=real` in `.env`

The pipeline auto-detects the binary at startup. Receptor PDB files are downloaded from RCSB automatically on first use when not present in `data/receptors/`.

---

## Configuration reference

All parameters live in `config/config.yaml`. Key settings:

```yaml
# Molecular filter profile
filter_profile: standard      # standard | permissive | cns | natural_products

# Docking
docking_mode: auto            # auto | real | mock

# Quality gate — candidates with better scores than this threshold qualify
thresholds:
  min_docking_score: -6.5     # kcal/mol (more negative = stronger binding)
  max_mw: 500                 # Daltons
  min_qed: 0.4                # Drug-likeness (0–1)
  max_toxicity: 0.5           # ADMET toxicity probability

# Pipeline
pipeline:
  iterations: 50
  top_k_for_md: 5             # Candidates sent to MMFF94 strain analysis

# Skill execution security
skills:
  exec_allowlist:
    - diversity_enhancer_v4   # Only named skills can execute Python code
```

**Filter profiles:**

| Profile | MW | logP | HBD | TPSA | Use case |
|---|---|---|---|---|---|
| `standard` | ≤ 500 | ≤ 5.0 | ≤ 5 | ≤ 140 | General drug discovery |
| `permissive` | ≤ 800 | ≤ 7.0 | ≤ 10 | ≤ 200 | Fragment/scaffold exploration |
| `cns` | ≤ 450 | 0–5 | ≤ 3 | ≤ 90 | CNS / brain-penetrant drugs |
| `natural_products` | ≤ 1000 | ≤ 7.0 | ≤ 10 | ≤ 250 | Macrolides, cyclopeptides |

---

## Output files

| Path | Contents |
|---|---|
| `output/agent.log` | Full timestamped run log (UTF-8, ANSI-stripped) |
| `data/drugagent.db` | SQLite — all runs, candidates, ADMET data, generated skills |
| `data/mlflow.db` | MLflow experiment tracking database |
| `data/evidence/<run_id>/` | ChEMBL evidence comparison report per run |
| `output/report_<run_id>.pdf` | PDF with candidate cards, docking tables, SAR summary |
| `output/top_candidates_<run_id>.sdf` | 3D SDF export (requires `--export-sdf` flag) |
| `memory/skills/` | LLM-generated Python skills (Markdown files with embedded code) |
| `memory/chroma/` | ChromaDB vector index of scientific insights |

---

## Project structure

```
DrugAgent/
├── catalog/
│   └── therapeutic_areas.yaml    # 18 pre-configured targets with docking params
├── cli/
│   └── interactive_menu.py       # Rich/questionary terminal UI
├── config/
│   └── config.yaml               # Main runtime configuration
├── core/
│   └── docking.py                # Vina wrapper, receptor prep, mock scoring, DBSCAN pocket detection
├── data/
│   ├── receptors/                # PDB and PDBQT receptor files
│   ├── evidence/                 # ChEMBL evidence reports per run
│   └── mlflow.db                 # MLflow backend
├── memory/
│   ├── skills/                   # LLM-generated skill files
│   └── chroma/                   # ChromaDB vector store
├── orchestrator/
│   ├── graph.py                  # LangGraph StateGraph — node wiring and routing
│   ├── state.py                  # AgentState TypedDict definition
│   ├── db.py                     # Prisma client initialization
│   └── nodes/
│       ├── planner.py            # Target-specific pharmacophore planning
│       ├── generator.py          # BRICS generation + LLM + skill execution
│       ├── simulator.py          # AutoDock Vina docking (parallel ThreadPoolExecutor)
│       ├── analyzer.py           # ADMET multi-label RF + structural filters + DB persistence
│       ├── md_simulator.py       # MMFF94 strain energy + flexibility classification
│       └── reflector.py          # LLM SAR analysis + skill authoring + ChromaDB write
├── ui/
│   └── dashboard.py              # Streamlit live dashboard
├── utils/
│   ├── guardrails.py             # SMARTS blocklist + configurable filter profiles
│   ├── ml_admet.py               # ADMET random-forest model (scikit-learn)
│   ├── memory_db.py              # ChromaDB read/write interface
│   ├── mlflow_logger.py          # MLflow experiment telemetry
│   ├── pdf_generator.py          # FPDF2 report generation
│   ├── pubmed_client.py          # PubMed E-utilities for literature context
│   ├── mmp_analysis.py           # Matched molecular pairs and SAR correlation
│   ├── evidence_report.py        # ChEMBL public activity comparison
│   ├── breakthrough.py           # Breakthrough candidate detection and registration
│   ├── sdf_exporter.py           # 3D SDF export via RDKit
│   ├── target_validation.py      # PDB ID / target name coherence check
│   └── scoring.py                # Deterministic noise for reproducible mock scores
├── scripts/
│   ├── test_all.py               # Integration test suite
│   ├── test_guardrails.py        # Safety filter verification
│   ├── test_docking_real.py      # Vina connectivity test
│   └── fetch_chembl_evidence.py  # Manual ChEMBL evidence fetch
├── run_agent.py                  # Single-run entry point (argparse CLI)
├── run_autonomous.py             # Autonomous multi-target loop
└── requirements.txt
```

---

## Safety and ethics

DrugAgent is designed exclusively for legitimate medicinal chemistry research and education. Multiple independent safety layers are in place:

- **Structural blocklist** (`utils/guardrails.py`): SMARTS patterns permanently block opioid-like cores, fentanyl analogs, organophosphate threat structures, mustard-gas derivatives, and cocaine-like scaffolds. These rules are hardcoded and cannot be overridden by any config file, environment variable, runtime argument, or LLM instruction.
- **Target validation**: PDB IDs are validated against RCSB PDB at startup. The system checks that the target name and structure are scientifically coherent.
- **Skill execution allowlist**: LLM-generated Python code can only run if the exact skill filename appears in `config.yaml → skills.exec_allowlist`. An empty list disables all skill execution entirely.
- **Full audit trail**: Every candidate, run, and skill is persisted in SQLite with timestamps, run IDs, and provenance.
- **No synthesis guidance**: The system generates SMILES strings and binding affinity estimates only. It provides no synthesis routes, no sourcing guidance, and no dosage information.

---

## Limitations

**Read this section before citing or publishing results from DrugAgent.**

1. **Docking scores are estimates.** AutoDock Vina empirical free energies carry a root-mean-square error of approximately 1–2 kcal/mol versus experiment. Relative rankings within a run are meaningful; absolute values should not be directly compared to experimental IC50 or Ki values without calibration.

2. **Mock scoring is not docking.** When Vina is unavailable, scores derive from a QSAR-like deterministic function. Results are useful for pipeline testing and offline demos, but should be clearly labeled and not compared to real Vina output.

3. **ADMET predictions are heuristic.** The random-forest model was trained on publicly available ChEMBL and literature data using Morgan fingerprints and physicochemical descriptors. It captures broad trends but will miss behavior on novel scaffolds distant from the training set. Do not substitute these predictions for experimental DMPK assays.

4. **MMFF94 is not molecular dynamics.** The conformational stability proxy identifies structurally strained molecules but cannot capture protein-induced conformational selection, solvation effects, or entropic contributions to binding.

5. **PubMed and ChEMBL context is informational.** Literature and activity data are injected into the LLM context to improve generation quality. They do not constitute validation of generated candidates.

6. **LLM outputs are non-deterministic.** Scaffold suggestions, insights, and generated skills depend on the LLM in use. Results will vary between runs. Skills are reviewed and controlled through the allowlist system.

---

## Running tests

```bash
# Full integration suite
python scripts/test_all.py

# Safety filter verification (guardrails must block all known bad structures)
python scripts/test_guardrails.py

# Vina connectivity (requires tools/vina/vina.exe)
python scripts/test_docking_real.py

# Fetch ChEMBL public evidence for a target
python scripts/fetch_chembl_evidence.py --target EGFR --pdb 4HJO
```

---

## License

MIT — see [LICENSE](LICENSE).

*Developed by [clevervi](https://github.com/clevervi)*
