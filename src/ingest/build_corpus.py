"""
build_corpus.py
Unify systematic-review study exports (PubMed, Scopus, Embase, IEEE Xplore)
into a single GraphRAG input corpus.

For every study we emit a plain-text file under data/graphrag/input/ with a
small structured header (title, authors, journal, year, DOI, source database)
followed by the abstract when available. We also write a deduplicated
metadata.csv keyed by DOI when present, otherwise by a slug of the title.

Run:
    python -m src.ingest.build_corpus \
        --csv-root "/Users/robertjames/Documents/Documents - Robert’s iMac/Research Projects/MSKCC Research Fellowship/Projects/llm_systematic_review/search/studies extracted" \
        --out-dir data/graphrag/input \
        --meta-csv data/processed/metadata.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Iterator

csv.field_size_limit(sys.maxsize)


# ---------------------------------------------------------------------------
# Record model
# ---------------------------------------------------------------------------
@dataclass
class Study:
    source_db: str
    title: str
    authors: str = ""
    journal: str = ""
    year: str = ""
    doi: str = ""
    abstract: str = ""
    keywords: str = ""
    url: str = ""
    raw_id: str = ""

    def key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.strip().lower()}"
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")[:80]
        return f"title:{slug}"

    def filename(self) -> str:
        h = hashlib.sha1(self.key().encode("utf-8")).hexdigest()[:10]
        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")[:60] or "study"
        return f"{self.source_db}_{slug}_{h}.txt"

    def has_content(self) -> bool:
        return bool(self.title) and (bool(self.abstract) or bool(self.keywords))

    def to_text(self) -> str:
        parts = [
            f"Title: {self.title}",
            f"Authors: {self.authors}" if self.authors else "",
            f"Journal: {self.journal}" if self.journal else "",
            f"Year: {self.year}" if self.year else "",
            f"DOI: {self.doi}" if self.doi else "",
            f"Source: {self.source_db}",
            f"Keywords: {self.keywords}" if self.keywords else "",
            "",
            "Abstract:",
            self.abstract or "(no abstract provided in the source export)",
        ]
        return "\n".join(p for p in parts if p is not None)


# ---------------------------------------------------------------------------
# Per-database parsers
# ---------------------------------------------------------------------------
def parse_pubmed(path: Path) -> Iterator[Study]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            title = (row.get("Title") or "").strip()
            if not title:
                continue
            yield Study(
                source_db="pubmed",
                title=title,
                authors=(row.get("Authors") or "").strip(),
                journal=(row.get("Journal/Book") or "").strip(),
                year=(row.get("Publication Year") or "").strip(),
                doi=(row.get("DOI") or "").strip(),
                raw_id=(row.get("PMID") or "").strip(),
            )


def parse_scopus(path: Path) -> Iterator[Study]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            title = (row.get("Title") or "").strip()
            if not title:
                continue
            yield Study(
                source_db="scopus",
                title=title,
                authors=(row.get("Authors") or "").strip(),
                journal=(row.get("Source title") or "").strip(),
                year=(row.get("Year") or "").strip(),
                doi=(row.get("DOI") or "").strip(),
                abstract=(row.get("Abstract") or "").strip(),
                url=(row.get("Link") or "").strip(),
                raw_id=(row.get("EID") or "").strip(),
            )


def parse_ieee(path: Path) -> Iterator[Study]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            title = (row.get("Document Title") or "").strip()
            if not title:
                continue
            yield Study(
                source_db="ieee_xplore",
                title=title,
                authors=(row.get("Authors") or "").strip(),
                journal=(row.get("Publication Title") or "").strip(),
                year=(row.get("Publication Year") or "").strip(),
                doi=(row.get("DOI") or "").strip(),
                abstract=(row.get("Abstract") or "").strip(),
                keywords=(row.get("Author Keywords") or "").strip(),
                url=(row.get("PDF Link") or "").strip(),
            )


# Embase export uses one row per field within a record. Records are
# separated by a line of dashes. We rebuild records by reading the raw CSV
# row by row and grouping by separator lines.
_EMBASE_SEP_RE = re.compile(r"^-{5,}$")


def _embase_records(path: Path) -> Iterator[dict[str, list[str]]]:
    current: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                if current:
                    yield current
                    current = {}
                continue
            first = (row[0] or "").strip()
            if not first:
                if current:
                    yield current
                    current = {}
                continue
            if _EMBASE_SEP_RE.match(first):
                if current:
                    yield current
                    current = {}
                continue
            if first.isupper() or first.startswith(("AiP", "FULL")) or first in {
                "TITLE", "AUTHOR NAMES", "SOURCE", "SOURCE TITLE",
                "PUBLICATION YEAR", "ABSTRACT", "DOI", "AUTHOR KEYWORDS",
                "EMTREE MEDICAL INDEX TERMS", "EMTREE MEDICAL INDEX TERMS (MAJOR FOCUS)",
                "EMTREE DRUG INDEX TERMS", "VOLUME", "ISSUE", "PUBLICATION TYPE",
                "DATE OF PUBLICATION", "FIRST PAGE", "LAST PAGE", "EMBASE LINK",
                "OPEN URL LINK", "FULL TEXT LINK", "COPYRIGHT",
                "EMBASE CLASSIFICATIONS", "CLINICAL TRIAL NUMBERS",
                "DEVICE MANUFACTURERS", "DEVICE TRADE NAMES",
                "DRUG MANUFACTURERS", "DRUG TRADE NAMES",
                "CAS REGISTRY NUMBERS", "AiP/IP ENTRY DATE",
                "FULL RECORD ENTRY DATE",
            }:
                values = [c.strip() for c in row[1:] if c and c.strip()]
                current[first] = values
            else:
                # continuation of a long previous value - append to last key
                if current:
                    last_key = list(current.keys())[-1]
                    current[last_key].extend(c.strip() for c in row if c and c.strip())
        if current:
            yield current


def parse_embase(path: Path) -> Iterator[Study]:
    for rec in _embase_records(path):
        title_vals = rec.get("TITLE") or []
        if not title_vals:
            continue
        title = title_vals[0]
        if title.startswith("(") and "OR" in title:  # this is the search query row
            continue
        authors = ", ".join(rec.get("AUTHOR NAMES", []))
        journal = (rec.get("SOURCE TITLE") or [""])[0]
        year = (rec.get("PUBLICATION YEAR") or [""])[0]
        doi = (rec.get("DOI") or [""])[0]
        abstract = " ".join(rec.get("ABSTRACT", []))
        author_kw = "; ".join(rec.get("AUTHOR KEYWORDS", []))
        emtree = "; ".join(rec.get("EMTREE MEDICAL INDEX TERMS", []))
        keywords = "; ".join(filter(None, [author_kw, emtree]))
        url = (rec.get("FULL TEXT LINK") or rec.get("EMBASE LINK") or [""])[0]
        yield Study(
            source_db="embase",
            title=title,
            authors=authors,
            journal=journal,
            year=year,
            doi=doi,
            abstract=abstract,
            keywords=keywords,
            url=url,
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
PARSERS = {
    "pubmed": (parse_pubmed, "csv_studies_pubmed.csv"),
    "scopus": (parse_scopus, "csv_studies_scopus.csv"),
    "embase": (parse_embase, "csv_studies_embase.csv"),
    "ieee_xplore": (parse_ieee, "csv_studies_ieee_xplore_1k.csv"),
}


def iter_all_studies(csv_root: Path) -> Iterator[Study]:
    for db, (parser, filename) in PARSERS.items():
        path = csv_root / db / filename
        if not path.exists():
            print(f"  ! skipping {db}: {path} not found", file=sys.stderr)
            continue
        n = 0
        for study in parser(path):
            n += 1
            yield study
        print(f"  - {db}: parsed {n} records from {path.name}")


def write_corpus(
    studies: Iterable[Study],
    out_dir: Path,
    meta_csv: Path,
    require_abstract: bool = False,
) -> tuple[int, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_csv.parent.mkdir(parents=True, exist_ok=True)

    seen: dict[str, Study] = {}
    skipped_empty = 0
    for s in studies:
        if require_abstract and not s.abstract:
            skipped_empty += 1
            continue
        if not s.has_content() and not s.title:
            skipped_empty += 1
            continue
        key = s.key()
        if key in seen:
            existing = seen[key]
            # prefer the record with an abstract
            if not existing.abstract and s.abstract:
                seen[key] = s
            continue
        seen[key] = s

    fieldnames = list(asdict(next(iter(seen.values()))).keys()) if seen else [
        "source_db", "title", "authors", "journal", "year", "doi",
        "abstract", "keywords", "url", "raw_id",
    ]
    fieldnames = ["key", "filename"] + fieldnames

    with meta_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for key, s in seen.items():
            fname = s.filename()
            (out_dir / fname).write_text(s.to_text(), encoding="utf-8")
            writer.writerow({"key": key, "filename": fname, **asdict(s)})

    return len(seen), skipped_empty


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--csv-root",
        required=True,
        help="Folder containing pubmed/, scopus/, embase/, ieee_xplore/ subfolders",
    )
    p.add_argument(
        "--out-dir",
        default="data/graphrag/input",
        help="Where to write one .txt per study (becomes GraphRAG input/)",
    )
    p.add_argument(
        "--meta-csv",
        default="data/processed/metadata.csv",
        help="Deduplicated metadata index",
    )
    p.add_argument(
        "--require-abstract",
        action="store_true",
        help="Skip records with no abstract (recommended for GraphRAG quality)",
    )
    args = p.parse_args()

    csv_root = Path(args.csv_root).expanduser()
    out_dir = Path(args.out_dir)
    meta_csv = Path(args.meta_csv)

    print(f"Reading CSVs from: {csv_root}")
    studies = list(iter_all_studies(csv_root))
    print(f"Total raw records: {len(studies)}")

    n, skipped = write_corpus(studies, out_dir, meta_csv, args.require_abstract)
    print(f"Wrote {n} unique study files to {out_dir}")
    print(f"Skipped (empty or no abstract): {skipped}")
    print(f"Metadata index: {meta_csv}")


if __name__ == "__main__":
    main()
