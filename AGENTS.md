# AGENTS.md - Biomedical Deep-Research Multi-Agent System

Canonical specification of the agent team for `agentic_research_team`. Keep this
file truthful: if the code diverges, edit this file first, then the code.

This replaces the original linear pipeline (Triage -> Clarify -> Instruct ->
Research) in `src/agents/biomedical_agents.py` with a **Magentic-style
orchestration** (manager + ledgers + dynamic delegation) built on **LangGraph**.

The team now spans research, content writing, notes capture, and self-documentation
on one LangGraph spine. The proven research pipeline is **reused as a single
`research_pipeline` tool** rather than rewritten (see
[ADR 0001](docs/adr/0001-langgraph-orchestration-reuse-pipeline.md)). For product
scope and the full backlog see [`PRODUCT.md`](PRODUCT.md),
[`ARCHITECTURE.md`](ARCHITECTURE.md), [`docs/plans/merge-content-and-deploy-plan.md`](docs/plans/merge-content-and-deploy-plan.md),
and the [gap register](docs/gaps.md). Items not built yet are marked **(target)**.

- Pattern reference: Magentic / Magentic-One orchestration from AutoGen, as
  implemented in `~/loc/repos/agent-framework`
  (`python/packages/orchestrations/agent_framework_orchestrations/_magentic.py`,
  sample `python/samples/03-workflows/orchestrations/magentic.py`).
