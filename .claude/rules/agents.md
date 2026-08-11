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
