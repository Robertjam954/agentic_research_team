# Technical Specification - Agentic Research Team (Research Core)

**Scope of this document.** A buildable, end-to-end spec for the biomedical
deep-research system: the multi-agent research team and the research tools that
back it. It is the implementation contract a developer can build the application
from without further design work.

**Explicitly out of scope (excluded by request).** Content writing
(blog / LinkedIn / Twitter / social), personal-notes capture (Apple Notes, blog
scraping, YouTube transcripts), and the Obsidian vault writer. The
`Content Writer` and the notes side of `Notes / Ingestion` are **not** built
here, and the tools `fetch_blog`, `fetch_youtube`, and `obsidian_write` are
**not** included. Research-corpus ingestion (PubMed / Scopus / Microsoft Learn
-> KB) **is** in scope because it grows the evidence base.

This spec reconciles and supersedes, for the research core only, the relevant
parts of `AGENTS.md`, `ARCHITECTURE.md`, `PRODUCT.md`, and `CLAUDE.md`. Where it
says **(target)** the capability is not built yet; everything else either exists
in the repo today or is a thin wrapper over what exists.

---

## 1. Goal and success criteria

Build a biomedical deep-research system that, given a clinical research question,
retrieves evidence from three sources (GraphRAG community reasoning, vector ANN
over a systematic-review corpus, and live web), reasons over it with a
Magentic-style multi-agent team, and returns a **citation-grounded structured
summary**.

Success criteria:

1. A researcher asks a biomedical question and receives a structured, cited
   summary that combines graph + semantic + web evidence, with every claim
   traceable to a source (`[study:PMID]`, `[community:Cxx]`, `[web:url]`).
2. The team plans, delegates, detects stalls, and replans without human
   babysitting; an optional human-in-the-loop gate can approve the plan.
3. When the corpus lacks coverage, the system can fetch authoritative evidence
   (PubMed / Scopus / Microsoft Learn) and upsert it into the KB.
4. Runs are durable (Cosmos run records), reproducible, and traced.

---

## 2. System architecture

```
Client / CLI / API
   |
   v
LangGraph Orchestrator (StateGraph + checkpointer + optional HITL interrupt)
   |  Magentic control loop: task ledger (facts + plan) + progress ledger + stall/replan
   |
   |-- Orchestration nodes:  ResearchAgent(facts) -> PlannerAgent(plan) -> ManagerAgent(route)
   |-- Capability nodes:      KnowledgeAgent | IngestionAgent | CoderAgent
   |-- Terminal node:         SummaryAgent (citation-grounded structured report)
   |-- Optional:              Evaluator (quality / citation faithfulness / safety)  (target)
   |
   |-- tool: research_pipeline(query) -> existing OpenAI Agents SDK pipeline
   |          (Triage -> Clarify -> Instruct -> Research)
   |
   v
Retrieval tools:  search_corpus_graph (GraphRAG)  |  search_corpus_semantic (pgvector)  |  web_search
KB-growth tools:  fetch_ms_learn (MCP) | fetch_pubmed | kb_upsert
Compute:          run_code (sandbox)        Citation: cite        Cache: cache_get/set (target)
   |
   v
Storage tier:
   PostgreSQL + pgvector   - primary vector store, corpus-chunk embeddings    (target; LanceDB today)
   GraphRAG index          - community/local reasoning (parquet + LanceDB)     (current, local)
   Cosmos for MongoDB vCore- run records, conversation history, study JSON     (provisioned)
   Azure Blob Storage      - artifacts (figures/tables, GraphRAG outputs)      (provisioned)
   Azure Managed Redis     - semantic cache + working memory                   (target)
   |
   v
Models: Azure OpenAI / Foundry   |   Observability: LangSmith + App Insights (OTel)   |   Deploy: azd + Bicep
```

**Core architectural decision (ADR 0001).** Standardize orchestration on
**LangGraph + deepagents** and **reuse the existing 4-agent research pipeline as
a single `research_pipeline` tool** (adapter pattern) rather than rewriting it.
This unifies control flow, HITL, memory, and checkpointing on one runtime while
preserving proven retrieval handoff logic.

---

## 3. Agent team

