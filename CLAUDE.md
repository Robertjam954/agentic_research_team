# CLAUDE.md

Operating manual for Claude Code in `agentic_research_team`. Keep this file 100%
truthful: if reality diverges, edit this file first, then the code. Where a
capability is not built yet it is marked **(target)**; everything else reflects
what is in the repo today.

---

## 1. Project Overview

**agentic_research_team** is a GraphRAG-backed biomedical deep-research stack. It
builds a Microsoft GraphRAG index over a systematic-review corpus exported from
**PubMed, Scopus, Embase, and IEEE Xplore**, surfaces hierarchical community
summaries (leaf / intermediate / macro-root), and exposes that index to a
multi-agent research team.

- **Today:** local-first. OpenAI Agents SDK + Microsoft GraphRAG (LanceDB vector
  store) + a 4-agent linear pipeline (Triage -> Clarify -> Instruct -> Research)
  in `src/agents/biomedical_agents.py`. Run end-to-end with
  `scripts/run_pipeline.sh`.
- **Target:** Azure-hosted, with a **Magentic-style multi-agent team on
  LangGraph** (see `AGENTS.md`) and the managed data tier in section 4.

`AGENTS.md` is the canonical spec for the agent team. This file owns
infrastructure, data, evals, and ops.

**Direction:** orchestration standardizes on **LangGraph + deepagents**, reusing
the existing research pipeline as a `research_pipeline` tool (not a rewrite), and
deploys to Azure. The team grows to cover content writing, notes -> Obsidian, and
self-documentation. See the docs below.

### Docs

| Doc | Purpose |
|---|---|
| [`PRODUCT.md`](PRODUCT.md) | Vision, capabilities (v1 vs roadmap), scope, success criteria |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Target architecture + framework-reconciliation decision |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Setup, conventions, ADR requirement, PR checklist |
| [`AGENTS.md`](AGENTS.md) | Canonical agent-team spec (roster, control loop, tools) |
| [`docs/plans/merge-content-and-deploy-plan.md`](docs/plans/merge-content-and-deploy-plan.md) | Master implementation backlog |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records (template + 0001/0002) |
| [`docs/gaps.md`](docs/gaps.md) | What's missing, mapped to each capability |

---

## 2. Repository Layout

```
agentic_research_team/
  data/
    raw/                 source CSV exports (gitignored)
    processed/           metadata.csv from build_corpus
    graphrag/
      input/             one .txt per study (GraphRAG input)
      output/            entities/relationships/communities/community_reports parquet
      cache/             LLM call cache
  src/
    ingest/build_corpus.py        unify CSVs -> per-study txt + metadata
    graphrag/
      settings.yaml               canonical GraphRAG config
      run_index.py                stage root, init prompts, run indexer
      extract_summaries.py        bucket communities into leaf/intermediate/root
    query/run_query.py            global/local/drift/basic search CLI + lib
    agents/
      biomedical_agents.py        CURRENT 4-agent pipeline (public entrypoint)
      graphrag_tool.py            GraphRAG-as-tool wrapper
      state.py                    (target) ResearchState + ProgressLedger
      graph.py                    (target) LangGraph StateGraph (Magentic loop)
      tools.py                    (target) typed tool registry
    publish/notion_uploader.py    push notes/reports to the blog-review Notion DB
    utils/
  prompts/    docs/    eval/    experiments/    reports/    search/
  notebooks/biomedical_research_agents.ipynb
  scripts/run_pipeline.sh
  AGENTS.md   CLAUDE.md   README.md   requirements.txt   .env.example
```

---

## 3. Pipeline (corpus -> index -> agents)

1. **Build corpus** - `python -m src.ingest.build_corpus --csv-root "$SR_CSV_ROOT"
   --out-dir data/graphrag/input --meta-csv data/processed/metadata.csv
   --require-abstract`. Parses each database's quirks (Embase is a block
   key-value format; the rest are standard CSV), dedupes by DOI, writes one
   `.txt` per study. `--require-abstract` drops abstract-less records.
2. **Index** - `python -m src.graphrag.run_index --root data/graphrag`. Produces
   `entities/relationships/communities/community_reports/text_units/documents`
   parquet under `data/graphrag/output/`.
3. **Summaries** - `python -m src.graphrag.extract_summaries` buckets community
   reports by Leiden `level` into `summaries_{macro_root,intermediate,leaf}.md`.
4. **Query / agents** - `src/query/run_query.py` (global/local/drift/basic) and
   the agent team in `src/agents/` (today linear; target = LangGraph, AGENTS.md).

