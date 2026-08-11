---
paths:
  - "src/**/*.py"
  - "scripts/**/*.py"
---

# Code style (project-specific)

The portfolio `CLAUDE.md` owns the general Python standard (snake_case, PascalCase
classes, required type hints, brief why-focused docstrings, import order). Do not
restate those here. Below is only what is specific to `agentic_research_team`.

- **`from __future__ import annotations`** at the top of every module (matches the
  existing `src/` files and keeps annotations cheap).
- **Config via env vars only.** No hard-coded endpoints, models, keys, or paths.
  Read through `os.environ` / `python-dotenv`; document any new variable in
  `.env.example` and CLAUDE.md section 9. See also [security](security.md).
- **Honest `(target)` labeling.** Code, docstrings, and docs must not imply a
  capability that is not built. If a module is a placeholder, say so; keep the
  current-vs-`(target)` split in CLAUDE.md sections 1-9 truthful.
- **Best-effort persistence never breaks a run.** Store writes (`src/store/*`) are
  wrapped so a missing connection string or driver is a no-op, not a failure - keep
  that pattern (see `docdb.save_run_record`).
- **Single hyphen `-`, never an em dash `—`** in code comments, docstrings, and any
  generated text.
- **`requirements.txt` reflects what runs today.** Only declare third-party imports
  used by code that actually executes (src/, scripts/, the notebook); never add deps
  for `(target)` modules that import nothing yet.
