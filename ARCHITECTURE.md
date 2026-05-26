# DrugAgent — Technical Architecture

This document provides a full technical breakdown of the DrugAgent pipeline: how the nodes are wired, what each one does scientifically and computationally, how state flows between them, and how the persistence subsystems interact.

---

## Pipeline overview

DrugAgent is a **closed-loop agentic pipeline** built on LangGraph. Each iteration of the loop corresponds to one complete cycle of the following nodes:

```
plan ──► generate ──► simulate ──► analyze ──► md_simulate ──► reflect
                                                                    │
                          ◄─────────────────── loop ────────────────┘
                                                                    │
                                                               output (end)
```

The `plan` node runs only once at startup. All other nodes repeat for `max_iterations` cycles or until the reflector decides to terminate.

---

## State

All data flows through a single `AgentState` TypedDict defined in `orchestrator/state.py`. Key fields:

| Field | Type | Description |
|---|---|---|
| `target_name` | `str` | Protein target (e.g. `"EGFR"`) |
| `target_pdb_id` | `str` | RCSB PDB entry (e.g. `"4HJO"`) |
| `iteration` | `int` | Current loop count |
| `current_batch` | `list[MoleculeCandidate]` | Molecules processed in this iteration |
| `all_candidates` | `list[MoleculeCandidate]` | Cumulative history of all candidates |
| `top_candidates` | `list[MoleculeCandidate]` | Top 10 by docking score (historically sorted) |
| `best_score` | `float` | Best docking score seen so far (kcal/mol) |
| `priority_scaffolds` | `list[str]` | Valid SMILES suggested by reflector for next iteration |
| `insights` | `list[str]` | SAR insights from the reflector |
| `skill_content` | `dict[str, str]` | Loaded skill Markdown content (keyed by filename stem) |
| `skill_failures` | `dict[str, str]` | Tracebacks from failed skill executions |
| `memory_context` | `str` | ChromaDB RAG retrieval result injected into generation |
| `docking_mode` | `str` | `"real"` or `"mock"` — set by the simulator |
| `next_action` | `str` | Routing signal read by the LangGraph router |
| `run_id` | `str` | Unique run identifier (Prisma DB foreign key) |

`MoleculeCandidate` is also a TypedDict. Every field is optional to allow progressive population across pipeline stages:

```python
class MoleculeCandidate(TypedDict, total=False):
    smiles: str
    mol_id: str
    iteration: int
    mw: float
    logp: float
    qed: float
    hbd: int
    hba: int
    tpsa: float
    docking_score: Optional[float]
    binding_affinity: Optional[float]
    admet_toxicity: Optional[float]
    admet_solubility: Optional[float]
    admet_absorption: Optional[float]
    herg_risk: Optional[float]
    bbb_permeability: Optional[float]
    cyp3a4_inhibition: Optional[float]
    pains_alert: bool
    brenk_alert: bool
    sa_score: Optional[float]
    ligand_efficiency: Optional[float]
    md_rmsd: Optional[float]
    md_refined_score: Optional[float]
    md_strain_energy: Optional[float]
    md_flexibility: Optional[str]
    status: str
    score_final: Optional[float]
```

---

## Node-by-node breakdown

### 1. Planner (`orchestrator/nodes/planner.py`)

**Runs:** Once, at pipeline start.

**Purpose:** Primes the agent with target-specific pharmacophore context that will guide the first generation cycle.

**Method:**
- Sends a short prompt to the configured LLM (local, Groq, or Gemini) asking for the key structural requirements of an inhibitor for the target.
- Falls back to a template string if no LLM is available.
- Stores the response as `memory_context` in state.

**Fallback chain:** Local LLM → Gemini → Groq → hardcoded template.

---

### 2. Generator (`orchestrator/nodes/generator.py`)

**Runs:** Every iteration.

**Purpose:** Produce a batch of novel, chemically valid SMILES strings.

**Generation pathway:**

