"""
extract_summaries.py
Read GraphRAG's community_reports.parquet and emit human-readable summaries
bucketed by hierarchy level: leaf (finest), intermediate (middle), and macro
root (coarsest, level 0).

GraphRAG uses Leiden hierarchical clustering. Each community report has a
`level` integer; level 0 is the coarsest "root" partition of the graph and
larger integers are finer-grained sub-communities. We pick three buckets:

    macro_root   -> level == 0
    intermediate -> the median present level (or level 1 if only 0 and max)
    leaf         -> level == max(level)

Outputs (under <out-dir>):
    summaries_macro_root.md
    summaries_intermediate.md
    summaries_leaf.md
    summaries_index.csv      one row per community report

Run:
    python -m src.graphrag.extract_summaries --root data/graphrag --out-dir reports/community_summaries
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median_low

import pandas as pd


def _load_reports(root: Path) -> pd.DataFrame:
    candidates = [
        root / "output" / "community_reports.parquet",
        root / "output" / "create_final_community_reports.parquet",
    ]
    for c in candidates:
        if c.exists():
            return pd.read_parquet(c)
    raise FileNotFoundError(
        f"No community_reports parquet under {root/'output'}. "
        "Did `graphrag index` finish successfully?"
    )


def _bucket_levels(levels: list[int]) -> dict[str, int]:
    uniq = sorted(set(levels))
    if not uniq:
        return {}
    root_lvl = uniq[0]
    leaf_lvl = uniq[-1]
    if len(uniq) == 1:
        return {"macro_root": root_lvl, "intermediate": root_lvl, "leaf": leaf_lvl}
    middle = median_low(uniq[1:-1]) if len(uniq) > 2 else uniq[len(uniq) // 2]
    return {"macro_root": root_lvl, "intermediate": middle, "leaf": leaf_lvl}


def _render_markdown(df: pd.DataFrame, bucket_name: str, level: int) -> str:
    lines = [f"# Community summaries - {bucket_name} (Leiden level {level})", ""]
    lines.append(f"Total communities at this level: **{len(df)}**\n")
    sort_key = "rank" if "rank" in df.columns else "community"
    df = df.sort_values(sort_key, ascending=False if sort_key == "rank" else True)
    for _, row in df.iterrows():
        title = row.get("title") or f"Community {row.get('community', '?')}"
        rank = row.get("rank")
        summary = (row.get("summary") or "").strip()
        full = (row.get("full_content") or row.get("explanation") or "").strip()
        cid = row.get("community", row.get("id", "?"))
        lines.append(f"## [{cid}] {title}")
        if pd.notna(rank):
            lines.append(f"*Impact rank: {rank}*\n")
        if summary:
            lines.append(summary)
        if full and full != summary:
            lines.append("\n<details><summary>Full report</summary>\n")
            lines.append(full)
            lines.append("\n</details>")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="data/graphrag", help="GraphRAG project root")
    p.add_argument(
        "--out-dir",
        default="reports/community_summaries",
        help="Where to write the three markdown summaries and index CSV",
    )
    args = p.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = _load_reports(root)
    if "level" not in reports.columns:
        raise SystemExit("community_reports parquet has no `level` column")

    buckets = _bucket_levels(reports["level"].astype(int).tolist())
    print("Hierarchy buckets:", buckets)

    # Write per-bucket markdown
    for bucket, level in buckets.items():
        subset = reports[reports["level"] == level].copy()
        md = _render_markdown(subset, bucket, level)
        path = out_dir / f"summaries_{bucket}.md"
        path.write_text(md, encoding="utf-8")
        print(f"  - {bucket} (level {level}): {len(subset)} communities -> {path}")

    # Write flat index for downstream tooling
    index_path = out_dir / "summaries_index.csv"
    keep_cols = [c for c in
                 ["community", "level", "title", "rank", "summary", "size"]
                 if c in reports.columns]
    reports[keep_cols].sort_values(["level", "community" if "community" in keep_cols else "title"]) \
        .to_csv(index_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"  - index: {index_path}")


if __name__ == "__main__":
    main()
