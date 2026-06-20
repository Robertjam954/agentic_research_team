# Gap register - what's missing

What the merged system needs versus what exists today. This is the "so we can see
what's missing" artifact. Status: **done** / **partial** / **missing**. Each gap
names the concrete artifact and the capability it blocks.

Legend for capabilities: **C1** research+summary, **C2** self-documenting+deploy,
**C3** content writer, **C4** evaluator, **C5** notes->Obsidian.

## Orchestration (C1)

| Artifact | Status | Notes |
|---|---|---|
| `src/agents/state.py` (`ResearchState`, `ProgressLedger`) | **missing** | Spec'd in AGENTS.md s.2. |
| `src/agents/graph.py` (LangGraph `StateGraph`, stall/replan, checkpointer) | **missing** | Spec'd in AGENTS.md s.2. |
| `src/agents/tools.py` (typed tool registry) | **missing** | 8+ tools spec'd in AGENTS.md s.4. |
| `research_pipeline` adapter tool wrapping `biomedical_agents.run_research` | **missing** | The ADR-0001 adapter boundary. |
| LangGraph + deepagents in `requirements.txt` | **missing** | `langgraph`, `deepagents`, `langgraph-cli`. |

## Retrieval (C1)

| Artifact | Status | Notes |
|---|---|---|
| `search_corpus_graph` (GraphRAG global/local) | **partial** | `src/agents/graphrag_tool.py` wraps GraphRAG; needs the two-tool split. |
| `search_corpus_semantic` (vector ANN) | **partial** | Today via GraphRAG `basic`/LanceDB; move to pgvector. |
| `web_search` | **partial** | Hosted web search in the pipeline; Azure path = Bing grounding tool. |
| `src/store/pgvector.py` (primary vector store) | **missing** | Replaces LanceDB; HNSW + `azure_ai` in-DB embeddings. |

## Summarization + evaluation (C1, C4)

| Artifact | Status | Notes |
|---|---|---|
| Structured Summarizer (schema'd, cited output) | **partial** | Pipeline summarizes; needs structured-output schema + citation normalizer. |
| Evaluator agent | **missing** | Summary quality, RAG citation faithfulness, safety. |
| `eval/` deep-eval harness (Foundry `azure-ai-evaluation`) | **missing** | Quality/safety/task-adherence + summarization; CI gate. |

## Self-documenting + deploy (C2)

| Artifact | Status | Notes |
|---|---|---|
| `docs/adr/` template + seed ADRs | **done** | This round. |
| Self-Documenting middleware (`git diff` -> ADR) | **missing** | Automates the CONTRIBUTING ADR step. |
| `src/store/cache.py` (Redis semantic cache) | **missing** | ADR 0002; threshold + TTL + metrics. |
| `infra/` azd + Bicep (AI project, models, Redis, Postgres, Blob, monitoring, Key Vault) | **missing** | One module per resource; `main.bicep` wires them. |
| Observability wiring (App Insights + OTel + LangSmith) | **missing** | Data-tier metrics + alerts; cache hit/miss; per-run cost. |
| Storage planning (sizing for index/Blob/Postgres/Redis) | **missing** | Capacity + cost estimate doc. |
| `.github/agents/{plan,tdd}.agent.md`, `docs/context-engineering-workflow.md` | **missing** | Copy from the deployment-tools repo as the new-project standard. |

## Content writer (C3)

| Artifact | Status | Notes |
|---|---|---|
| Content Writer agent (deepagents) | **missing** | Lift `create_deep_agent` + `interrupt_on` from `interrupt-resume-deep-agents`. |
| `src/agents/skills/{blog-post,linkedin-post}/SKILL.md` | **missing** | linkedin/twitter skills exist to copy in the source repo. |
| HITL review loop (`Command(resume=...)`) | **missing** | Approve/edit before publish. |

## Notes -> Obsidian (C5) - largely net-new

| Artifact | Status | Notes |
|---|---|---|
| Apple Notes / iPhone Notes export ingest | **missing** | No code anywhere; needs AppleScript/iCloud export path. |
| Blog post scraper | **missing** | httpx + readability/bs4 extraction. |
| YouTube transcript ingest | **partial** | Pattern exists in `zen-ai-engineer-tutor` (`youtube-transcript-api`); not in this repo. |
| Obsidian vault writer (markdown, frontmatter, `[[wikilinks]]`, backlinks) | **missing** | Conventions exist as prompt-only briefs in `local_agentic_content_extraction_blog_writer`; no code. |
| Note chunking + embedding into KB | **partial** | Chunking pattern liftable from `zen-ai-engineer-tutor`. |

## Cross-cutting / security

| Artifact | Status | Notes |
|---|---|---|
| Key Vault + `DefaultAzureCredential` wiring | **missing** | No plaintext secrets in image/repo. |
| Rotate shared Mongo/Azure credentials | **action** | Treat credentials shared during setup as compromised; rotate before deploy. |
