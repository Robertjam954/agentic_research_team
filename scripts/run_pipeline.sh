#!/usr/bin/env bash
# Orchestrates the full pipeline:
#   1. Build corpus from the SR CSV exports
#   2. Initialise + index with Microsoft GraphRAG
#   3. Extract leaf / intermediate / macro-root community summaries
#
# Usage:
#   ./scripts/run_pipeline.sh
#   ./scripts/run_pipeline.sh --skip-corpus    # if data/graphrag/input is already populated
set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "${ROOT_DIR}"

CSV_ROOT="${SR_CSV_ROOT:-/Users/robertjames/Documents/Documents - Robert’s iMac/Research Projects/MSKCC Research Fellowship/Projects/llm_systematic_review/search/studies extracted}"
GRAPHRAG_ROOT="${GRAPHRAG_ROOT:-data/graphrag}"
SUMMARY_DIR="${SUMMARY_DIR:-reports/community_summaries}"

SKIP_CORPUS=0
for arg in "$@"; do
  case "$arg" in
    --skip-corpus) SKIP_CORPUS=1 ;;
  esac
done

if [[ "${SKIP_CORPUS}" -eq 0 ]]; then
  echo "==> [1/3] Building corpus from CSV exports"
  python -m src.ingest.build_corpus \
    --csv-root "${CSV_ROOT}" \
    --out-dir "${GRAPHRAG_ROOT}/input" \
    --meta-csv data/processed/metadata.csv \
    --require-abstract
else
  echo "==> [1/3] Skipping corpus build (--skip-corpus)"
fi

echo "==> [2/3] Indexing with Microsoft GraphRAG"
python -m src.graphrag.run_index --root "${GRAPHRAG_ROOT}"

echo "==> [3/3] Extracting community summaries (leaf / intermediate / macro root)"
python -m src.graphrag.extract_summaries --root "${GRAPHRAG_ROOT}" --out-dir "${SUMMARY_DIR}"

echo "Done. Summaries in ${SUMMARY_DIR}/"