```
ChromaDB RAG retrieval
        │
        ▼
Priority scaffolds validation  ←── from reflector (SMILES only; invalid strings discarded)
        │
        ▼
  ┌─────────────────────────────────────────────────┐
  │ Try in order until batch is filled:             │
  │  1. Local LLM (Ollama/OpenAI-compatible)        │
  │  2. Gemini Flash                                │
  │  3. Groq llama-3.3-70b                         │
  │  4. Dynamic skill function (exec'd Python)      │
  │  5. RDKit BRICS + scaffold hopping (proxy mode) │
  └─────────────────────────────────────────────────┘
        │
        ▼
 Validate each SMILES:
   - RDKit parseability
   - Lipinski / profile filter
   - PAINS / Brenk (structural alerts)
   - Tanimoto similarity blacklist (vs. breakthrough candidates and prior batch)
   - Structural safety guardrails
```

**BRICS scaffold hopping (proxy mode):**

1. Pick a scaffold from `active_scaffolds` (priority scaffolds + `KINASE_SCAFFOLDS` fallback pool)
2. With probability 0.7: BRICS-decompose the scaffold and 1–2 random pool members, recombine up to 6 fragments using `BRICSBuild`
3. With probability 0.3: apply string-level substitutions (`mutate_smiles`)
4. Validate and add to batch

**Workflow modes:**
- `de_novo`: pure BRICS/LLM generation from scaffolds
- `lead_opt`: generates analogs of `parent_smiles` constrained by Tanimoto similarity ≥ 0.50 to the parent
- `repurposing`: seeds generation from ChEMBL active compounds fetched via REST API, constrained by Tanimoto ≥ 0.40 to each seed

**Dynamic skills:** If a `*.md` file in `memory/skills/` is in `exec_allowlist` and contains a ````python` block, the code is `exec()`-d at runtime. The extracted callable receives `(batch_size: int, scaffolds: list[str])` and must return `list[str]` (SMILES). Failed skills are captured with full tracebacks and forwarded to the reflector for self-healing.

---

### 3. Simulator (`orchestrator/nodes/simulator.py`)

**Runs:** Every iteration.

**Purpose:** Score each candidate molecule against the target protein using 3D molecular docking.

**Docking box resolution (in order of priority):**

1. `catalog/therapeutic_areas.yaml` entry for the current PDB ID — if `center != (0,0,0)`
2. Dynamic detection via `find_ligand_centroid_and_box()`: locates HETATM atoms in the PDB file using a DBSCAN-like approach; falls back to protein centroid if no ligand found
3. Config file fallback (`config.yaml → docking → center_*`)

**Real docking (AutoDock Vina):**

```
smiles_to_pdbqt(smiles, ligand_dir)          # RDKit ETKDGv3 → Meeko → PDBQT
        │
run_vina_native(receptor, ligand, center, box, exhaustiveness)
        │
parse stdout → extract mode 1 affinity (kcal/mol)
        │