- Framework reference: LangGraph supervisor/deep-research pattern
  (https://towardsdatascience.com/langgraph-101-lets-build-a-deep-research-agent/).
- We adopt the Magentic *control loop* (task ledger + progress ledger +
  stall-based replanning) but implement it as an explicit **LangGraph
  `StateGraph`**, because LangGraph gives us checkpointing, streaming, and
  human-in-the-loop interrupts for free.

---

## 1. Team at a glance

Two layers: an **orchestration layer** that plans and routes, and a
**capability layer** that does the actual work via tools.

| Agent | Layer | Role | Primary tools | Default model | Status |
|---|---|---|---|---|---|
| **ManagerAgent** | Orchestration | Owns the control loop: maintains the progress ledger, decides `next_speaker`, issues the next instruction, detects stalls/loops, declares completion. | (none - reasons over ledgers) | `o3` / reasoning | spec |
| **ResearchAgent** | Orchestration | Analyzes the task and correlates known/unknown facts into the **task-ledger facts** sheet. Re-grounds facts after each replanning. | `search_corpus_semantic`, `search_corpus_graph` | `gpt-4o` | spec |
| **PlannerAgent** | Orchestration | Turns the facts + team roster into a concise bullet-point **plan**; produces a revised plan on replanning. | (none - reasons over facts) | `o3` / reasoning | spec |
| **SummaryAgent** (Summarizer) | Orchestration | Synthesizes the final, citation-grounded **structured** summary when the manager marks the request satisfied. | `cite` | `gpt-4o` | partial |
| **KnowledgeAgent** (Retriever) | Capability | Retrieves evidence from **both the database and the web**: pgvector ANN over the SR corpus, GraphRAG community/local search, and web search. Also fronts the `research_pipeline` adapter tool. | `search_corpus_semantic`, `search_corpus_graph`, `web_search`, `research_pipeline` | `gpt-4o-mini` | partial |
| **Content Writer** | Capability | Turns research/summaries into blog + LinkedIn content via deepagents **skills**; drafts gated by `interrupt_on` for human review before publish. | `skills/`, `write_file` (HITL) | `gpt-4o` | **(target)** |
| **Evaluator** | Capability | Scores summary quality, **RAG citation faithfulness**, and safety; drives the deep-eval harness. | eval tools (`azure-ai-evaluation`) | `gpt-4o` | **(target)** |
| **Notes / Ingestion** | Capability | Grows the KB and the notes graph: Microsoft Learn (MCP) + PubMed/Scopus into the corpus, and **Apple Notes / blogs / YouTube into an Obsidian vault** (wikilinks, frontmatter, backlinks). | `fetch_ms_learn`, `fetch_pubmed`, `fetch_blog`, `fetch_youtube`, `kb_upsert`, `obsidian_write` | `gpt-4o-mini` | **(target)** |
| **Self-Documenting** | Middleware | On an architectural change, turns `git diff` into an ADR; wraps LLM/retrieval calls in a Redis semantic cache. | `generate_adr`, `cache_get`/`cache_set` | `gpt-4o` | **(target)** |
| **CoderAgent** | Capability | Writes and executes Python in a sandbox for quantitative analysis, table/figure generation, and meta-analysis math. | `run_code` (code interpreter) | `gpt-4o` | spec |

Name mapping to the consolidated roster: **Orchestrator** = ManagerAgent +
PlannerAgent (detailed in s.3); **Retriever** = KnowledgeAgent; **Summarizer** =
SummaryAgent.

The roster is **declarative**: the manager is given each agent's `name` +
`description` (the "team block") and routes by name, exactly as Magentic's
`_team_block(participants)` does. Adding an agent = adding a row here + a node
in the graph + an entry in the participant registry.

---

## 2. Control loop (Magentic, on LangGraph)

State object (`src/agents/state.py`, `ResearchState` TypedDict):

```python
class ResearchState(TypedDict):
    task: str                       # original user request
    facts: str                      # task-ledger facts (ResearchAgent)
    plan: str                       # task-ledger plan (PlannerAgent)
    messages: list[AnyMessage]      # running transcript (LangGraph add_messages)
    progress: ProgressLedger        # see below; refreshed every round by ManagerAgent
    next_speaker: str               # capability agent name to run next
    round_count: int
    stall_count: int
    final_report: str | None
```

`ProgressLedger` mirrors `MagenticProgressLedger` exactly:
`is_request_satisfied`, `is_in_loop`, `is_progress_being_made`, `next_speaker`,
`instruction_or_question` (each = `{answer, reason}`).

Graph topology:

```
START
  -> research        (ResearchAgent: build facts)
  -> plan            (PlannerAgent: build plan)
  -> manager         (ManagerAgent: refresh progress ledger)
        |
        |  conditional edge on progress ledger:
        |   - is_request_satisfied        -> summary
        |   - stall_count >= MAX_STALLS    -> replan (reset chat, new facts+plan) -> manager
        |   - round_count >= MAX_ROUNDS    -> summary (best-effort)
        |   - else                         -> route to next_speaker
        v
  -> knowledge | ingestion | coder   (capability node runs, appends to messages)
        -> manager                    (loop back; round_count += 1)
  -> summary         (SummaryAgent: final_report) -> END
```

Loop rules (ported from `_magentic.py`):

- **Round budget:** `MAX_ROUNDS` (default 20) hard-stops the loop.
- **Stall detection:** if `is_progress_being_made.answer == False` or
  `is_in_loop.answer == True`, increment `stall_count`. At `MAX_STALLS`
  (default 3) the manager triggers a **replan**: `ResearchState` chat history is
  reset, ResearchAgent re-derives facts (with a "what went wrong" hint), and
  PlannerAgent produces a fresh plan. Task, round_count, and roster persist.
- **Completion:** when `is_request_satisfied.answer == True`, route to
  SummaryAgent.
- **Human-in-the-loop (optional):** a LangGraph `interrupt()` before the first
  capability round lets a human approve/edit the plan (mirrors the
  `magentic_human_plan_review.py` sample). Gate with `HITL_PLAN_REVIEW=true`.

Checkpointing: LangGraph checkpointer persists `ResearchState` per `thread_id`
so a run can resume. Durable snapshots of the task + progress ledgers are also
written to Cosmos (see CLAUDE.md data tier) for audit and eval replay.

---

## 3. Agents in detail

### ManagerAgent (orchestrator)
- **Input:** task, facts, plan, transcript.
- **Output:** refreshed `ProgressLedger` (strict JSON, parsed like Magentic's
  `_extract_json`), and on completion a go/no-go to SummaryAgent.
- **Behavior:** never calls tools or answers the user. Each round it answers the
  five ledger questions and names the single `next_speaker`. Owns stall/loop
  detection and replanning triggers.
- **Prompt:** `prompts/manager.system.md` (the five-question progress-ledger
  prompt + the team block).

### ResearchAgent (facts)
- **Input:** task (+ replanning hint on retry).
- **Output:** a facts sheet bucketed as: GIVEN facts, facts to LOOK UP, facts to
  DERIVE, EDUCATED GUESSES (mirrors Magentic's facts prompt).
- **Tools:** may call `search_sr_corpus` / `graph_search` to ground facts
  against the corpus before planning.
- **Prompt:** `prompts/research_facts.system.md`.

### PlannerAgent (plan)
- **Input:** facts + team roster.
- **Output:** short bullet-point plan assigning steps to capability agents by
  name. No prose, no next-steps until asked (matches Magentic plan prompt).
- **Prompt:** `prompts/planner.system.md`.

### SummaryAgent (synthesis)
- **Input:** full transcript + retrieved evidence.
- **Output:** final report with inline citations (`[study:PMID]`,
  `[community:Cxx]`, `[web:url]`), a limitations section, and a confidence note.
- **Tools:** `cite` for citation normalization.
- **Prompt:** `prompts/summary.system.md`.

### KnowledgeAgent (DB + web retrieval)
- **The point:** one agent, both sources. It decides per-instruction whether to
  hit the **database** (`search_sr_corpus` pgvector ANN, `graph_search`
  GraphRAG) or the **web** (`web_search`), or both, then returns a deduped,
  source-tagged evidence bundle.
- **Output:** evidence chunks with provenance + relevance scores; never final
  prose (the SummaryAgent owns synthesis).
- **Prompt:** `prompts/knowledge.system.md`.

### IngestionAgent (information extraction -> KB)
- **The point:** grows the knowledge base on demand. When the corpus lacks
  coverage, it fetches authoritative docs - **Microsoft Learn via the MCP
  server** (`https://learn.microsoft.com/api/mcp`) for method/tooling guidance,
  and PubMed/Scopus for biomedical evidence - extracts clean text, and upserts
  into the KB (corpus `.txt`, pgvector embeddings via `azure_ai`, and the
  GraphRAG input set for the next index).
- **Tools:** `fetch_ms_learn`, `fetch_pubmed`, `kb_upsert`.
- **Prompt:** `prompts/ingestion.system.md`.

### CoderAgent (compute)
- **The point:** quantitative work the LLM should not do in its head - effect
  sizes, forest-plot data, pooling, simple stats over retrieved tables.
- **Tools:** `run_code` (sandboxed Python / code interpreter). Returns results +
  any generated artifacts (paths in Blob).
- **Prompt:** `prompts/coder.system.md`.

### Content Writer (target)
- **The point:** turns a finished summary/report into publishable content (blog
  posts, LinkedIn) using deepagents **skills** (`skills/<format>/SKILL.md`).
  Reuses the patterns in `interrupt-resume-deep-agents` (`create_deep_agent`,
  `skills=[...]`).
- **HITL:** drafts are written behind `interrupt_on={"write_file": True}`; a human
  approves/edits via `Command(resume=...)` before anything is finalized.
- **Output:** markdown drafts under the run's workspace; never auto-publishes.
- **Prompt / skills:** `prompts/content_writer.system.md`,
  `src/agents/skills/{blog-post,linkedin-post}/SKILL.md`.

### Evaluator (target)
- **The point:** judges the team's output - summary quality, **RAG citation
  faithfulness** (does each claim trace to retrieved evidence), and safety - and
  drives the deep-eval harness in `eval/`.
- **Backed by:** Foundry `azure-ai-evaluation` builtins (quality, safety,
  task-adherence) plus a citation-faithfulness check over retrieved chunks.
- **Prompt:** `prompts/evaluator.system.md`. See `CLAUDE.md` "Evaluation".

### Notes / Ingestion (target)
- **The point:** the IngestionAgent expanded. Besides growing the KB from
  Microsoft Learn (MCP) and PubMed/Scopus, it captures personal sources -
  **Apple Notes, blog posts, and YouTube** - and writes them into an **Obsidian
  vault** as a linked graph (frontmatter, `[[wikilinks]]`, backlinks), following
  the conventions lifted from `local_agentic_content_extraction_blog_writer`.
- **Tools:** `fetch_ms_learn`, `fetch_pubmed`, `fetch_blog`, `fetch_youtube`,
  `kb_upsert`, `obsidian_write`.
- **Note:** Apple Notes export, blog scraping, and the Obsidian writer are
  net-new (see `docs/gaps.md`); YouTube chunking is liftable from
  `zen-ai-engineer-tutor`.
- **Prompt:** `prompts/ingestion.system.md`.

### Self-Documenting (target, middleware)
- **The point:** keeps the codebase explainable. On an architectural change it
  runs `git diff main`, evaluates the delta against `docs/adr/0000-template.md`,
  and writes a new ADR capturing the **why** (see ADR 0001/0002 for the format).
- **Caching:** wraps LLM and retrieval calls in a Redis **semantic cache**
  (embedding-similarity hit -> stored response), per
  [ADR 0002](docs/adr/0002-redis-semantic-caching.md).
- **Tools:** `generate_adr`, `cache_get`/`cache_set`.

---

## 4. Tool registry

Tools are defined once in `src/agents/tools.py` and bound to agents per the
table in section 1. Each tool is a typed LangGraph/LC `@tool`.

| Tool | Signature (logical) | Backed by | Used by |
|---|---|---|---|
| `search_corpus_semantic` | `(query, k=8, filters?) -> list[Chunk]` | **PostgreSQL pgvector** ANN (HNSW); query embedded via `azure_openai.create_embeddings` inside the DB | Retriever, Research |
| `search_corpus_graph` | `(query, method=global\|local\|drift, level=0..n) -> Summary` | **GraphRAG** community index (`src/graphrag`, `src/query/run_query.py`) | Retriever, Research |
| `web_search` | `(query) -> list[WebHit]` | Web search (Bing grounding on Azure) | Retriever |
| `research_pipeline` | `(query) -> Report` | Adapter over the existing OpenAI Agents SDK pipeline (`biomedical_agents.run_research`) | Retriever / Orchestrator |
| `fetch_ms_learn` | `(topic\|url) -> Doc` | **Microsoft Learn MCP** server | Notes/Ingestion |
| `fetch_pubmed` | `(query\|pmid) -> list[Record]` | PubMed E-utilities | Notes/Ingestion |
| `fetch_blog` | `(url) -> Doc` | blog scraper (httpx + readability) **(target)** | Notes/Ingestion |
| `fetch_youtube` | `(url\|id) -> Transcript` | `youtube-transcript-api` **(target)** | Notes/Ingestion |
| `kb_upsert` | `(docs) -> UpsertResult` | writes corpus `.txt` + pgvector rows + GraphRAG input | Notes/Ingestion |
| `obsidian_write` | `(note) -> Path` | Obsidian vault writer: frontmatter + `[[wikilinks]]` + backlinks **(target)** | Notes/Ingestion |
| `run_code` | `(code) -> ExecResult` | sandboxed Python (code interpreter) | Coder |
| `cite` | `(claims, evidence) -> list[Citation]` | citation normalizer | Summarizer |
| `generate_adr` | `(diff) -> AdrPath` | `git diff` -> ADR markdown from `docs/adr/0000-template.md` **(target)** | Self-Documenting |
| `cache_get` / `cache_set` | `(query) -> Hit?` / `(query, value)` | **Redis** semantic cache (embedding similarity) **(target)** | Self-Documenting |

**Hosting (per decision):** capability agents run **in-process** (LangGraph
nodes, plain Python tool modules) for now - no Azure Functions host. The tool
wrappers (`search_sr_corpus` over pgvector, `cache_*` over Redis, `cosmos_*`
over Cosmos) live under `src/agents/tools/` and `src/utils/`. Revisit Functions
only if a tool needs independent scaling.

---

## 5. Models, memory, and tracing

- **Models:** orchestration reasoning (Manager, Planner) defaults to a reasoning
  model (`o3`); content agents use `gpt-4o` / `gpt-4o-mini`. Override via
  `.env` (`MANAGER_MODEL`, `RESEARCH_MODEL`, `KNOWLEDGE_MODEL`, ...).
- **Working memory:** the live `ResearchState` (ledgers + transcript) is held in
  **Azure Managed Redis** during a run (fast, TTL'd) and checkpointed by
  LangGraph; durable run records + final reports persist to **Cosmos DB**.
- **Semantic cache:** `web_search` / `search_sr_corpus` results and LLM
  completions are cached in Redis keyed by embedding similarity.
- **Tracing:** every node + tool call is traced to **LangSmith** (LangGraph
  native) and **Azure Monitor / App Insights** via OpenTelemetry. See CLAUDE.md
  "Monitoring".

---

## 6. Evaluation hooks

Agents are evaluated with the same suite described in `CLAUDE.md` (Foundry
`azure-ai-evaluation`): quality (`builtin.fluency`, coherence, relevance,
groundedness), safety (`builtin.violence` and the other content categories),
**task adherence** (`builtin.task_adherence` - did the agent follow the
manager's instruction), and summarization quality on the SummaryAgent output.
Per-agent traces feed continuous evaluation in the Foundry project.

---

## 7. Build order

1. `src/agents/state.py` - `ResearchState` + `ProgressLedger`.
2. `src/agents/tools.py` - the 8 tools (start by porting `search_sr_corpus`
   from LanceDB to pgvector; wrap existing `run_query.py` as `graph_search`).
3. `prompts/*.system.md` - one per agent (facts/plan/manager/summary borrowed
   from `_magentic.py`).
4. `src/agents/graph.py` - the `StateGraph`: nodes, conditional edges, stall +
   replan logic, checkpointer.
5. Keep `biomedical_agents.py:run_research()` as the public entrypoint; have it
   invoke the new graph so existing callers/notebook keep working.
6. Wire LangSmith + OTel; add the eval hooks.
