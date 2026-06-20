# Product Vision and Goals

## Product

**Agentic Research Team** - a biomedical deep-research system that retrieves
evidence (GraphRAG community reasoning + vector search over a systematic-review
corpus + live web), produces citation-grounded structured summaries, and is
growing into a single LangGraph-orchestrated stack that also writes content,
captures notes into a knowledge graph, and documents its own architectural
decisions. It deploys to Azure.

## Target users

- **Clinical / biomedical researchers** who need grounded, cited answers and
  structured summaries over a curated systematic-review corpus.
- **AI engineers** extending the agent team (adding agents, tools, skills) on a
  consistent LangGraph + deepagents foundation.
- **The maintainer**, who wants every architectural choice the system makes to be
  self-documented (ADRs) and every new project scaffolded against one standard.

## Core value

1. **Grounded research, not guesses.** Three retrieval modes - graph (GraphRAG
   community/local), semantic (vector ANN over corpus chunks), and web - feed a
   summarizer that cites every claim.
2. **One orchestration spine.** LangGraph + `deepagents` runs planning,
   delegation, human-in-the-loop, memory, and checkpointing; the proven research
   pipeline is reused behind a single tool rather than rewritten.
3. **Self-documenting.** Architectural changes generate an ADR from the git diff,
   so the "why" survives past deployment; repeated LLM/retrieval calls are served
   from a Redis semantic cache.
4. **Deployable + reproducible.** azd + Bicep stand up the Azure footprint
   (models, storage, observability); a documentation standard (PRODUCT /
   ARCHITECTURE / CONTRIBUTING / plan) drops into every new project.

## Capabilities

| # | Capability | Status |
|---|---|---|
| 1 | **Research + structured summary** - graph/semantic/web retrieval, citation-grounded structured summaries | **v1 (mostly built)** |
| 2 | **Self-documenting + deploy tooling** - git-diff ADRs, Redis semantic caching, azd/Bicep deploy, observability, storage planning, doc standard | **v1 (this round documents it)** |
| 3 | **Content writer** - blog / LinkedIn from research, deepagents skills + human-in-the-loop review | **roadmap** |
| 4 | **Evaluator** - summary quality, RAG citation faithfulness, safety; deep evals | **roadmap** |
| 5 | **Notes -> Obsidian graph** - Apple Notes / blogs / YouTube ingested into an Obsidian vault (wikilinks, frontmatter, backlinks) | **roadmap (largely net-new code)** |

## In scope (v1)

- The LangGraph orchestration spine reusing the existing research pipeline as a
  `research_pipeline` tool.
- The three retrieval tools (`search_corpus_graph`, `search_corpus_semantic`,
  `web_search`) and the structured Summarizer.
- The Self-Documenting capability: ADR generation from `git diff` and Redis
  semantic caching around LLM / retrieval calls.
- Deployment tooling: azd + Bicep for the Azure footprint, observability (App
  Insights + OTel + LangSmith), storage planning, and the new-project doc
  standard.

## Roadmap (documented now, built later)

- Content Writer agent (skills for blog / LinkedIn, `interrupt_on` review gates).
- Evaluator agent + deep-eval harness.
- Notes -> Obsidian ingestion (Apple Notes export, blog scraper, YouTube
  transcripts, Obsidian markdown/graph writer).

See `docs/gaps.md` for the concrete missing artifacts behind each roadmap item.

## Out of scope

- A front-end UI - clients consume the agent via CLI / API.
- End-user authentication - the host trusts the runtime.
- Re-indexing the GraphRAG corpus - the existing index is mounted, not rebuilt.

## Success criteria

- A researcher asks a biomedical question and gets a cited, structured summary
  combining graph + semantic + web evidence.
- Every architectural change lands with an ADR generated from its git diff.
- Semantically repeated questions are served from cache in roughly the time of a
  vector lookup, not a full LLM round-trip.
- `azd provision` + `azd deploy` stand up and ship the system to Azure with no
  code edits; a new project can adopt the doc standard by copying four files.