mol_data["docking_score"] = score            # negative = stronger binding
```

Parallelized over the batch using `ThreadPoolExecutor(max_workers=min(4, batch_size))`. Temporary PDBQT files are written to a UUID-named subdirectory and cleaned up after each batch.

**Batch limit:** When real Vina is active, the batch is trimmed to top 10 by QED score before docking to control wall-clock time.

**Fallback chain:**
- Mode `real` (forced): raises `ValueError` if Vina or receptor unavailable
- Mode `auto`: uses real Vina if `tools/vina/vina.exe` exists and receptor prepared; falls back to mock
- Mode `mock` (forced): always uses `mock_score()`

**Mock score:** Deterministic function of molecular properties (logP, MW, rotatable bonds, ring count) with a small seeded noise term. Always returns negative values in the −5 to −10 kcal/mol range. Useful for pipeline testing; clearly labeled as mock in all outputs.

---

### 4. Analyzer (`orchestrator/nodes/analyzer.py`)

**Runs:** Every iteration.

**Purpose:** Apply ADMET predictions and structural filters; persist all candidates to SQLite; select top candidates for MD refinement.

**ADMET model (`utils/ml_admet.py`):**

Multi-label random-forest classifier trained on public data. Feature vector per molecule:
- 512-bit Morgan ECFP4 fingerprint (radius=2)
- Physicochemical descriptors: MW, logP, TPSA, HBD, HBA, rotatable bonds, ring count, aromatic ring count, fraction Csp3

Predicted endpoints (all as probabilities 0–1):
- `admet_toxicity` — broad multi-endpoint toxicity risk
- `admet_absorption` — oral absorption probability
- `admet_solubility` — aqueous solubility probability
- `herg_risk` — hERG channel inhibition (cardiac toxicity proxy)
- `bbb_permeability` — blood-brain barrier penetration
- `cyp3a4_inhibition` — CYP3A4 metabolism liability

**Structural filters:**
- PAINS (pan-assay interference compounds) — 480 SMARTS patterns
- Brenk alerts — 105 SMARTS patterns for reactive/unstable groups
- SA score (synthetic accessibility, 1–10; lower = easier to synthesize)

**Quality gate:** Candidates with `docking_score < min_docking_score` (default −6.5 kcal/mol) are flagged. Top candidates for MD simulation are selected by combining docking score and QED.

**Persistence (`orchestrator/db.py`):** Prisma ORM upserts each candidate into the `Candidate` table using `(run_id, smiles)` as a composite unique key. Writes all ADMET fields, structural alert flags, SA score, docking score, and filter results.

---

### 5. MD Simulator (`orchestrator/nodes/md_simulator.py`)

**Runs:** Every iteration, on `top_k_for_md` candidates (default 5).

**Purpose:** Evaluate conformational stability of the shortlisted candidates using molecular mechanics — a fast proxy for what a full MD simulation would assess.

**MMFF94 protocol:**

```python
mol_h = AddHs(mol)
EmbedMolecule(mol_h, ETKDGv3())          # Generate 3D conformer (seeded by SMILES hash)
ff = MMFFGetMoleculeForceField(mol_h)
energy_before = ff.CalcEnergy()
ff.Minimize(maxIts=500)
energy_after = ff.CalcEnergy()

