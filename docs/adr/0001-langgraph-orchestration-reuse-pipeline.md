# ADR 0001: LangGraph orchestration, reuse the research pipeline as a tool

- **Status:** accepted
- **Date:** 2026-06-20
- **Deciders:** robertjames
- **Change reference:** doc round establishing the merged architecture (see `docs/plans/merge-content-and-deploy-plan.md`)

## Context

`agentic_research_team` has a working OpenAI Agents SDK research pipeline
(Triage -> Clarify -> Instruct -> Research) over a pre-built GraphRAG index. We
are merging in content-writing, notes-to-Obsidian, self-documenting, and
deployment capabilities. Three agent frameworks were candidates: OpenAI Agents
SDK (the pipeline), Microsoft Agent Framework (the Foundry/azd deploy shell), and
LangGraph + deepagents (content-writer skills, interrupt/resume HITL, and the
Magentic-style orchestration already specified in `AGENTS.md`). They deploy to
different runtimes and have different HITL/memory models.

## Decision

Standardize orchestration on **LangGraph + deepagents** and invoke the existing
research pipeline through a single `research_pipeline` tool (adapter pattern)
rather than porting or rewriting it. Models, storage, and deployment target
**Azure**; the code stays in `agentic_research_team`.

## Why

The system already gravitates to LangGraph (deepagents content writer, the
interrupt/resume repo, and the `AGENTS.md` Magentic-on-LangGraph spec). LangGraph
gives checkpointing, streaming, HITL interrupts, and memory for free. Wrapping the
proven pipeline as a tool keeps working retrieval/handoff logic intact while
unifying control flow on one runtime - the lowest-risk path to one coherent stack.

## Alternatives considered

- **Foundry-centric adapter on MS Agent Framework only** - rejected: would
  re-implement the deepagents HITL + skills we specifically want to reuse.
- **Full LangGraph port of the pipeline** - rejected for v1: highest rewrite
  cost, discards working handoff logic, and moves off Azure Foundry hosting.

## Consequences

- Positive: one orchestration runtime; content writer, HITL, memory, and research
  share infrastructure; retrieval is preserved.
- Negative / cost: two SDKs coexist (LangGraph outer, OpenAI Agents SDK inside the
  tool) until/unless a later native port; the adapter boundary must be kept thin.
- Follow-ups: build `src/agents/{state,graph,tools}.py` and the
  `research_pipeline` tool; see `docs/gaps.md`.
