# System Architecture and Design Principles

This document is the canonical architecture for `agentic_research_team`. If the
code diverges, fix this file first, then the code. Items not yet built are marked
**(target)**.

## High-level architecture

```
Client / CLI
  |
  v
LangGraph Orchestrator  (deepagents: planner + orchestrator, checkpointer, HITL interrupts)
  |
  |-- tool:     research_pipeline(query)        -> existing OpenAI Agents SDK pipeline
  |               (Triage -> Clarify -> Instruct -> Research;
  |                retrieval: search_corpus_graph | search_corpus_semantic | web_search)
  |-- subagent: Summarizer                       -> structured, citation-grounded summary
  |-- subagent: Content Writer        (target)   -> blog / LinkedIn via skills/, write_file gated by interrupt_on
  |-- subagent: Evaluator             (target)   -> summary quality, RAG citation faithfulness, safety (deep evals)
  |-- subagent: Notes / Ingestion     (target)   -> Apple Notes / blog / YouTube -> Obsidian vault graph
  |-- middleware: Self-Documenting    (target)   -> git diff -> ADR markdown; Redis semantic cache around LLM/retrieval
  |
  v
Storage tier
  Cosmos for MongoDB vCore  - docs, conversation history, agent run records   (provisioned)
  Azure Blob Storage        - artifacts (figures/tables, GraphRAG outputs)    (provisioned)
  Azure Managed Redis       - semantic cache + working memory                 (target)
  PostgreSQL + pgvector     - primary vector store for corpus chunks          (target)
  GraphRAG index            - community/local reasoning (parquet + LanceDB)   (current, local)
  |
  v
Models: Azure OpenAI (Foundry project)   |   Observability: App Insights + OpenTelemetry + LangSmith
  |
  v
Deploy: azd + Bicep (infra/)  -> Azure   |   Doc standard scaffolds new projects (PRODUCT/ARCHITECTURE/CONTRIBUTING/plan)
```

## Framework reconciliation (the core decision)

Three frameworks were in play: the **OpenAI Agents SDK** (the working research
pipeline), the **Microsoft Agent Framework** (the Foundry/azd deployment shell),
and **LangGraph + deepagents** (content-writer skills, interrupt/resume HITL, and
the Magentic-style orchestration in `AGENTS.md`).

**Decision:** standardize orchestration on **LangGraph + deepagents** and **reuse
the existing research pipeline as a single `research_pipeline` tool** (adapter
pattern), rather than porting or rewriting it. This unifies control flow, HITL,
memory, and checkpointing on one runtime while preserving proven retrieval.
Models, storage, and deployment target **Azure**. Recorded as ADR 0001
(`docs/adr/0001-langgraph-orchestration-reuse-pipeline.md`).

Rejected: (a) Foundry-centric adapter on MS Agent Framework only - would
re-implement deepagents HITL/skills we want to reuse; (b) full LangGraph port of
the pipeline - highest rewrite cost, discards working handoff logic, and moves
off Azure Foundry hosting.

## Repository layout

| Path | Purpose | Status |
| --- | --- | --- |
| `src/agents/biomedical_agents.py` | Current 4-agent research pipeline; stays the public entrypoint `run_research()` | current |
| `src/agents/graphrag_tool.py` | GraphRAG-as-tool wrapper (`search_sr_corpus`) | current |
| `src/agents/{state,graph,tools}.py` | LangGraph `ResearchState`, `StateGraph`, typed tool registry | (target) |
| `src/agents/skills/<name>/SKILL.md` | deepagents skills (blog-post, linkedin-post, ...) | (target) |
| `src/store/docdb.py` | Cosmos for MongoDB vCore document store | current |
| `src/store/blob.py` | Azure Blob Storage for artifacts | current |
| `src/store/{cache,pgvector}.py` | Redis semantic cache; pgvector store | (target) |
| `src/graphrag/`, `src/query/`, `src/ingest/` | GraphRAG index build/query + corpus build | current |
| `infra/` | azd + Bicep: AI project, models, storage, Redis, Postgres, monitoring | (target) |
| `docs/adr/` | Architecture Decision Records (template + ADRs) | this round |
| `docs/plans/` | Implementation plans (from `plan-template.md`) | this round |
| `AGENTS.md` | Canonical agent-team spec | current |
| `PRODUCT.md` / `ARCHITECTURE.md` / `CONTRIBUTING.md` | Documentation standard | this round |

## Data / storage tier

The authoritative store-per-concern mapping lives in **`CLAUDE.md` -> "Data and
storage tier"**; this section is a pointer, not a second source of truth. Summary:
pgvector is the **primary** vector store here (fed by Databricks); Cosmos for
MongoDB vCore owns documents/history/run records; Blob owns artifacts; Redis is
ephemeral cache + working memory; GraphRAG is a retrieval *method*, not a store.

## Key design decisions

1. **LangGraph orchestration, pipeline-as-tool.** One control runtime; retrieval
   reused, not rewritten (ADR 0001).
2. **Self-documenting changes.** Architectural changes emit an ADR derived from
   `git diff`, so intent is captured at the moment of change (see CONTRIBUTING).
3. **Semantic cache before generation.** LLM/retrieval calls check a Redis
   embedding-similarity cache first (ADR 0002); Redis is never the source of
   truth.
4. **Credentials via `DefaultAzureCredential` + Key Vault.** No plaintext secrets
   in the image or repo; connection strings come from env / Key Vault.
5. **Config via env vars.** No hard-coded endpoints/models/keys; new config is
   documented in `.env.example` and `PRODUCT.md`/this file.
6. **Infra is template-only.** One reusable Bicep module per resource under
   `infra/core/<category>/`; `infra/main.bicep` wires them together. **(target)**

## Runtime flow

1. Client sends a research request to the LangGraph orchestrator.
2. Orchestrator plans (write_todos), checks the Redis semantic cache, and routes.
3. `research_pipeline` tool runs the existing pipeline; retrieval hits GraphRAG
   (graph), pgvector (semantic), and web search.
4. Summarizer synthesizes a structured, cited summary; Evaluator scores it
   **(target)**; Content Writer can render it to blog/LinkedIn with a HITL gate
   **(target)**.
5. Run records + final report persist to Cosmos; artifacts to Blob; traces to
   LangSmith + App Insights.
6. On an architectural change, the Self-Documenting middleware writes an ADR from
   the diff **(target)**.

## Non-goals

- No front-end UI; no end-user auth.
- No GraphRAG re-index in the serving path (mount the existing index).
- No second vector store for the same concern - follow the CLAUDE.md data tier.