Two layers: an **orchestration layer** that plans and routes, and a
**capability layer** that does the work via tools. The roster is declarative:
the Manager is given each agent's `name` + `description` (the "team block") and
routes by name (Magentic `_team_block(participants)` pattern). Adding an agent =
add a row here + a graph node + a registry entry.

| Agent | Layer | Role | Primary tools | Default model | Status |
|---|---|---|---|---|---|
| **ManagerAgent** | Orchestration | Owns the control loop: refresh progress ledger, pick `next_speaker`, issue next instruction, detect stalls/loops, declare completion. Never calls tools or answers the user. | (none) | `o3` / reasoning | spec |
| **ResearchAgent** | Orchestration | Builds the task-ledger **facts** sheet (GIVEN / LOOK UP / DERIVE / GUESS). May ground facts against the corpus. Re-grounds on replan. | `search_corpus_semantic`, `search_corpus_graph` | `gpt-4o` | spec |
| **PlannerAgent** | Orchestration | Turns facts + roster into a concise bullet plan assigning steps to capability agents by name. | (none) | `o3` / reasoning | spec |
| **SummaryAgent** | Orchestration | Synthesizes the final citation-grounded structured report when the Manager marks the request satisfied. | `cite` | `gpt-4o` | partial |
| **KnowledgeAgent** | Capability | Retrieves evidence from DB **and** web: pgvector ANN, GraphRAG community/local, web search. Fronts the `research_pipeline` adapter. Returns deduped, source-tagged evidence; never final prose. | `search_corpus_semantic`, `search_corpus_graph`, `web_search`, `research_pipeline` | `gpt-4o-mini` | partial |
| **IngestionAgent** | Capability | Grows the KB on demand when the corpus lacks coverage: fetch authoritative docs (Microsoft Learn MCP, PubMed/Scopus), extract clean text, upsert to corpus `.txt` + pgvector + GraphRAG input. **(Research ingestion only - no personal notes / Obsidian.)** | `fetch_ms_learn`, `fetch_pubmed`, `kb_upsert` | `gpt-4o-mini` | (target) |
| **CoderAgent** | Capability | Sandboxed Python for quantitative work the LLM should not do in its head: effect sizes, forest-plot data, pooling, simple stats over retrieved tables. Returns results + artifact paths in Blob. | `run_code` | `gpt-4o` | spec |
| **Evaluator** | Capability | Scores summary quality, RAG citation faithfulness, and safety; drives the eval harness. | eval tools (`azure-ai-evaluation`) | `gpt-4o` | (target) |

Name mapping to the consolidated roster: **Orchestrator** = ManagerAgent +
PlannerAgent; **Retriever** = KnowledgeAgent; **Summarizer** = SummaryAgent.

### 3.1 Agent contracts