Indexing is **expensive** (one LLM call per chunk for entity extraction plus
per-community summarization). Start with a symlinked subset in
`data/graphrag/input/`.

---

## 4. Data and storage tier (canonical database choices)

Authoritative mapping of which datastore owns what. Add a feature's data to the
store named here - do not stand up a parallel store for the same concern.
Vector search has multiple capable engines across the wider portfolio; **for the
biomed stack, PostgreSQL + pgvector is the primary vector store** (fed by
Databricks), which differs from the AI-tutor repo where Azure AI Search is
primary.

| Concern | Store / service | What it owns | Status |
|---|---|---|---|
| **Dataset ETL + batch embedding + analytics** | **Azure Databricks** | ingests SR CSV exports -> unified Delta tables; dedupe; batch-embeds study chunks; writes vectors to pgvector; meta-analysis feature tables | **(target)** replaces local `build_corpus.py` at scale |
| **Primary vector store** | **Azure DB for PostgreSQL Flexible Server** (`pgvector` + `azure_ai`) | study-chunk embeddings (`vector` column, HNSW index); ANN retrieval for `search_sr_corpus` | **(target)** replaces LanceDB. Query-time embeddings via `azure_openai.create_embeddings` in-DB |
| **JSON documents + conversation history** | **Azure Cosmos DB for MongoDB (vCore)** - cluster `docdb-cluster-20260619-0425` (`norwayeast`, M30, HA) | study metadata JSON, extracted entities, community summaries, conversation history, **agent run records (task + progress ledger snapshots)** | **provisioned** - connect via `pymongo` + `AZURE_DOCDB_CONNECTION_STRING` (Mongo wire protocol, not the NoSQL/azure-cosmos SDK) |
| **Knowledge graph** | **Azure Cosmos DB for Apache Gremlin** | GraphRAG entities/edges/communities for live graph queries | **(target / optional)** - GraphRAG parquet output is the source of truth today |
| **Cache + working memory** | **Azure Managed Redis** | (1) semantic / LLM-response cache, (2) live `ResearchState` working memory during a run, (3) app cache | **(target)** ephemeral / TTL'd only; Cosmos is durable record |
| **Files / artifacts** | **Azure Blob Storage** | raw exports, generated figures/tables from CoderAgent, GraphRAG outputs | **provisioned** - `src/store/blob.py`, `AZURE_STORAGE_*` |
| **Embedding producer** (not a store) | **Azure OpenAI** `text-embedding-3-large` (+ Azure AI Vision for any figures) | text (+ image) vectors written to pgvector | **(target)** |
| **Models + evals + agent hosting** | **Azure AI Foundry project / Azure OpenAI** | agent chat/reasoning models, eval runs, continuous evaluation | **(target)** |

Notes:
- **pgvector is primary here** by design (Databricks is the natural feeder and
  the workload is relational + analytical). The AI-tutor repo keeps Azure AI
  Search primary and pgvector secondary - the two repos share the Postgres
  design but assign it different ranks.
- **GraphRAG stays.** It is a retrieval *method* (`graph_search` tool), not a
  store choice. Its community index complements pgvector ANN.

---

## 5. Agents

See **`AGENTS.md`** for the full spec. Summary: a Magentic-style team on
LangGraph - **ManagerAgent** (control loop + progress ledger), **ResearchAgent**
(facts), **PlannerAgent** (plan), **SummaryAgent** (synthesis), plus capability
agents **KnowledgeAgent** (DB + web retrieval), **IngestionAgent** (Microsoft
Learn / PubMed -> KB), and **CoderAgent** (sandboxed compute). Tools are
registered in `src/agents/tools.py`. Capability agents run in-process (no Azure
Functions host for now).

---

## 6. Evaluation

Evals live in `eval/`. The suite mirrors the Foundry "idea to prototype"
evaluation model using the **`azure-ai-evaluation` SDK** and Foundry built-in
evaluators, run as cloud batch evals against the agent target:

- **Quality:** `builtin.fluency`, `builtin.coherence`, `builtin.relevance`,
  `builtin.groundedness` (1-5 scale). Groundedness/relevance matter most for a
  retrieval system - they catch unsupported claims.
- **Safety:** `builtin.violence`, plus self-harm / sexual / hate-unfairness
  (0-7 severity, lower safer); run via the Foundry adversarial simulator.
- **Task adherence:** `builtin.task_adherence` (1-5) - did each agent follow the
  manager's instruction; the key orchestration-health metric.
- **Summarization:** evaluate the SummaryAgent's final report with the quality
  evaluators above (relevance + groundedness + coherence) over a ground-truth
  set of research questions; track citation faithfulness.

