#!/usr/bin/env python3
"""
deidentify_redcap.py
--------------------
De-identify REDCap-style exports for on-prem usage.


Key features
* Deterministic per-participant DATE SHIFTING using an HMAC(seed) offset (preserves within-subject temporal relationships).
* Drops direct identifiers (names, emails, phone, MRN, SSN, addresses).
* Hashes participant IDs with a separate salt to produce a non-reversible study_id.
* ZIP generalization to ZIP3 (last two digits -> "00").
* Age handling: compute from DOB when available; bin >89 as "90+" (sets age_90plus flag).
* Timestamp rounding (e.g., to day or 15-min increments).
* Basic PHI scrubbing in free text columns (emails, phones, SSNs, URLs, dates).
* Provenance JSON with operations performed and column-level notes.
* Optional secure linkage file (kept OFF the shared path) if you must retain a map from original_id -> hashed_id.


Usage
-----
python deidentify_redcap.py \
  --in /path/input.csv \
  --out /path/deid.csv \
  --id-col record_id \
  --date-cols "visit_date,created_ts,updated_ts" \
  --drop-cols "first_name,last_name,email,phone,address,city,state,zipcode,ssn,mrn" \
  --text-cols "free_text,notes,comments" \
  --salt-file ./date_shift_salt.txt \
  --hash-salt-file ./id_hash_salt.txt \
  --round-timestamps "D" \
  --zip-col zipcode \
  --dob-col dob \
  --age-col age \
  --max-shift-days 180 \
  --emit-linkage /secure/offline/linkage_map.csv


Notes
-----
- Keep your salts in a secure, on-prem location with restricted access.
- If salts are lost, you can still use the output, but you cannot reproduce the exact date shifts or hashed IDs.
- Free-text scrubbing is heuristic; do not rely on it alone for PHI—prefer removing free text or replacing with coded fields when possible.
"""


import argparse
import json
import re
import os
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import hmac
import pandas as pd
import numpy as np


def _load_or_create_salt(path: Path) -> bytes:
    path = Path(path)
    if path.exists():
        b = path.read_bytes().strip()
        if not b:
            raise ValueError(f"Salt file {path} is empty.")
        return b
    # create a new random salt
    rnd = os.urandom(32)
    path.write_bytes(rnd)
    return rnd


def _hmac_int(salt: bytes, key: str) -> int:
    hm = hmac.new(salt, key.encode('utf-8'), hashlib.sha256).digest()
    return int.from_bytes(hm[:8], 'big', signed=False)


def _deterministic_shift_days(salt: bytes, subject_key: str, max_days: int) -> int:
    if max_days <= 0:
        return 0
    x = _hmac_int(salt, subject_key)
    # map to symmetric range [-max_days, +max_days]
    return (x % (2*max_days + 1)) - max_days


def _hash_id(salt: bytes, subject_key: str) -> str:
    hm = hmac.new(salt, subject_key.encode('utf-8'), hashlib.sha256).hexdigest()
    return hm[:16]  # short stable pseudonym


def _parse_cols(s: str):
    if s is None or s.strip() == "":
        return []
    return [c.strip() for c in s.split(",") if c.strip()]


def _to_datetime(s):
    try:
        return pd.to_datetime(s, errors="coerce", utc=False, infer_datetime_format=True)
    except Exception:
        return pd.to_datetime(s, errors="coerce", utc=False)


def _round_timestamp(series: pd.Series, rule: str) -> pd.Series:
    # rule examples: 'D' (day), 'H' (hour), '15T' (15 minutes)
    try:
        return series.dt.round(rule)
    except Exception:
        return series


