# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `main` branch | Yes |
| Any tagged release | Yes |

## Reporting a vulnerability

If you discover a security issue, **do not open a public GitHub issue** with exploit details.

Instead, email `raivel.studio@gmail.com` or open a [private security advisory](https://github.com/clevervi/DrugAgent/security/advisories/new) on GitHub with:

- A clear description of the issue and its potential impact
- Steps to reproduce (minimally)
- A suggested fix or mitigation if you have one

You will receive an acknowledgment within 72 hours. We aim to release a fix within 14 days for critical issues.

---

## Threat model

The following attack surfaces are considered in scope:

### 1. Arbitrary code execution via dynamic skills

Dynamic Python skills in `memory/skills/*.md` are `exec()`-d through the generator node. Controls in place:

- Skills only execute if their filename stem (without `.md`) is listed in `config/config.yaml → skills.exec_allowlist`.
- An empty allowlist disables all skill execution entirely.
- The reflector LLM writes skills, but they do not run until a human explicitly adds the name to the allowlist.

**Recommendation:** Review every skill file before adding it to the allowlist. The skill function signature is constrained to `(batch_size: int, scaffolds: list) -> list[str]`, but `exec()` with `globals()` does not enforce this at the OS level.

### 2. Secrets in the repository

DrugAgent requires API keys for cloud LLM providers (Groq, Gemini). These must live in `.env`, which is listed in `.gitignore`.

**Recommendation:** Never commit `.env`. If keys were ever pushed, rotate them immediately at the provider's dashboard.

### 3. Subprocess invocation

The pipeline spawns `vina.exe` as a subprocess with arguments constructed from SMILES-derived filenames. Filenames are UUID-based (`uuid.uuid4().hex`) and created in a temporary subdirectory, limiting path-injection surface.

**Recommendation:** Run DrugAgent only on trusted machines. Do not expose the Streamlit dashboard or MLflow UI to untrusted networks without authentication.

### 4. LLM-generated content

The reflector LLM can write files to `memory/skills/`. The generator LLM proposes SMILES strings. Both are subject to prompt-injection risk from ChromaDB context retrieved from prior iterations.

**Recommendation:** Monitor `memory/skills/` for unexpected files. The structural guardrails in `utils/guardrails.py` filter LLM-generated SMILES independently of LLM behavior.

### 5. Database access

`data/drugagent.db` and `data/mlflow.db` contain all run history and candidate data. These are local SQLite files with no authentication.

**Recommendation:** Keep the `data/` directory out of public forks. Do not expose Prisma Studio (`npx prisma studio`) to untrusted networks.

---

## Out of scope

- **Scientific false positives/negatives** in docking or ADMET prediction are not CVEs.
- **Misuse of generated SMILES** for illicit synthesis is the user's legal and ethical responsibility. The built-in guardrails are best-effort and explicitly not exhaustive.
- **Rate limiting or abuse** of third-party APIs (Groq, Gemini, PubMed, ChEMBL) is the user's responsibility under those providers' terms of service.

---

## Built-in safety controls

These controls are part of the codebase and are not configurable by the end user:

| Control | Location | Behavior |
|---|---|---|
| Structural blocklist | `utils/guardrails.py` | SMARTS patterns blocking opioid cores, organophosphate threats, mustard-gas derivatives, cocaine-like scaffolds, fentanyl analogs — hardcoded, non-overridable |
| Skill execution allowlist | `config/config.yaml → skills.exec_allowlist` | LLM-generated Python runs only if explicitly allowed by the operator |
| PDB validation | `utils/target_validation.py` | PDB IDs checked against RCSB at startup; target/structure coherence validated |
| Candidate audit trail | `data/drugagent.db` | Every generated SMILES is persisted with provenance, timestamps, and run ID |

---

## Recommendations for operators

1. Use `OFFLINE_MODE=True` and `LOCAL_LLM_BASE_URL` for air-gapped demos and controlled research environments.
2. Keep `skills.exec_allowlist` minimal — only add skills that have been manually reviewed.
3. Review `memory/skills/` periodically for unexpected files, especially in autonomous loop mode (`run_autonomous.py`).
4. Do not expose dashboards (Streamlit port 8501, MLflow port 5000, Prisma Studio port 5555) to public networks.
5. Keep `data/evidence/` and local databases out of public repository forks — they may contain proprietary research outputs.
6. Rotate cloud API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`) on a regular schedule and immediately after any suspected leak.
