---
paths:
  - "src/agents/**/*.py"
---

# Agent-layer rules

Applies to the runtime research team (see `AGENTS.md` for the canonical spec).
This is the adaptation of the path-scoped rules pattern to this project's agent code.

- **Orchestration is LangGraph + deepagents (ADR-0001).** The existing OpenAI Agents
  SDK pipeline is reused behind a single `research_pipeline` tool - do not port or
  rewrite it. New control flow, HITL, memory, and checkpointing live in the LangGraph
  layer (`src/agents/graph.py`, `state.py` - target).
- **Tools go in the typed registry** (`src/agents/tools.py` - target): a JSON input
  schema mapped to a handler. Give each agent only the tool subset it needs; document
  each tool's schema, auth, and timeout behavior. A tool must handle its own
  errors/timeouts and never crash the loop.
- **Report-back contract.** Worker agents return structured results to the
  manager/supervisor; do not let a worker mutate shared state directly outside the
  defined channel.
- **Bounded loops.** Every orchestration loop has an explicit step / recursion cap
  and a stall/replan path - no unbounded agent recursion.
- **Every claim carries a citation.** The summarizer's output is structured and
  grounded; unsupported claims are a defect.
- **Architectural change -> ADR.** Changing the agent roster, routing, tool
  boundaries, or a store choice requires an ADR before implementation (portfolio
  self-documenting protocol; `docs/adr/`, template `0000-template.md`). Use the
  `adr-writer` subagent to draft it from the diff.
- **Prompts stay reviewable.** Keep role prompts named and separate from control
  logic so they can be versioned and evaluated.

## LangGraph + deepagents components to include (target)

Grounded in the actual `langchain-ai/langgraph` primitives - use these names, do not
invent equivalents.

- **Graph API:** `StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`,
  `START` / `END`, `.compile(checkpointer=..., store=...)`. This is the spine in
  `src/agents/graph.py`.
- **State:** a typed graph state (`TypedDict` / `MessagesState`) with reducers; this
  is the `ResearchState` + `ProgressLedger` in `src/agents/state.py`.
- **Short-term memory / durable execution:** a **checkpointer** keyed by `thread_id`
  (`InMemorySaver` locally -> `PostgresSaver` / a Redis-backed saver in Azure). Maps
  to the CLAUDE.md data tier: Redis for live working memory, Cosmos for the durable
  run record.
- **Long-term memory:** the LangGraph **`Store`** (`BaseStore`) for cross-thread
  facts / retrieval, backed by pgvector.
- **Tools:** `@tool` functions + a `ToolNode`; the prebuilt `create_react_agent` for
  a worker where a plain ReAct loop suffices. `research_pipeline` is one such tool.
- **Multi-agent supervisor:** `langgraph-supervisor` (`create_supervisor`) or a custom
  supervisor node; workers hand control back with `Command(goto=..., update=...)`.
- **Human-in-the-loop:** `interrupt()` with `HumanInterrupt` / `HumanResponse`, resumed
  via `Command(resume=...)` - the review gate for the Content Writer (C3). The HITL
  surface is LangGraph Studio (`langgraph dev`), no bespoke frontend.
- **Streaming:** `graph.stream(...)` for incremental output.
- **deepagents:** `create_deep_agent` for planning (`write_todos`), sub-agent
  delegation, and skills under `src/agents/skills/<name>/SKILL.md`.