strain = max(0.0, energy_before - energy_after)   # True conformational tension
return round(strain / 10.0, 2)                    # Scaled kcal/mol
```

A strain energy above 10 kcal/mol (scaled) indicates structural tension and adds a penalty to the refined docking score.

**Flexibility classification:**

| Rotatable bonds | Class |
|---|---|
| ≤ 3 | `rigid` |
| 4–7 | `flexible` |
| ≥ 8 | `highly_flexible` |

`highly_flexible` molecules incur an additional 0.3 kcal/mol entropic penalty on the refined score (approximating binding entropy loss).

**Refined score:** `md_refined_score = docking_score + strain_penalty + entropy_penalty`

**Why not real MD?** Full molecular dynamics (OpenMM, GROMACS) requires GPU time, parameterized force fields per molecule, system solvation, equilibration, and production runs of tens of nanoseconds. For a pipeline running 50 iterations on a laptop, MMFF94 provides a computationally tractable proxy that identifies the most problematic geometries.

---

### 6. Reflector (`orchestrator/nodes/reflector.py`)

**Runs:** Every iteration.

**Purpose:** Analyze iteration results, extract SAR insights, decide next strategy, optionally write a new generation skill.

**Inputs assembled for the LLM:**
- Top-3 candidates: SMILES, docking score, QED, hERG, BBB
- Iteration statistics: number docked, average score, best score
- PubMed literature context (iterations 1 and every 5th)
- MMP/SAR analysis (when ≥ 10 total candidates; Murcko scaffold grouping + matched molecular pairs)
- ChromaDB RAG retrieval for the current target
- Tracebacks of any failed dynamic skills (triggers self-healing response)

**LLM output format (strict JSON):**

```json
{
    "analysis": "One-sentence assessment of this iteration",
    "insights": ["SAR insight 1", "SAR insight 2"],
    "next_strategy": "generate",
    "strategy_reason": "Why this strategy was chosen",
    "new_skill": {
        "generate": false,
        "name": "skill_name_snake_case",
        "description": "What this skill does",
        "content": "Markdown with embedded ```python block```"
    },
    "priority_scaffolds": ["valid_smiles_1", "valid_smiles_2"],
    "terminate": false
}
```

**Priority scaffold validation:** Scaffolds returned by the reflector are validated with `Chem.MolFromSmiles()` in the generator before use. Invalid notation (e.g. motif descriptions like `O=C(Ar1)Ar2`) is silently discarded rather than causing RDKit error floods.

**ChromaDB persistence:** Extracted insights are embedded and stored in ChromaDB, keyed by target name and iteration number. The generator retrieves the top-k most semantically relevant insights at the start of the next iteration.

**Fallback:** If all LLMs fail, a heuristic offline mode generates a basic insight from the iteration statistics and chooses `"generate"` as the next strategy.

**Self-healing skills:** When `skill_failures` is non-empty, the LLM receives the exact Python tracebacks and is instructed to return a corrected skill via `new_skill`. The corrected version overwrites the broken file on disk.

---

## Routing

The `router` function in `orchestrator/graph.py` reads `state["next_action"]` to determine which node runs next:

```python
mapping = {
    "generate": "generate",
    "simulate": "simulate",
    "analyze": "analyze",
    "reflect": "reflect",
    "output": "output",
    "end": "__end__",
}
```

The reflector sets `next_action` to `"generate"` for normal iteration, `"output"` when the reflector sets `terminate: true` or max iterations are reached, or `"__end__"` on excessive error accumulation (≥ 10 consecutive errors).

A separate `analyze_router` function handles the conditional edge from `analyze` → either `md_simulate` (normal) or `output` (human review flag set).

---

## Persistence subsystems

### SQLite via Prisma ORM

Schema file: `prisma/schema.prisma`

Two primary models:
- **`Run`**: one record per `run_agent.py` invocation — target, PDB ID, workflow mode, timing, status, MLflow run ID
- **`Candidate`**: one record per unique `(run_id, smiles)` pair — all computed properties including full ADMET profile, MD strain, flexibility, docking scores

The Prisma client is initialized once per process (`orchestrator/db.py`) and shared across all nodes. Compound unique key `@@unique([run_id, smiles])` prevents duplicate entries on re-analysis.

### ChromaDB vector store

Path: `memory/chroma/`

Collection: `drug_discovery_insights`

Each document is a reflector-generated insight string. Metadata includes `target`, `iteration`, and timestamp. The generator queries this collection using semantic similarity search with the prompt `"insights e indicaciones científicas para diseñar inhibidores de {target}"` to retrieve the most relevant SAR knowledge.

### MLflow

Backend: `data/mlflow.db` (SQLite)

Logged per run:
- **Parameters:** target, PDB ID, workflow mode, docking mode, max iterations, filter profile
- **Metrics (per iteration):** best docking score, average score, candidate count, QED average, hERG risk average
- **Artifacts:** top candidates JSON, evidence report, PDF

---

## Safety architecture

Safety enforcement happens at three independent layers:

### Layer 1 — Structural blocklist (generator, non-configurable)

`utils/guardrails.py` defines `RESTRICTED_PATTERNS`: a set of SMARTS patterns covering opioid-like cores, fentanyl analogs, cocaine-like scaffolds, organophosphate threat agents, and mustard-gas derivatives. Every candidate SMILES is checked against these patterns before being added to any batch. Matching candidates are silently rejected with a log entry. These patterns are hardcoded and cannot be disabled via config, environment variables, or LLM instruction.

### Layer 2 — Execution allowlist (generator, configurable)

LLM-generated Python skills are `exec()`-d only when the skill's filename stem appears in `config.yaml → skills.exec_allowlist`. An empty list disables all dynamic code execution. Each skill receives only `batch_size` and `scaffolds` as arguments; no access to state, filesystem, or network is explicitly provided (though not sandboxed at OS level).

### Layer 3 — Target validation (entry point)

`utils/target_validation.py` is called from `run_agent.py` before the pipeline starts. It:
- Validates that the PDB ID exists in RCSB PDB
- Checks that the target name is scientifically coherent with the PDB structure (e.g. rejects PD-L1 with an EGFR structure)
- Emits warnings for unusual combinations

---

## LLM fallback chain

The pipeline is designed to degrade gracefully when LLMs are unavailable:

```
Local LLM (LOCAL_LLM_BASE_URL)
    │ fail
    ▼
