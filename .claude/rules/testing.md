---
paths:
  - "tests/**/*.py"
  - "src/**/*.py"
---

# Testing conventions (project-specific)

Portfolio `CLAUDE.md` sets the baseline: >80% line coverage on new code, the
`tests/{unit,integration,e2e}` layout, and descriptive `test_<subject>_<behavior>`
names. Project specifics:

- **Never call live LLM or Azure services in unit tests or CI.** Mock the OpenAI
  Agents SDK, GraphRAG query, web search, Cosmos, and Blob. Live calls are
  non-deterministic, cost money, and leak keys into CI.
- **GraphRAG fixtures use a tiny symlinked subset**, never the full index. Indexing
  is one LLM call per chunk; tests must not trigger it.
- **Required agent tests:**
  - a tool test per registered tool (input schema in, handled output/error out);
  - one agent-loop test that drives triage -> research end to end with mocks;
  - one e2e smoke that runs a fixed question and asserts a structured, cited result
    shape (not exact text).
- **`research_pipeline` parity check (target):** when the LangGraph adapter lands,
  add a test asserting the adapter returns the same shape as
  `biomedical_agents.run_research` for one fixed question.
- **Store helpers:** assert the best-effort no-op path (unset connection string) as
  well as the happy path against a mocked client.
- Keep tests offline and hermetic; gate coverage in CI (`--cov=src --fail-under=80`).
