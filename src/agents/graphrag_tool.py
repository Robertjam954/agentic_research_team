"""
graphrag_tool.py
Expose the local GraphRAG index as a function tool for the OpenAI Agents
SDK. The Research Agent can then query our SR corpus alongside its web
search tool.
"""
from __future__ import annotations

import os
from pathlib import Path

from agents import function_tool

from src.query.run_query import query as graphrag_query

DEFAULT_ROOT = Path(os.environ.get("GRAPHRAG_ROOT", "data/graphrag"))


@function_tool
def search_sr_corpus(
    question: str,
    method: str = "global",
    community_level: int = 2,
) -> str:
    """
    Search the local systematic-review corpus indexed by Microsoft GraphRAG.

    Args:
        question: A natural-language question grounded in the SR papers.
        method:   "global" for dataset-wide synthesis,
                  "local"  for entity- or paper-specific lookups,
                  "drift"  for community-aware local expansion,
                  "basic"  for plain vector retrieval.
        community_level: Used by global search. 0=root (broadest themes),
                         increasing numbers descend toward leaf clusters
                         (most specific sub-topics). Default 2.
    Returns:
        The synthesized answer with inline citations from the indexed corpus.
    """
    return graphrag_query(
        text=question,
        root=DEFAULT_ROOT,
        method=method,
        community_level=community_level if method == "global" else None,
    )
