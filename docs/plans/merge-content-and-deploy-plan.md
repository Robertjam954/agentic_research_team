---
title: Merge content + notes + self-documenting + deploy into the research team
version: 0.1
date_created: 2026-06-20
last_updated: 2026-06-20
owner: robertjames
---

# Implementation Plan: Agentic Research Team (merged)

Grow `agentic_research_team` from a research+summary pipeline into one
LangGraph-orchestrated system that also writes content, captures notes into an
Obsidian graph, documents its own decisions, and deploys to Azure. Orchestration
standardizes on **LangGraph + deepagents**, reusing the existing OpenAI Agents SDK
pipeline as a `research_pipeline` tool (ADR 0001). Code stays in this repo and
deploys to Azure. Success: a researcher gets cited structured summaries from
graph+semantic+web evidence; architectural changes self-document via ADRs;
repeated queries are served from a Redis semantic cache; `azd` provisions/ships
the stack. See `../../ARCHITECTURE.md` and `../gaps.md`.

## Requirements

### Functional
- LangGraph orchestrator (planner+orchestrator) routes to subagents and the
  `research_pipeline` tool; checkpointing + HITL interrupts.
- Three retrieval tools: `search_corpus_graph`, `search_corpus_semantic`,
  `web_search`; structured, citation-grounded Summarizer.
- Self-Documenting: generate an ADR from `git diff`; Redis semantic cache around
  LLM/retrieval calls.
- Content Writer (blog/LinkedIn, skills + HITL) - roadmap.
- Evaluator + deep evals (quality, citation faithfulness, safety) - roadmap.
- Notes -> Obsidian (Apple Notes / blog / YouTube) - roadmap, largely net-new.

### Non-functional
- Models on Azure OpenAI (Foundry project); credentials via
  `DefaultAzureCredential` + Key Vault, no plaintext secrets.
- Same code runs locally and deployed; cost-aware (mount existing GraphRAG index,
  cache repeated calls).
- Shared Mongo/Azure credentials from setup are treated as compromised - rotate
  before deploy.

## Architecture and design

See `../../ARCHITECTURE.md` for the diagram and the framework-reconciliation
decision (ADR 0001) and the caching decision (ADR 0002). New modules:
`src/agents/{state,graph,tools}.py`, `src/agents/skills/`, `src/store/{cache,
pgvector}.py`, `infra/` (Bicep), `eval/`. Adapter boundary kept thin: LangGraph
outside, OpenAI Agents SDK inside the `research_pipeline` tool.

## Tasks

Phase 0 - docs (this round, done)
- [x] PRODUCT / ARCHITECTURE / CONTRIBUTING; ADR template + 0001/0002; gaps.md;
      AGENTS.md roster reconciled; CLAUDE.md Docs section. Acceptance: docs
      cross-link and AGENTS.md matches ARCHITECTURE.

Phase 1 - orchestration spine (C1)
- [ ] `src/agents/state.py`: `ResearchState` + `ProgressLedger`. Acceptance:
      imports, typed.
- [ ] `src/agents/tools.py`: port `search_sr_corpus`->`search_corpus_semantic`
      (pgvector), wrap `run_query.py` as `search_corpus_graph`, `web_search`.
- [ ] `research_pipeline` tool wrapping `run_research()`. Acceptance: one fixed
      question returns equivalent retrieval to the direct pipeline.
- [ ] `src/agents/graph.py`: `StateGraph`, conditional edges, stall/replan,
      checkpointer. Acceptance: `langgraph dev` runs a query end to end.

Phase 2 - self-documenting + cache (C2)
- [ ] `src/store/cache.py`: Redis semantic cache (embed -> ANN -> write-through,
      TTL). Acceptance: second similar query is a cache hit with logged latency.
- [ ] Self-Documenting middleware: `git diff` -> ADR via `docs/adr/0000-template`.
      Acceptance: a sample change emits a valid ADR.

Phase 3 - deploy + observability (C2)
- [ ] `infra/` Bicep: AI project + Azure OpenAI deployments, Managed Redis,
      Postgres+pgvector, Blob, App Insights/Log Analytics, Key Vault; wire
      `main.bicep`. Acceptance: `azd provision --preview` clean.
- [ ] Observability: App Insights + OTel + LangSmith; data-tier metrics + alerts
      (pgvector latency, Redis hit-rate/evictions, Cosmos RU, cache hit/miss);
      per-run cost to the Cosmos run record.
- [ ] Storage planning doc: size index/Blob/Postgres/Redis + cost estimate.
- [ ] Copy new-project standard: `.github/agents/{plan,tdd}.agent.md`,
      `docs/context-engineering-workflow.md`.

Phase 4 - content writer + evaluator (C3, C4)
- [ ] Content Writer deepagent + `skills/{blog-post,linkedin-post}/SKILL.md` +
      `interrupt_on` review loop.
- [ ] Evaluator agent + `eval/` Foundry deep-eval harness; CI gate.

Phase 5 - notes -> Obsidian (C5, net-new)
- [ ] Ingest: Apple Notes export, blog scraper, YouTube transcript (lift
      `zen-ai-engineer-tutor` chunking).
- [ ] Obsidian writer: markdown + frontmatter + `[[wikilinks]]` + backlinks
      (lift conventions from the content-extraction briefs).

- [ ] Update `.env.example`, `PRODUCT.md`/`ARCHITECTURE.md`, `infra/` per phase.

## Test plan

- Unit tests per new tool (`search_corpus_graph/semantic`, `web_search`, cache
  get/set, ADR generator, Obsidian writer).
- Parity: a fixed question retrieves equivalently before/after the adapter.
- Cache: repeated similar query hits; metrics recorded.
- Local e2e: `langgraph dev` query -> cited summary; `run_research()` still works.
- Deployed smoke: `azd provision --preview` + `azd deploy`.
- Eval gate: quality/safety/task-adherence baseline scorecard.

## Open questions

1. Deep-research model on Azure, or fall back to `gpt-4o` + Bing grounding for the
   Research step in v1?
2. GraphRAG index mount: Azure Files (persistent) vs Blob download at startup?
3. Obsidian vault location - local path, synced vault, or Blob-backed?

## Out of scope

- GraphRAG re-index in the serving path (mount the existing index).
- Front-end UI; end-user auth.
- Native port of the research pipeline to LangGraph (adapter for now; ADR 0001).
