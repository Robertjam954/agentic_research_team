# Agentic Research Team

GraphRAG-backed biomedical research stack. Builds a Microsoft GraphRAG index
over the systematic-review corpus exported from PubMed, Scopus, Embase, and
IEEE Xplore, surfaces hierarchical community summaries at the **leaf**,
**intermediate**, and **macro-root** levels, and exposes the index as a tool
for a four-agent OpenAI Agents SDK pipeline (Triage -> Clarify -> Instruct
-> Research).

## Project layout

```
agentic_research_team/
  data/
    raw/                 source CSV exports (gitignored)
    processed/           metadata.csv produced by build_corpus
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
      graphrag_tool.py            GraphRAG-as-tool wrapper
      biomedical_agents.py        four-agent pipeline (refactored from notebook)
  notebooks/
    biomedical_research_agents.ipynb
  prompts/    docs/    eval/    experiments/    reports/    search/
  scripts/run_pipeline.sh
  requirements.txt    .env.example    .gitignore
```

## One-time setup

```bash
cd /Users/robertjames/Documents/GitHub/agentic_research_team
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then edit OPENAI_API_KEY / GRAPHRAG_API_KEY
```

## End-to-end run

```bash
./scripts/run_pipeline.sh
```

That script does three things:

1. **Build corpus**
   ```bash
   python -m src.ingest.build_corpus \
       --csv-root "$SR_CSV_ROOT" \
       --out-dir data/graphrag/input \
       --meta-csv data/processed/metadata.csv \
       --require-abstract
   ```
   Parses each database's quirks (PubMed and Scopus are standard CSV;
   Embase is a key-value block format; IEEE is standard CSV with abstracts),
   deduplicates by DOI, and writes one `.txt` per study with a header plus
   abstract. `--require-abstract` drops records that have no abstract since
   GraphRAG quality collapses without text content.

2. **Index with GraphRAG**
   ```bash
   python -m src.graphrag.run_index --root data/graphrag
   ```
   Copies `src/graphrag/settings.yaml` into the project root, runs
   `graphrag init` (once, to materialise the prompt templates), then
   `graphrag index`. Produces `entities.parquet`, `relationships.parquet`,
   `communities.parquet`, `community_reports.parquet`, `text_units.parquet`,
   and `documents.parquet` under `data/graphrag/output/`.

3. **Extract hierarchical summaries**
   ```bash
   python -m src.graphrag.extract_summaries \
       --root data/graphrag \
       --out-dir reports/community_summaries
   ```
   Reads `community_reports.parquet`, buckets every report by its Leiden
   `level` column, and writes three Markdown files:
   - `summaries_macro_root.md`   level 0, broadest themes across the corpus
   - `summaries_intermediate.md` median present level
   - `summaries_leaf.md`         max level, most specific sub-topics
   Plus a flat `summaries_index.csv` for downstream tooling.

## Querying

```bash
# Global search (community-level synthesis)
python -m src.query.run_query --method global --community-level 0 \
    --query "What are the dominant themes in LLM-based clinical summarization?"

python -m src.query.run_query --method global --community-level 2 \
    --query "Which prompt-engineering strategies reduce hallucination?"

# Local search (specific entities/papers)
python -m src.query.run_query --method local \
    --query "Studies that fine-tuned BioBERT on oncology notes"
```

`community_level` controls the Leiden cut: `0` is the macro root (broadest),
larger numbers descend toward leaf communities (most specific).

## Biomedical agent pipeline

The four-agent pipeline (Triage -> Clarify -> Instruct -> Research) lives in
`src/agents/biomedical_agents.py`. The Research Agent has two tools:

- `WebSearchTool()` - hosted web search via Deep Research models
- `search_sr_corpus` - calls into the local GraphRAG index

```python
from src.agents.biomedical_agents import run_research

result = await run_research(
    "What is the efficacy of LLM-based clinical note summarization "
    "in oncology workflows?",
)
print(result.final_output)
```

`notebooks/biomedical_research_agents.ipynb` is the original interactive
demo (still works); the refactored module is what scripts and other agents
import.

## Notes on the SR corpus

- PubMed and Scopus exports do **not** include abstracts; only Embase and
  IEEE do. With `--require-abstract` you will keep roughly the Embase + IEEE
  subset. Drop the flag to include title-only records as anchor nodes.
- Embase exports use a block-per-record key-value layout (one CSV row per
  field, blocks separated by `---`). `build_corpus.py` handles this.
- GraphRAG indexing on this corpus is **expensive** (one LLM call per chunk
  for entity extraction plus per-community summarization). Start with a
  subset by symlinking a handful of files into `data/graphrag/input/`.

## Model selection

Defaults in `src/graphrag/settings.yaml`:
- chat: `gpt-4o-mini`
- embedding: `text-embedding-3-small`

Override via environment in `.env` or by editing the yaml directly. For
production-grade reports switch the chat model to `gpt-4o` or `o3`.