Pattern (Python): build an `openai_client.evals` object with
`testing_criteria` of `type: azure_ai_evaluator`, run with an
`azure_ai_target_completions` data source pointed at the agent, poll
`evals.runs`, read pass/score/reason per item. Wire into CI for regression
gating. **(target)** - eval scaffolding to be added under `eval/`.

---

## 7. Monitoring

**(target - none today.)**

- **Tracing:** LangSmith (LangGraph-native, every node + tool span) + Azure
  Monitor / Application Insights via OpenTelemetry. Set `LANGSMITH_API_KEY`,
  `LANGSMITH_PROJECT`, `APPLICATIONINSIGHTS_CONNECTION_STRING`.
- **Data-tier metrics:** export PostgreSQL (Flexible Server) + Managed Redis +
  Cosmos + Databricks job metrics into App Insights / Azure Monitor; add alerts
  for pgvector query latency, Redis evictions/hit-rate, Cosmos RU throttling,
  and Databricks job failures.
- **Agent observability:** Foundry continuous evaluation + the agent dashboard
  for online quality/safety/task-adherence sampling on live runs.
- **Cost:** per-run token + RU accounting written to the Cosmos run record.

---

## 8. Commands

```bash
# Current (local)
cd /Users/robertjames/Documents/GitHub/agentic_research_team
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set OPENAI_API_KEY / GRAPHRAG_API_KEY
./scripts/run_pipeline.sh       # build corpus -> index -> summaries

# Query
python -m src.query.run_query --method global --community-level 0 \
    --query "Dominant themes in LLM-based clinical summarization?"

# Agents (current entrypoint)
python -c "import asyncio; from src.agents.biomedical_agents import run_research; \
    print(asyncio.run(run_research('Efficacy of LLM clinical note summarization in oncology?')).final_output)"
```

---

## 9. Environment variables

`.env` (gitignored), template in `.env.example`.

| Variable | Purpose | Status |
|---|---|---|
| `OPENAI_API_KEY` `GRAPHRAG_API_KEY` | OpenAI for Agents SDK + GraphRAG | current |
| `GRAPHRAG_ROOT` | indexed root for the graph tool (`data/graphrag`) | current |
| `SR_CSV_ROOT` | root of the SR CSV exports for `build_corpus` | current |
| `RESEARCH_MODEL` `SUPPORT_MODEL` | model overrides | current |
| `MANAGER_MODEL` `KNOWLEDGE_MODEL` `CODER_MODEL` | per-agent models (AGENTS.md) | target |
| `AZURE_POSTGRES_HOST` `AZURE_POSTGRES_DATABASE` `AZURE_POSTGRES_USER` | pgvector store | target |
| `AZURE_DOCDB_CONNECTION_STRING` `AZURE_DOCDB_DATABASE` | Cosmos for MongoDB vCore: JSON + history + run records (pymongo) | provisioned |
| `AZURE_REDIS_HOST` `AZURE_REDIS_PORT` | cache + working memory (AAD auth) | target |
| `AZURE_DATABRICKS_HOST` `AZURE_DATABRICKS_TOKEN` | dataset ETL + batch embeddings | target |
| `AZURE_OPENAI_ENDPOINT` `AZURE_OPENAI_EMB_DEPLOYMENT` | models + embeddings | target |
| `NOTION_API_KEY` `NOTION_DATABASE_ID` | blog-review Notion DB for `src/publish/notion_uploader.py` (Status = "Needs Review"; consumed by the blog-writer repo) | current |
| `MCP_SERVER_URL` | Microsoft Learn MCP (`https://learn.microsoft.com/api/mcp`) | target |
| `LANGSMITH_API_KEY` `LANGSMITH_PROJECT` `APPLICATIONINSIGHTS_CONNECTION_STRING` | tracing | target |

---

## 10. Conventions and gotchas

- **PubMed/Scopus exports lack abstracts; Embase/IEEE include them.** With
  `--require-abstract` you keep roughly the Embase + IEEE subset. GraphRAG
  quality collapses on title-only records.
- **GraphRAG community refresh is not automatic** - re-running the index is
  required after corpus changes.
- **Redis is ephemeral** - working memory + cache only; Cosmos is the durable
  source of truth for conversations and run records.
- **pgvector is primary here, secondary in the tutor repo** - do not copy the
  ranking across; check each repo's CLAUDE.md.
- **Default Claude pipeline model:** `claude-sonnet-4-20250514` (user memory).
- **No em dashes** - single hyphen `-` only.
