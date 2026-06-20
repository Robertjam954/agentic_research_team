"""
run_index.py
Initialise and run the Microsoft GraphRAG indexing pipeline against the
corpus produced by src.ingest.build_corpus.

Workflow:
    1. Ensure <root>/input exists and is populated.
    2. Copy our settings.yaml into <root>/settings.yaml.
    3. Run `graphrag init --root <root>` once (generates prompts/ and .env).
       Existing settings.yaml is preserved with --force only on explicit flag.
    4. Run `graphrag index --root <root>`.

Run:
    python -m src.graphrag.run_index --root data/graphrag
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS_SRC = HERE / "settings.yaml"


def _run(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd, env=env or os.environ.copy())


def ensure_root(root: Path, force_settings: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "input").mkdir(exist_ok=True)
    (root / "output").mkdir(exist_ok=True)
    (root / "cache").mkdir(exist_ok=True)

    target_settings = root / "settings.yaml"
    if not target_settings.exists() or force_settings:
        shutil.copy2(SETTINGS_SRC, target_settings)
        print(f"  - wrote {target_settings}")

    env_file = root / ".env"
    if not env_file.exists():
        api_key = os.environ.get("GRAPHRAG_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        env_file.write_text(f"GRAPHRAG_API_KEY={api_key}\n", encoding="utf-8")
        print(f"  - wrote {env_file}")


def init_prompts(root: Path) -> None:
    # graphrag init creates the prompts/ folder. It is safe to re-run with
    # --force but we only do that on demand because it overwrites settings.
    if (root / "prompts").exists():
        return
    rc = _run([sys.executable, "-m", "graphrag", "init", "--root", str(root)])
    if rc != 0:
        raise SystemExit(f"graphrag init failed with exit code {rc}")


def index(root: Path) -> None:
    rc = _run([sys.executable, "-m", "graphrag", "index", "--root", str(root)])
    if rc != 0:
        raise SystemExit(f"graphrag index failed with exit code {rc}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="data/graphrag", help="GraphRAG project root")
    p.add_argument(
        "--force-settings",
        action="store_true",
        help="Overwrite an existing settings.yaml inside --root",
    )
    p.add_argument(
        "--skip-init",
        action="store_true",
        help="Skip `graphrag init` (use when prompts/ has been customised)",
    )
    args = p.parse_args()

    root = Path(args.root)
    print(f"GraphRAG root: {root.resolve()}")
    ensure_root(root, args.force_settings)

    inputs = list((root / "input").glob("*.txt"))
    if not inputs:
        raise SystemExit(
            f"No .txt files in {root/'input'}. Run src.ingest.build_corpus first."
        )
    print(f"  - {len(inputs)} input documents staged")

    if not args.skip_init:
        init_prompts(root)

    index(root)
    print("\nIndexing complete. Output parquets in:", (root / "output").resolve())


if __name__ == "__main__":
    main()
