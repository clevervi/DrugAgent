# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` on GitHub | Yes |

## Reporting a vulnerability

If you discover a security issue, please **do not** open a public issue with exploit details.

Email or open a private security advisory on GitHub for repository `clevervi/DrugAgent` with:

- Description and impact
- Steps to reproduce
- Suggested fix (if any)

## Threat model (what we consider in scope)

1. **Arbitrary code execution via skills**  
   Python blocks in `memory/skills/*.md` run only through `exec()` when the skill stem is listed in `config/config.yaml` → `skills.exec_allowlist`. Keep this list minimal.

2. **Secrets in repository**  
   Never commit `.env`. Rotate `GROQ_API_KEY` / `GEMINI_API_KEY` if they were ever pushed.

3. **Subprocess invocation**  
   CLI and dashboard spawn `run_agent.py`, Streamlit, and MLflow with user-controlled env vars. Run only on trusted machines.

4. **Generated skills**  
   The reflector can write new `.md` files under `memory/skills/`. Review before adding any name to `exec_allowlist`.

## Out of scope

- Scientific false positives/negatives in docking or ADMET (not CVEs).
- Misuse of generated SMILES for illicit synthesis (user responsibility; guardrails are best-effort).

## Recommendations for operators

- Use `OFFLINE_MODE=True` and `LOCAL_LLM_BASE_URL` for air-gapped demos.
- Do not expand `exec_allowlist` without code review.
- Keep `data/evidence/` and local databases out of public forks if they contain proprietary runs.