- **ManagerAgent** - in: task, facts, plan, transcript. out: refreshed
  `ProgressLedger` (strict JSON, parsed like Magentic's `_extract_json`) and a
  go/no-go to Summary. Prompt: `prompts/manager.system.md` (five-question
  progress-ledger prompt + team block).
- **ResearchAgent** - in: task (+ replan hint on retry). out: facts bucketed as
  GIVEN / LOOK UP / DERIVE / EDUCATED GUESS. Prompt: `prompts/research_facts.system.md`.
- **PlannerAgent** - in: facts + roster. out: short bullet plan, no prose.
  Prompt: `prompts/planner.system.md`.
- **SummaryAgent** - in: full transcript + retrieved evidence. out: final report
  with inline citations, a limitations section, and a confidence note. Tool:
  `cite`. Prompt: `prompts/summary.system.md`.
- **KnowledgeAgent** - decides per instruction whether to hit the DB
  (`search_corpus_semantic`, `search_corpus_graph`), the web (`web_search`), or
  both, then returns evidence chunks with provenance + relevance scores. Prompt:
  `prompts/knowledge.system.md`.
- **IngestionAgent** - tools `fetch_ms_learn`, `fetch_pubmed`, `kb_upsert`.
  Prompt: `prompts/ingestion.system.md`.
- **CoderAgent** - tool `run_code`. Prompt: `prompts/coder.system.md`.
- **Evaluator** (target) - Foundry `azure-ai-evaluation` builtins +
  citation-faithfulness check over retrieved chunks. Prompt:
  `prompts/evaluator.system.md`.

---

## 4. Control loop (Magentic, on LangGraph)

### 4.1 State

`src/agents/state.py`:

```python
class ProgressLedger(TypedDict):     # mirrors MagenticProgressLedger
    is_request_satisfied: dict       # {answer: bool, reason: str}
    is_in_loop: dict
    is_progress_being_made: dict
    next_speaker: dict               # {answer: agent_name, reason: str}
    instruction_or_question: dict    # {answer: str, reason: str}

class ResearchState(TypedDict):
    task: str                        # original user request
    facts: str                       # task-ledger facts (ResearchAgent)
    plan: str                        # task-ledger plan (PlannerAgent)
    messages: list[AnyMessage]       # running transcript (add_messages)
    progress: ProgressLedger         # refreshed every round by ManagerAgent
    next_speaker: str                # capability agent to run next
    round_count: int
    stall_count: int
    final_report: str | None
```

### 4.2 Graph topology

```
START
  -> research        (ResearchAgent: build facts)
  -> plan            (PlannerAgent: build plan)
  -> manager         (ManagerAgent: refresh progress ledger)
        |
        |  conditional edge on the progress ledger:
        |    is_request_satisfied            -> summary
        |    stall_count >= MAX_STALLS       -> replan (reset chat, new facts+plan) -> manager
        |    round_count >= MAX_ROUNDS       -> summary (best-effort)
        |    else                            -> route to next_speaker
        v
  -> knowledge | ingestion | coder   (capability node runs, appends to messages)
        -> manager                    (loop back; round_count += 1)
  -> summary         (SummaryAgent: final_report) -> END
```

### 4.3 Loop rules (ported from Magentic `_magentic.py`)

- **Round budget:** `MAX_ROUNDS` (default 20) hard-stops the loop.
- **Stall detection:** if `is_progress_being_made.answer == False` or
  `is_in_loop.answer == True`, increment `stall_count`. At `MAX_STALLS`
  (default 3) trigger a **replan**: reset the chat history, ResearchAgent
  re-derives facts with a "what went wrong" hint, PlannerAgent produces a fresh
  plan. `task`, `round_count`, and roster persist.
- **Completion:** `is_request_satisfied.answer == True` routes to SummaryAgent.
- **Human-in-the-loop (optional):** a LangGraph `interrupt()` before the first
  capability round lets a human approve/edit the plan. Gate with
  `HITL_PLAN_REVIEW=true`.

### 4.4 Persistence

A LangGraph checkpointer persists `ResearchState` per `thread_id` so a run can
resume. Durable snapshots of the task + progress ledgers also write to Cosmos
for audit and eval replay (see section 7).

---

## 5. Tool registry

Tools are defined once in `src/agents/tools.py` and bound to agents per the
table in section 3. Each is a typed LangGraph/LC `@tool`. **Only the research
and KB-growth tools are in scope** - the notes/Obsidian tools are excluded.

| Tool | Signature (logical) | Backed by | Used by | Status |
|---|---|---|---|---|
| `search_corpus_semantic` | `(query, k=8, filters?) -> list[Chunk]` | PostgreSQL pgvector ANN (HNSW); query embedded via `azure_openai.create_embeddings` in-DB | Knowledge, Research | target (LanceDB today) |
| `search_corpus_graph` | `(query, method=global\|local\|drift\|basic, level=0..n) -> Summary` | GraphRAG community index (`src/query/run_query.py`) | Knowledge, Research | current |
| `web_search` | `(query) -> list[WebHit]` | Web search (Bing grounding on Azure; Tavily acceptable locally) | Knowledge | partial |
| `research_pipeline` | `(query) -> Report` | Adapter over `biomedical_agents.run_research` (OpenAI Agents SDK) | Knowledge / Orchestrator | current |
| `fetch_ms_learn` | `(topic\|url) -> Doc` | Microsoft Learn MCP server (`https://learn.microsoft.com/api/mcp`) | Ingestion | target |
| `fetch_pubmed` | `(query\|pmid) -> list[Record]` | PubMed E-utilities | Ingestion | target |
| `kb_upsert` | `(docs) -> UpsertResult` | writes corpus `.txt` + pgvector rows + GraphRAG input set | Ingestion | target |
| `run_code` | `(code) -> ExecResult` | sandboxed Python / code interpreter | Coder | spec |
| `cite` | `(claims, evidence) -> list[Citation]` | citation normalizer | Summary | partial |
| `cache_get` / `cache_set` | `(query) -> Hit?` / `(query, value)` | Redis semantic cache (embedding similarity) | middleware | target |

**Excluded tools (do not implement):** `fetch_blog`, `fetch_youtube`,
`obsidian_write`, and any blog/LinkedIn/Twitter publishing tool.

**Hosting:** capability agents run **in-process** (LangGraph nodes + plain
Python tool modules). No Azure Functions host. Tool wrappers live under
`src/agents/tools/` and `src/store/` (`pgvector.py`, `cache.py`, `docdb.py`).
Revisit Functions only if a tool needs independent scaling.

### 5.1 Today's retrieval (what exists)

`src/agents/graphrag_tool.py` exposes `search_sr_corpus(question, method,
community_level)` as an OpenAI Agents SDK `@function_tool` over the local
GraphRAG index (methods: global / local / drift / basic). The LangGraph
`search_corpus_graph` wraps this same `src/query/run_query.py:query()`. Port
`search_corpus_semantic` from LanceDB to pgvector per the data-tier plan.

---

## 6. Data and storage tier

Authoritative store-per-concern mapping (canonical copy in `CLAUDE.md`). Add a
feature's data to the store named here; do not stand up a parallel store for the
same concern.

| Concern | Store / service | Owns | Status |
|---|---|---|---|
| **Primary vector store** | Azure DB for PostgreSQL Flexible Server (`pgvector` + `azure_ai`) | study-chunk embeddings (`vector` column, HNSW), ANN retrieval for `search_corpus_semantic`; query-time embeddings via `azure_openai.create_embeddings` in-DB | target (replaces LanceDB) |
| **Knowledge graph / community index** | GraphRAG parquet (+ LanceDB) | entities / relationships / communities / community_reports; community + local reasoning | current |
| **Documents + history + run records** | Cosmos DB for MongoDB vCore (`docdb-cluster-20260619-0425`, norwayeast, M30 HA) | study metadata JSON, extracted entities, community summaries, conversation history, agent run records (task + progress ledger snapshots) | provisioned (`src/store/docdb.py`, pymongo) |
| **Dataset ETL + batch embedding** | Azure Databricks | SR CSV exports -> unified Delta tables; dedupe; batch-embed chunks; write vectors to pgvector | target (replaces local `build_corpus.py` at scale) |
| **Cache + working memory** | Azure Managed Redis | semantic / LLM-response cache, live `ResearchState` working memory, app cache (TTL'd; never source of truth) | target |
| **Files / artifacts** | Azure Blob Storage | raw exports, CoderAgent figures/tables, GraphRAG outputs | provisioned (`src/store/blob.py`) |
| **Embedding producer** | Azure OpenAI `text-embedding-3-large` | text vectors written to pgvector | target |

Notes: pgvector is **primary here** by design (Databricks is the natural feeder,
workload is relational + analytical). GraphRAG is a retrieval *method*, not a
store choice; its community index complements pgvector ANN. Cosmos is the
**Mongo wire protocol** offering - connect with `pymongo`, not the
`azure-cosmos` SDK; all writes are best-effort no-ops without
`AZURE_DOCDB_CONNECTION_STRING` so local runs keep working.

---

## 7. Corpus -> index -> agents pipeline

The serving path mounts an existing GraphRAG index (no re-index in the request
path). Index build is offline and expensive (one LLM call per chunk for entity
extraction + per-community summarization).

1. **Build corpus** - `python -m src.ingest.build_corpus --csv-root "$SR_CSV_ROOT"
   --out-dir data/graphrag/input --meta-csv data/processed/metadata.csv
   --require-abstract`. Unifies PubMed / Scopus / Embase / IEEE exports (Embase
   is a block key-value format; the rest are standard CSV), dedupes by DOI,
   writes one `.txt` per study. `--require-abstract` drops abstract-less records
   (GraphRAG quality collapses on title-only records; PubMed/Scopus often lack
   abstracts, so this keeps roughly the Embase + IEEE subset).
2. **Index** - `python -m src.graphrag.run_index --root data/graphrag` produces
   `entities / relationships / communities / community_reports / text_units /
   documents` parquet under `data/graphrag/output/`.
3. **Summaries** - `python -m src.graphrag.extract_summaries` buckets community
   reports by Leiden `level` into `summaries_{macro_root,intermediate,leaf}.md`.
4. **Query / agents** - `src/query/run_query.py` (global/local/drift/basic) and
   the agent team in `src/agents/`.

GraphRAG community refresh is **not** automatic - re-run the index after corpus
changes. Start with a symlinked subset in `data/graphrag/input/`.

---

## 8. Evaluation (target)

Evals live in `eval/`, mirroring the Foundry "idea to prototype" model using the
**`azure-ai-evaluation` SDK** and built-in evaluators, run as cloud batch evals
against the agent target:

- **Quality:** `builtin.fluency`, `builtin.coherence`, `builtin.relevance`,
  `builtin.groundedness` (1-5). Groundedness/relevance matter most - they catch
  unsupported claims.
- **Safety:** `builtin.violence` plus self-harm / sexual / hate-unfairness
  (0-7 severity, lower safer) via the Foundry adversarial simulator.
- **Task adherence:** `builtin.task_adherence` (1-5) - did each agent follow the
  Manager's instruction (the key orchestration-health metric).
- **Summarization:** evaluate the SummaryAgent report with the quality
  evaluators over a ground-truth question set; track citation faithfulness
  (does each claim trace to a retrieved chunk).

Pattern: build `openai_client.evals` with `testing_criteria` of
`type: azure_ai_evaluator`, run with `azure_ai_target_completions` pointed at
the agent, poll `evals.runs`, read pass/score/reason per item. Wire into CI for
regression gating.

---

## 9. Monitoring (target)

- **Tracing:** LangSmith (LangGraph-native, every node + tool span) + Azure
  Monitor / App Insights via OpenTelemetry. Env: `LANGSMITH_API_KEY`,
  `LANGSMITH_PROJECT`, `APPLICATIONINSIGHTS_CONNECTION_STRING`.
- **Data-tier metrics:** export Postgres + Redis + Cosmos + Databricks metrics
  into App Insights; alert on pgvector query latency, Redis evictions/hit-rate,
  Cosmos RU throttling, Databricks job failures.
- **Cost:** per-run token accounting written to the Cosmos run record.

---

## 10. Models, config, security

- **Models:** orchestration reasoning (Manager, Planner) defaults to a reasoning
  model (`o3`); capability agents use `gpt-4o` / `gpt-4o-mini`. Today's pipeline
  defaults: `RESEARCH_MODEL=o4-mini-deep-research-2025-06-26`,
  `SUPPORT_MODEL=gpt-4o-mini`. Override per agent via `.env` (`MANAGER_MODEL`,
  `RESEARCH_MODEL`, `KNOWLEDGE_MODEL`, `CODER_MODEL`, ...).
- **Config:** env vars only, no hard-coded endpoints/models/keys; new config is
  documented in `.env.example`.
- **Credentials:** `DefaultAzureCredential` + Key Vault for deployed hosts; no
  plaintext secrets in the image or repo. Connection strings come from env /
  Key Vault.

### 10.1 Environment variables

| Variable | Purpose | Status |
|---|---|---|
| `OPENAI_API_KEY` `GRAPHRAG_API_KEY` | OpenAI for Agents SDK + GraphRAG | current |
| `GRAPHRAG_ROOT` | indexed root for the graph tool (`data/graphrag`) | current |
| `SR_CSV_ROOT` | root of the SR CSV exports for `build_corpus` | current |
| `RESEARCH_MODEL` `SUPPORT_MODEL` | model overrides (current pipeline) | current |
| `MANAGER_MODEL` `KNOWLEDGE_MODEL` `CODER_MODEL` | per-agent models | target |
| `HITL_PLAN_REVIEW` | gate the optional plan-review interrupt | target |
| `AZURE_POSTGRES_HOST` `AZURE_POSTGRES_DATABASE` `AZURE_POSTGRES_USER` | pgvector store | target |
| `AZURE_DOCDB_CONNECTION_STRING` `AZURE_DOCDB_DATABASE` | Cosmos for MongoDB vCore (pymongo) | provisioned |
| `AZURE_STORAGE_CONNECTION_STRING` `AZURE_STORAGE_ACCOUNT` `AZURE_STORAGE_CONTAINER` | Blob artifacts | provisioned |
| `AZURE_REDIS_HOST` `AZURE_REDIS_PORT` | cache + working memory (AAD auth) | target |
| `AZURE_OPENAI_ENDPOINT` `AZURE_OPENAI_EMB_DEPLOYMENT` | models + embeddings | target |
| `MCP_SERVER_URL` | Microsoft Learn MCP (`https://learn.microsoft.com/api/mcp`) | target |
| `LANGSMITH_API_KEY` `LANGSMITH_PROJECT` `APPLICATIONINSIGHTS_CONNECTION_STRING` | tracing | target |

---

## 11. Repository layout

```
src/
  ingest/build_corpus.py        unify CSVs -> per-study txt + metadata        (current)
  graphrag/
    settings.yaml               canonical GraphRAG config                     (current)
    run_index.py                stage root, init prompts, run indexer         (current)
    extract_summaries.py        bucket communities into leaf/intermediate/root(current)
  query/run_query.py            global/local/drift/basic search CLI + lib     (current)
  agents/
    biomedical_agents.py        4-agent pipeline; stays the public entrypoint (current)
    graphrag_tool.py            search_sr_corpus over GraphRAG                 (current)
    state.py                    ResearchState + ProgressLedger                (target)
    graph.py                    LangGraph StateGraph (Magentic loop)          (target)
    tools.py                    typed tool registry                           (target)
    tools/                      pgvector, web_search, research_pipeline, ...   (target)
  store/
    docdb.py                    Cosmos for MongoDB vCore                       (current)
    blob.py                     Azure Blob Storage                            (current)
    pgvector.py  cache.py       pgvector store; Redis semantic cache          (target)
prompts/      one *.system.md per agent (manager/research_facts/planner/summary/knowledge/ingestion/coder) (target)
eval/         azure-ai-evaluation harness                                    (target)
infra/        azd + Bicep: AI project, models, storage, Redis, Postgres, monitoring (target)
scripts/run_pipeline.sh         build corpus -> index -> summaries            (current)
```

---

## 12. Build order

1. `src/agents/state.py` - `ResearchState` + `ProgressLedger`.
2. `src/agents/tools.py` + `src/agents/tools/` - the in-scope tools. Start by
   porting `search_sr_corpus` from LanceDB to pgvector (`search_corpus_semantic`)
   and wrapping `run_query.py` as `search_corpus_graph`; add `web_search`,
   `research_pipeline` (adapter over `biomedical_agents.run_research`),
   `fetch_ms_learn`, `fetch_pubmed`, `kb_upsert`, `run_code`, `cite`.
3. `prompts/*.system.md` - one per agent (facts / plan / manager / summary
   borrowed from Magentic `_magentic.py`; knowledge / ingestion / coder new).
4. `src/agents/graph.py` - the `StateGraph`: nodes, conditional edges, stall +
   replan logic, checkpointer, optional HITL interrupt.
5. Keep `biomedical_agents.py:run_research()` as the public entrypoint; have it
   invoke the new graph so existing callers and the notebook keep working.
6. Wire LangSmith + OTel tracing and the Cosmos run-record writes; add the eval
   hooks in `eval/`.
7. `infra/` azd + Bicep for the Azure footprint (Postgres, Redis, Blob, Cosmos,
   models, monitoring); deploy with `azd provision` + `azd deploy`.

---

## 13. Non-goals

- No front-end UI; no end-user authentication (the host trusts the runtime).
- No GraphRAG re-index in the serving path (mount the existing index).
- No second vector store for the same concern - follow the section 6 data tier.
- **No content writer, social publishing, personal-notes capture, or Obsidian
  vault** - explicitly excluded from this build.
