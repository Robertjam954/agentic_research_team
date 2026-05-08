# Biomedical Deep Research Agent Team

A multi-agent research pipeline for biomedical and clinical research, built on the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) and Deep Research API.

## Description

This project provides an automated research assistant tailored for biomedical and clinical domains. It orchestrates four specialised AI agents that collaboratively handle the full lifecycle of a research query — from disambiguation and scoping, through structured instruction-building, to web-scale evidence synthesis.

**Key capabilities:**

- **Intelligent triage** — automatically determines whether a query is specific enough to proceed, or routes it to clarification first.
- **PICO-guided clarification** — structures ambiguous queries using the Population, Intervention, Comparator, Outcome framework widely used in evidence-based medicine.
- **Structured research briefs** — converts enriched queries into precise instructions that improve the quality and reproducibility of the generated research.
- **Deep Research synthesis** — leverages OpenAI's `o3-deep-research` / `o4-mini-deep-research` models to search and synthesise web-scale biomedical literature, with streamed intermediate steps and citation extraction.

**Ideal use cases:** systematic literature reviews, clinical evidence summaries, drug/target mechanism analysis, and comparative effectiveness research.

## Architecture

Four specialized agents work in sequence:

```
User Query
    │
    ▼
┌─────────────────┐
│  Triage Agent   │  ← Decides if clarification is needed
└─────────────────┘
    │           │
    ▼           ▼
┌──────────┐  ┌─────────────────────┐
│Clarifier │  │  Instruction Agent  │
│  Agent   │  │  (skip if clear)    │
└──────────┘  └─────────────────────┘
    │               │
    └───────┬────────┘
            ▼
    ┌───────────────────────────────────┐
    │         Research Agent            │
    │  (o3-deep-research / WebSearch)   │
    └───────────────────────────────────┘
            │
            ▼
    Final Research Report
```

1. **Triage Agent** — Inspects the query; routes to Clarifier if context is missing, otherwise directly to Instruction Agent.
2. **Clarifying Agent** — Asks 2–3 focused follow-up questions using the PICO framework (Population, Intervention, Comparator, Outcome) to sharpen the query.
3. **Instruction Builder Agent** — Converts the enriched input into a precise, structured research brief.
4. **Research Agent** (`o3-deep-research`) — Performs web-scale empirical research, streams intermediate steps, and outputs a structured clinical report.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

### 3. Launch Jupyter

```bash
jupyter notebook biomedical_research_agents.ipynb
```

## Notebooks

| File | Description |
|------|-------------|
| `biomedical_research_agents.ipynb` | Full 4-agent biomedical research pipeline with streaming, citation extraction, and interaction flow |

## Model Notes

- **Default**: `o4-mini-deep-research-2025-06-26` — faster and cost-efficient, suitable for most queries
- **High-quality**: Switch to `o3-deep-research-2025-06-26` for complex systematic reviews or multi-step synthesis tasks

## Requirements

- Python 3.10+
- OpenAI API key with access to Deep Research models (`o3-deep-research`, `o4-mini-deep-research`)