Gemini Flash (GEMINI_API_KEY)
    │ fail
    ▼
Groq llama-3.3-70b (GROQ_API_KEY)
    │ fail (or OFFLINE_MODE=True)
    ▼
Heuristic / deterministic fallback
(planner: template string)
(generator: BRICS scaffold hopping)
(reflector: score-based insight from state statistics)
```

Every node independently implements this chain. A failure in one node's LLM call never propagates to crash the loop.

---

## Extension points

### Adding a new target

Add an entry to `catalog/therapeutic_areas.yaml`:

```yaml
my_new_target:
  display_name: "Area: Target — Indication"
  target: "TARGET_NAME"
  pdb_id: "1ABC"
  receptor_path: "data/receptors/1ABC_receptor.pdbqt"
  disclaimer: "Computational in silico simulation. Requires experimental validation."
  docking_params:
    center_x: 12.5    # Set to 0,0,0 to trigger dynamic box detection
    center_y: 8.3
    center_z: -4.1
    size_x: 22.0
    size_y: 22.0
    size_z: 22.0
  planner_prompt: "Design inhibitors that ..."
```

If `center_x/y/z` are all 0.0, the simulator automatically falls back to `find_ligand_centroid_and_box()` which computes the box from HETATM ligand coordinates in the PDB file.

### Adding a new generation skill

The reflector will generate skills autonomously. To add one manually:

1. Create `memory/skills/my_skill.md`:

   ````markdown
   # My Skill

   Brief description of what this skill does.

   ```python
   def my_skill(batch_size: int, scaffolds: list) -> list:
       """Generate SMILES. Must return a list of SMILES strings."""
       from rdkit import Chem
       results = []
       # ... your generation logic ...
       return results
   ```
   ````

2. Add `my_skill` to `config.yaml → skills.exec_allowlist`.

### Adding a new ADMET endpoint

1. Extend the training labels in `utils/ml_admet.py` and retrain the model.
2. Add the new field to `MoleculeCandidate` in `orchestrator/state.py`.
3. Populate the field in `orchestrator/nodes/analyzer.py` and include it in the Prisma upsert call.
4. Add the column to `prisma/schema.prisma` and run `npx prisma db push`.

---

## Data flow diagram

```
run_agent.py
    │
    │  initial_state: AgentState
    ▼
LangGraph StateGraph.invoke()
    │
    ├─► planner_node()
    │       └── returns: memory_context
    │
    ├─► generator_node()  ◄──────────────────────── (loop starts here)
    │       ├── ChromaDB.query() → memory_context injection
    │       ├── validate priority_scaffolds (SMILES check)
    │       ├── LLM or BRICS → smiles_list
    │       └── returns: current_batch (MoleculeCandidate list)
    │
    ├─► simulator_node()
    │       ├── catalog lookup → docking box center
    │       ├── Vina subprocess (parallel) or mock_score()
    │       └── returns: current_batch (+ docking_score, status)
    │
    ├─► analyzer_node()
    │       ├── ml_admet.predict() → hERG, BBB, CYP3A4, toxicity, absorption
    │       ├── PAINS/Brenk/SA filters
    │       ├── Prisma.candidate.upsert() ← persists everything
    │       └── returns: top_candidates, current_batch (+ ADMET fields)
    │
    ├─► md_simulator_node()
    │       ├── MMFF94 conformer generation + minimization
    │       ├── strain = energy_before - energy_after
    │       ├── Prisma.candidate.update() ← md fields
    │       └── returns: top_candidates (+ md_strain_energy, md_flexibility)
    │
    ├─► reflector_node()
    │       ├── PubMed E-utilities (iterations 1, 6, 11, ...)
    │       ├── MMP/SAR analysis (≥ 10 total candidates)
    │       ├── LLM → JSON analysis
    │       ├── save_new_skill() if skill generated
    │       ├── ChromaDB.add() ← insight embedding
    │       └── returns: next_action, priority_scaffolds, insights
    │
    └─► router() → "generate" (next iteration) or "output" (terminate)
```
