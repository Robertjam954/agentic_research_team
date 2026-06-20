# Contributing Guidelines

## Setup

1. Prerequisites:
   - Python 3.11+
   - [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) (for deployment, **target**)
   - `az login` / `azd auth login` for Azure resource access
2. Virtual env + deps:
   ```bash
   cd /Users/robertjames/Documents/GitHub/agentic_research_team
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill it in (never commit `.env`):
   - `OPENAI_API_KEY`, `GRAPHRAG_API_KEY`, `GRAPHRAG_ROOT` (current)
   - `AZURE_DOCDB_CONNECTION_STRING`, `AZURE_DOCDB_DATABASE` (Mongo vCore)
   - `AZURE_STORAGE_*` (Blob)
   - `AZURE_REDIS_*`, `AZURE_POSTGRES_*`, `AZURE_OPENAI_*`, `LANGSMITH_*` (target)

## Local dev loop

```bash
# Current research pipeline (entrypoint stays stable through the migration)
python -c "import asyncio; from src.agents.biomedical_agents import run_research; \
    print(asyncio.run(run_research('<biomedical question>')).final_output)"

# Full pipeline (corpus -> index -> summaries)
./scripts/run_pipeline.sh

# LangGraph orchestrator (target)
# langgraph dev          # local graph server for the orchestrator
```

## Coding conventions

- **Tools.** Every callable exposed to a model is a typed `@tool` with a
  one-sentence imperative docstring - the model sees the signature + docstring, so
  do not duplicate that elsewhere. Register tools in `src/agents/tools.py`.
- **Skills (deepagents).** Reusable content formats are `skills/<name>/SKILL.md`
  with YAML frontmatter (`name`, `description`) + a markdown body (format / tone /
  length). The agent loads them on demand; keep one skill per file.
- **Human-in-the-loop.** Tools that write, send, or charge must be gated -
  `interrupt_on={"write_file": True, ...}` and resumed with
  `Command(resume=...)`. Read-only tools run without approval.
- **No mutable module-level agent state.** Build the graph/agent inside a factory
  so re-entry is clean.
- **Env vars only.** No hard-coded endpoints, model names, or keys. Add new
  config to `.env.example` and document it in `PRODUCT.md` / `ARCHITECTURE.md`.
- **Secrets.** Connection strings / keys come from `.env` (gitignored) or Key
  Vault. The Mongo/Azure credentials shared during setup are treated as
  compromised and must be rotated before deploy.
- **No em dashes** - single hyphen `-` only. **Pipeline model default:**
  `claude-sonnet-4-20250514` where a Claude model is used.

## Architecture Decision Records (required on architectural change)

Any change that alters architecture - a new store, a new agent/framework, a
caching layer, a deploy target - must land with an ADR:

1. Branch and make the change.
2. `git diff main` to get the exact delta.
3. Generate an ADR from the diff using `docs/adr/0000-template.md`; explain the
   **why**, not just the what (which store/approach and what was rejected).
4. Commit the ADR in the same PR as the change. (The Self-Documenting agent
   automates steps 2-3; see ARCHITECTURE.md - **target**.)

## Pull request checklist

- [ ] `python -m compileall src/` passes.
- [ ] `run_research()` still imports and runs (no regression to the entrypoint).
- [ ] New tools have a docstring + typed parameters; new skills have frontmatter.
- [ ] New env vars are in `.env.example` and documented.
- [ ] Architectural change includes an ADR under `docs/adr/`.
- [ ] If infra changed, `azd provision --preview` runs clean (**target**).
- [ ] No secrets committed (`.env`, `.azure/` are gitignored).

## New-project documentation standard

When this repo (or a derived project) starts new work, adopt the standard from
`azure_agent_deployment_tools_responses_api`: copy `PRODUCT.md`,
`ARCHITECTURE.md`, `CONTRIBUTING.md`, and `plan-template.md`, and use the
context-engineering workflow (`docs/context-engineering-workflow.md`) plus the
planner/TDD agents (`.github/agents/{plan,tdd}.agent.md`). Plans go under
`docs/plans/` using `plan-template.md`.

## What not to add

- A second vector store for a concern the CLAUDE.md data tier already assigns.
- Plaintext secrets, or config that bypasses `.env` / Key Vault.
- A web UI or end-user auth - out of scope (see PRODUCT.md).
