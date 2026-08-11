---
paths:
  - "**"
---

# Security requirements (project-specific)

## Secrets
- **No plaintext secrets in the repo or a built image.** `.env` is gitignored and
  stays that way; only `.env.example` (placeholder values) is committed.
- **Target auth model is `DefaultAzureCredential` + Key Vault.** New Azure clients
  (pgvector, Redis, Cosmos, Blob, OpenAI) must accept credentials from the
  environment / managed identity, never a hard-coded connection string in code.
- **Rotate the shared Mongo/Azure credentials from initial setup before any deploy.**
  They are flagged as compromised in `docs/gaps.md`; treat them as burned.
- Never echo a secret into logs, run records, or a git commit.

## Data / PHI
- This repo touches biomedical study data and includes de-identification code
  (`src/ingest/deidentify_genomic_data.py`). Follow the **data-analysis-hygiene**
  skill for any patient-level or PHI-adjacent data.
- **De-identify before persisting or embedding.** Do not write raw patient
  identifiers into Cosmos, Blob, pgvector, the GraphRAG index, or logs.
- Raw source exports under `data/raw/` are gitignored - keep it that way; never
  commit anything under `data/`.

## Dependencies & tools
- External tools (web search, Microsoft Learn MCP, PubMed) run with least scope;
  add timeouts and handle failures without crashing an agent run.
- Validate and bound any tool input that reaches a shell, a DB query, or a file path.
