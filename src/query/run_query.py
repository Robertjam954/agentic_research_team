"""
run_query.py
Thin CLI around `graphrag query` that supports global, local, drift, and
basic search modes. Defaults to global search at community level 2 which is
a sensible balance between breadth and specificity for SR corpora.

Run:
    python -m src.query.run_query --root data/graphrag --method global \
        --query "What architectures are used for clinical note summarization?"

    python -m src.query.run_query --root data/graphrag --method local \
        --query "Studies that fine-tuned BioBERT on oncology notes"

The function `query()` is reusable from notebooks and the biomedical agent.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

VALID_METHODS = ("global", "local", "drift", "basic")


def query(
    text: str,
    root: str | Path = "data/graphrag",
    method: str = "global",
    community_level: int | None = 2,
    response_type: str = "Multiple paragraphs",
) -> str:
    """Run a GraphRAG query via the CLI and return the captured stdout."""
    if method not in VALID_METHODS:
        raise ValueError(f"method must be one of {VALID_METHODS}, got {method!r}")

    cmd = [
        sys.executable, "-m", "graphrag", "query",
        "--root", str(root),
        "--method", method,
        "--response-type", response_type,
    ]
    if method == "global" and community_level is not None:
        cmd += ["--community-level", str(community_level)]
    # graphrag>=2 takes the query as a positional argument (was --query).
    cmd.append(text)

    env = os.environ.copy()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise RuntimeError(
            f"graphrag query failed (exit {result.returncode}). See stderr above."
        )
    return result.stdout


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="data/graphrag")
    p.add_argument("--method", choices=VALID_METHODS, default="global")
    p.add_argument("--community-level", type=int, default=2,
                   help="Used by global search. 0=root, higher=finer/leaf.")
    p.add_argument("--response-type", default="Multiple paragraphs")
    p.add_argument("--query", required=True)
    args = p.parse_args()

    out = query(
        text=args.query,
        root=args.root,
        method=args.method,
        community_level=args.community_level,
        response_type=args.response_type,
    )
    print(out)


if __name__ == "__main__":
    main()