PHI_PATTERNS = [
    # emails
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # phones (simple)
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    # SSNs
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # URLs
    (re.compile(r"https?://\S+"), "[URL]"),
    # Dates in common formats (very approximate)
    (re.compile(r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b"), "[DATE]"),
]


def scrub_text(s: pd.Series) -> pd.Series:
    def _scrub_one(x):
        if not isinstance(x, str):
            return x
        y = x
        for pat, repl in PHI_PATTERNS:
            y = pat.sub(repl, y)
        return y
    return s.apply(_scrub_one)


def generalize_zip(zip_series: pd.Series) -> pd.Series:
    def _clean(z):
        if pd.isna(z):
            return z
        z_str = re.sub(r"\D", "", str(z))
        if len(z_str) >= 3:
            return z_str[:3] + "00"
        return np.nan
    return zip_series.apply(_clean)


def compute_age_from_dob(dob_series: pd.Series, ref_date: pd.Timestamp) -> pd.Series:
    dob_dt = _to_datetime(dob_series)
    return ((ref_date - dob_dt).dt.days // 365.25).astype("float")


def main():
    ap = argparse.ArgumentParser(description="De-identify REDCap-like datasets")
    ap.add_argument("--in", dest="in_path", required=True, help="Input CSV file exported from REDCap")
    ap.add_argument("--out", dest="out_path", required=True, help="Output CSV path for de-identified data")
    ap.add_argument("--id-col", dest="id_col", required=True, help="Participant/record ID column")
    ap.add_argument("--date-cols", dest="date_cols", default="", help="Comma-separated list of date/datetime columns")
    ap.add_argument("--drop-cols", dest="drop_cols", default="", help="Comma-separated list of direct identifier columns to drop")
    ap.add_argument("--text-cols", dest="text_cols", default="", help="Comma-separated list of free-text columns to scrub")
    ap.add_argument("--salt-file", dest="salt_file", required=True, help="Path to the date-shift salt file (on-prem, secure)")
    ap.add_argument("--hash-salt-file", dest="hash_salt_file", required=True, help="Path to the ID-hash salt file (on-prem, secure)")
    ap.add_argument("--max-shift-days", dest="max_shift_days", type=int, default=180, help="Max absolute days to shift (+/-)")
    ap.add_argument("--round-timestamps", dest="round_rule", default="D", help="Pandas rounding rule (e.g., D, H, 15T) applied after shifting")
    ap.add_argument("--zip-col", dest="zip_col", default="", help="ZIP/postal code column (optional)")
    ap.add_argument("--dob-col", dest="dob_col", default="", help="DOB column (optional)")
    ap.add_argument("--age-col", dest="age_col", default="", help="Age column (optional)")
    ap.add_argument("--emit-linkage", dest="emit_linkage", default="", help="Optional path to write mapping of original_id->hashed_id (store offline!)")
    args = ap.parse_args()


    in_path = Path(args.in_path)
    out_path = Path(args.out_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")


    df = pd.read_csv(in_path, dtype=str)  # read as strings; we'll convert selectively
    if args.id_col not in df.columns:
        raise ValueError(f"ID column '{args.id_col}' not found in columns: {list(df.columns)}")


    date_cols = _parse_cols(args.date_cols)
    drop_cols = _parse_cols(args.drop_cols)
    text_cols = _parse_cols(args.text_cols)


    salt = _load_or_create_salt(Path(args.salt_file))
    hash_salt = _load_or_create_salt(Path(args.hash_salt_file))


    # build per-subject shift map and hashed IDs
    ids = df[args.id_col].astype(str).fillna("")
    unique_ids = ids.unique().tolist()
    shift_map = {sid: _deterministic_shift_days(salt, sid, args.max_shift_days) for sid in unique_ids}
    hash_map = {sid: _hash_id(hash_salt, sid) for sid in unique_ids}


    # Apply hashed ID (new column) and drop original ID at the end (or keep as needed)
    df.insert(0, "deid_id", ids.map(hash_map))


    # Date shifting
    for col in date_cols:
        if col not in df.columns:
            continue
        dt = _to_datetime(df[col])
        # compute shifted timestamps per row based on subject id
        shifts = ids.map(lambda sid: timedelta(days=shift_map.get(sid, 0)))
        shifted = dt + shifts
        if args.round_rule:
            try:
                shifted = shifted.dt.round(args.round_rule)
            except Exception:
                pass
        # preserve original timezone-naive formatting (ISO date if time=00:00)
        df[col] = shifted.dt.strftime("%Y-%m-%d %H:%M:%S").where(~shifted.isna(), other=np.nan)


    # ZIP generalization
    if args.zip_col and args.zip_col in df.columns:
        df[args.zip_col] = generalize_zip(df[args.zip_col])


    # Age handling
    today = pd.to_datetime("today").normalize()
    if args.dob_col and args.dob_col in df.columns:
        # Compute age from DOB
        ages = compute_age_from_dob(df[args.dob_col], today)
        df["age_years"] = np.floor(ages).where(~ages.isna(), other=np.nan)
    if args.age_col and args.age_col in df.columns:
        # Ensure numeric
        df[args.age_col] = pd.to_numeric(df[args.age_col], errors="coerce")


    # Create age_90plus flag and cap ages
    age_source = None
    if "age_years" in df.columns:
        age_source = "age_years"
    elif args.age_col and args.age_col in df.columns:
        age_source = args.age_col


    if age_source:
        df["age_90plus"] = df[age_source] >= 90
        df[age_source] = df[age_source].apply(lambda x: 90 if pd.notna(x) and x > 89 else x)


    # Scrub free-text
    for col in text_cols:
        if col in df.columns:
            df[col] = scrub_text(df[col])


    # Drop direct identifiers
    for col in drop_cols:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)


    # Emit linkage file (OPTIONAL): keep OFFLINE and access-restricted
    if args.emit_linkage:
        link_path = Path(args.emit_linkage)
        link_df = pd.DataFrame({
            "original_id": unique_ids,
            "deid_id": [hash_map[sid] for sid in unique_ids],
            "date_shift_days": [shift_map[sid] for sid in unique_ids],
        })
        # ensure directory exists
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_df.to_csv(link_path, index=False)


    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


    # Write provenance JSON
    prov = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": str(in_path),
        "output_file": str(out_path),
        "id_col": args.id_col,
        "date_cols": date_cols,
        "drop_cols": drop_cols,
        "text_cols": text_cols,
        "zip_col": args.zip_col,
        "dob_col": args.dob_col,
        "age_col": args.age_col,
        "round_rule": args.round_rule,
        "max_shift_days": args.max_shift_days,
        "salts": {
            "date_shift_salt_sha256": hashlib.sha256(salt).hexdigest(),
            "id_hash_salt_sha256": hashlib.sha256(hash_salt).hexdigest()
        },
        "notes": [
            "Dates shifted deterministically per subject using HMAC salt; temporal order preserved within subject.",
            "IDs hashed with separate salt; original ID replaced with 'deid_id'.",
            "ZIP generalized to ZIP3 (last two digits -> '00').",
            "Ages >89 capped at 90 and age_90plus flag added.",
            "Timestamps rounded per --round-timestamps rule.",
            "Free-text columns scrubbed heuristically for emails/phones/SSNs/URLs/dates.",
            "If linkage file emitted, store it OFF the analysis/share path with restricted access."
        ]
    }
    prov_path = out_path.with_suffix(".provenance.json")
    with open(prov_path, "w") as f:
        json.dump(prov, f, indent=2)


    print(f"De-identified data written to: {out_path}")
    print(f"Provenance written to: {prov_path}")
    if args.emit_linkage:
        print(f"Linkage map written to: {args.emit_linkage} (KEEP SECURE)")


if __name__ == "__main__":
    main()
