---
name: Agentic Research Team
description: GraphRAG-backed biomedical deep-research stack that indexes a systematic-review corpus and exposes it to a multi-agent research pipeline.
languages:
- python
products:
- azure-cosmos-db
- azure-storage-accounts
page_type: sample
urlFragment: agentic-research-team
---
<!-- YAML front-matter schema: https://review.learn.microsoft.com/en-us/help/contribute/samples/process/onboarding?branch=main#supported-metadata-fields-for-readmemd -->

# Agentic Research Team

## Table of Contents

- [User story](#user-story)
  - [About this repo](#about-this-repo)
  - [When should you use this repo?](#when-should-you-use-this-repo)
  - [Key features](#key-features)
  - [Roadmap (target)](#roadmap-target)
  - [Target end users](#target-end-users)
  - [Industry scenario](#industry-scenario)
- [Architecture](#architecture)
  - [Outputs](#outputs)
- [Run](#run)
  - [Pre-requisites](#pre-requisites)
  - [Tools and libraries used](#tools-and-libraries-used)
  - [Required licenses](#required-licenses)
  - [Pricing considerations](#pricing-considerations)
  - [Run instructions](#run-instructions)
  - [Verifying the run](#verifying-the-run)
- [Automated self-documentation](#automated-self-documentation)
- [Supporting documentation](#supporting-documentation)
  - [Resource links](#resource-links)
  - [Licensing](#licensing)
- [Disclaimers](#disclaimers)

## User story

### About this repo

**agentic_research_team** is a GraphRAG-backed biomedical deep-research stack. It
builds a Microsoft GraphRAG index over a systematic-review corpus exported from
PubMed, Scopus, Embase, and IEEE Xplore, surfaces hierarchical community
summaries (leaf / intermediate / macro-root), and exposes that index to a
multi-agent research team.

- **Today:** local-first. OpenAI Agents SDK + Microsoft GraphRAG (LanceDB vector
  store) + a 4-agent linear pipeline (Triage -> Clarify -> Instruct -> Research)
  in `src/agents/biomedical_agents.py`, run end-to-end with
  `scripts/run_pipeline.sh`.
- **Target:** an Azure-hosted, Magentic-style multi-agent team on LangGraph
  (spec in [AGENTS.md](AGENTS.md)) backed by the managed Azure data tier in
  [CLAUDE.md](CLAUDE.md) section 4. Of that tier, only Azure Cosmos DB for
  MongoDB (vCore) and Azure Blob Storage are provisioned today
  (`src/store/docdb.py`, `src/store/blob.py`); everything else is (target).

This README is updated at the end of each working session and verified by the
automated Monday documentation workflow.

### When should you use this repo?

- You have a systematic-review corpus (database CSV exports) and want a
  knowledge-graph index with community-level thematic summaries over it.
- You want a working reference for wiring Microsoft GraphRAG as a tool into an
  OpenAI Agents SDK multi-agent pipeline.

### Key features

What each module does and what it produces:

- **`src/ingest/build_corpus.py`** - unifies the SR CSV exports (PubMed, Scopus,
  Embase block key-value format, IEEE), dedupes by DOI, and writes one `.txt`
  per study to `data/graphrag/input/` plus `data/processed/metadata.csv`.
- **`src/graphrag/run_index.py`** - stages the GraphRAG root
  (`src/graphrag/settings.yaml`), initializes prompts, and runs the Microsoft
  GraphRAG indexer. Output: `entities`, `relationships`, `communities`,
  `community_reports`, `text_units`, and `documents` parquet files under
  `data/graphrag/output/`.
- **`src/graphrag/extract_summaries.py`** - buckets community reports by Leiden
  `level` and writes `summaries_macro_root.md`, `summaries_intermediate.md`,
  `summaries_leaf.md`, plus a flat `summaries_index.csv` (default out-dir:
  `reports/community_summaries/`).
- **`src/query/run_query.py`** - CLI and library for global / local / drift /
  basic GraphRAG search; returns synthesized answers over the index.
- **`src/agents/biomedical_agents.py`** - the current 4-agent linear pipeline
  (Triage -> Clarify -> Instruct -> Research). The Research agent combines
  hosted web search with the local GraphRAG index (`src/agents/graphrag_tool.py`)
  and returns a research report as text (`run_research(...).final_output`).
- **`src/store/blob.py` and `src/store/docdb.py`** - helpers for the provisioned
  Azure Blob Storage account and Cosmos DB for MongoDB (vCore) cluster
  (artifacts and JSON documents / run records respectively).

### Roadmap (target)

Not built yet; specified in the prep docs and tracked in [TODO.md](TODO.md) /
[docs/gaps.md](docs/gaps.md):

- LangGraph Magentic-style agent team (`src/agents/{state,graph,tools}.py`).
- PostgreSQL + pgvector as the primary vector store, fed by Azure Databricks ETL.
- Azure Managed Redis cache + working memory; Cosmos Gremlin knowledge graph.
- Eval suite under `eval/` (azure-ai-evaluation, Foundry built-in evaluators).
- Monitoring: LangSmith tracing + Azure Monitor / Application Insights.

### Target end users

Per [PRODUCT.md](PRODUCT.md): clinical and biomedical researchers who need
grounded, cited answers over a curated systematic-review corpus, and AI
engineers extending the agent team.

### Industry scenario

Biomedical research: answering questions over a systematic-review corpus by
querying a knowledge graph of it rather than reading each abstract. This is a
portfolio/research project, not a clinical product.

## Architecture

```
CURRENT (local-first)

+---------------------+     +----------------------+     +------------------------+
| SR CSV exports      |     | src/ingest/          |     | Microsoft GraphRAG     |
| PubMed / Scopus /   |---->| build_corpus.py      |---->| indexer                |
| Embase / IEEE       |     | (dedupe by DOI)      |     | (src/graphrag/         |
| (data/raw/,         |     |                      |     |  run_index.py +        |
|  gitignored)        |     | one .txt per study   |     |  settings.yaml)        |
+---------------------+     | -> data/graphrag/    |     +-----------+------------+
                            |    input/            |                 |
                            | metadata.csv         |                 v
                            +----------------------+     +------------------------+
                                                          | data/graphrag/output/  |
                                                          | entities / relations / |
                                                          | communities / reports  |
                                                          | parquet  (+ LanceDB)   |
                                                          +-----+------------+-----+
                                                                |            |
                            +-----------------------------------+            |
                            v                                                v
              +---------------------------+              +---------------------------+
              | src/graphrag/             |              | src/query/run_query.py    |
              | extract_summaries.py      |              | global/local/drift/basic  |
              | summaries_{macro_root,    |              +-------------+-------------+
              |  intermediate,leaf}.md    |                            |
              +---------------------------+                            v
                                                          +---------------------------+
                                                          | src/agents/               |
                                                          | biomedical_agents.py      |
                                                          | Triage -> Clarify ->      |
                                                          | Instruct -> Research      |
                                                          | (web search + GraphRAG    |
                                                          |  tool) -> research answer |
                                                          +---------------------------+

TARGET LANE (Azure data tier - not built unless marked provisioned)

  Databricks ETL (target) -> PostgreSQL + pgvector (target, primary vectors)
  Azure Managed Redis (target, cache/working memory)
  Cosmos DB for MongoDB vCore (PROVISIONED, src/store/docdb.py - JSON docs,
    history, run records)
  Azure Blob Storage (PROVISIONED, src/store/blob.py - raw exports, artifacts)
  LangGraph Magentic team + Foundry evals + LangSmith/App Insights (target)
```

Walkthrough: CSV exports are unified into one text file per study, GraphRAG
extracts an entity/relationship graph and Leiden community hierarchy from them,
and the summaries script renders that hierarchy as three Markdown digests. The
same index answers ad-hoc queries through `run_query.py` and serves as a tool
for the 4-agent research pipeline. The Azure lane exists as provisioned storage
helpers today; everything else in it is (target).

### Outputs

| Artifact | Path |
|---|---|
| Per-study corpus text files | `data/graphrag/input/*.txt` (gitignored) |
| Corpus metadata | `data/processed/metadata.csv` (gitignored) |
| GraphRAG parquet index | `data/graphrag/output/{entities,relationships,communities,community_reports,text_units,documents}.parquet` (gitignored) |
| Community summaries | `reports/community_summaries/summaries_{macro_root,intermediate,leaf}.md` + `summaries_index.csv` |
| Query answers | stdout from `src/query/run_query.py` |
| Agent research report | return value of `run_research(...)` (text) |

Nothing under `data/` is ever committed.

## Run

### Pre-requisites

- Python 3 with `venv`.
- An OpenAI API key: set `OPENAI_API_KEY` and `GRAPHRAG_API_KEY` in `.env`
  (template: `.env.example`; names only here, never commit values).
- A local systematic-review CSV export tree, pointed to by `SR_CSV_ROOT`.

### Tools and libraries used

- `openai` + `openai-agents` (Agents SDK) - the 4-agent pipeline.
- `graphrag` (Microsoft) + `lancedb` + `pandas` + `pyarrow` - indexing and
  reading the index.
- `pymongo`, `azure-storage-blob`, `azure-identity` - the provisioned Azure
  data-tier helpers in `src/store/`.
- Full pin list: [requirements.txt](requirements.txt).

### Required licenses

None beyond an OpenAI API key. The provisioned Azure resources (Cosmos DB for
MongoDB vCore, Blob Storage) require an Azure subscription but are optional for
the local pipeline.

### Pricing considerations

- The pipeline itself runs locally at no cost, but **GraphRAG indexing is
  expensive in OpenAI API calls**: one LLM call per chunk for entity extraction
  plus per-community summarization. Start with a small symlinked subset in
  `data/graphrag/input/` before indexing the full corpus.
- The provisioned Azure Cosmos DB (vCore) cluster and Blob Storage account bill
  while they exist, independent of this pipeline.

### Run instructions

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set OPENAI_API_KEY / GRAPHRAG_API_KEY

# End to end: build corpus -> index -> summaries
./scripts/run_pipeline.sh
./scripts/run_pipeline.sh --skip-corpus   # if data/graphrag/input is already populated

# Query the index
python -m src.query.run_query --method global --community-level 0 \
    --query "Dominant themes in LLM-based clinical summarization?"

# Agent pipeline (current entrypoint)
python -c "import asyncio; from src.agents.biomedical_agents import run_research; \
    print(asyncio.run(run_research('Efficacy of LLM clinical note summarization in oncology?')).final_output)"
```

### Verifying the run

- `data/graphrag/output/` contains `entities.parquet`,
  `relationships.parquet`, `communities.parquet`,
  `community_reports.parquet`, `text_units.parquet`, and `documents.parquet`.
- `reports/community_summaries/` contains `summaries_macro_root.md`,
  `summaries_intermediate.md`, `summaries_leaf.md`, and `summaries_index.csv`.
- The query command prints a synthesized answer; the agent command prints a
  research report.

## Automated self-documentation

This repository keeps its own documentation current on a fixed loop:

- End of every working session: CLAUDE.md, this README, `requirements.txt`, and any affected prep docs are updated to match reality.
- Every Monday at 09:00 UTC: the GitHub Actions workflow [`update-claude-md.yml`](.github/workflows/update-claude-md.yml) runs Claude Code with the prompt in [`claude-md-review-prompt.md`](.github/workflows/claude-md-review-prompt.md). It verifies CLAUDE.md and this README against the code, checks `requirements.txt` against actual imports, regenerates the prioritized [TODO.md](TODO.md), and opens a pull request with any corrections. It can also be triggered manually from the Actions tab.
- The workflow requires the `CLAUDE_CODE_OAUTH_TOKEN` repository secret (generate with `claude setup-token`).

## Supporting documentation

### Resource links

- [PRODUCT.md](PRODUCT.md) - vision, capabilities (v1 vs roadmap), scope.
- [ARCHITECTURE.md](ARCHITECTURE.md) - target architecture + framework decision.
- [CONTRIBUTING.md](CONTRIBUTING.md) - setup, conventions, ADR requirement.
- [CLAUDE.md](CLAUDE.md) - operating manual (data tier, evals, ops).
- [AGENTS.md](AGENTS.md) - canonical agent-team spec.
- [TODO.md](TODO.md) - machine-refreshed weekly backlog.
- [docs/gaps.md](docs/gaps.md), [docs/adr/](docs/adr/),
  [docs/plans/merge-content-and-deploy-plan.md](docs/plans/merge-content-and-deploy-plan.md).
- External: [Microsoft GraphRAG](https://github.com/microsoft/graphrag),
  [OpenAI Agents SDK](https://github.com/openai/openai-agents-python).

### Licensing

No LICENSE file is committed to this repository yet; until one is added, all
rights are reserved by the author. Adding a license file is tracked work
(target).

## Disclaimers

This is sample/portfolio research code provided as-is, with no warranty. You are
responsible for any costs incurred by OpenAI API usage or Azure resources you
provision. The systematic-review corpus and all index artifacts live under
`data/` and are never committed; do not place PHI or otherwise sensitive data in
this repository.
