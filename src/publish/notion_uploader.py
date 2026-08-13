"""Upload research notes to the blog-review Notion database.

Pushes a Markdown note (a research report from the pipeline, or any .md file)
into the shared Notion database with Status = "Needs Review". After human
review in Notion, notes marked "Ready for Blog" are picked up by the blog
generator in the agentic_content_extraction_blog_writer repo.

Usage (CLI):
  export NOTION_API_KEY=secret_...
  export NOTION_DATABASE_ID=...
  python -m src.publish.notion_uploader reports/report.md \
      --title "LLM summarization in oncology" \
      --tags oncology llm-summarization \
      --keywords "clinical NLP" "LLM evaluation" \
      --source https://example.com/underlying-paper

Usage (library):
  from src.publish.notion_uploader import upload_note
  url = upload_note(title=..., markdown=..., tags=[...])
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
MAX_RICH_TEXT_LEN = 2000
MAX_CHILDREN_PER_REQUEST = 100

STATUS_NEEDS_REVIEW = "Needs Review"


class NotionError(RuntimeError):
    """Raised when the Notion API returns an error response."""


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        raise NotionError("NOTION_API_KEY is not set")

    url = f"{NOTION_BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < 3:
                wait = float(exc.headers.get("Retry-After", 2 ** attempt))
                logger.warning("Notion rate limit hit; retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            raise NotionError(f"Notion API {exc.code} on {method} {path}: {payload}") from exc
        except urllib.error.URLError as exc:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise NotionError(f"Network error on {method} {path}: {exc}") from exc
    raise NotionError(f"Exhausted retries on {method} {path}")


def _rich_text(text: str) -> list[dict[str, Any]]:
    chunks = [text[i : i + MAX_RICH_TEXT_LEN] for i in range(0, len(text), MAX_RICH_TEXT_LEN)]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks or [""]]


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """Convert Markdown into Notion blocks (headings, lists, quotes, code)."""
    blocks: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    i = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(paragraph).strip()
            if text:
                blocks.append(
                    {"type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}
                )
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip() or "plain text"
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(
                {
                    "type": "code",
                    "code": {
                        "rich_text": _rich_text("\n".join(code_lines)),
                        "language": language,
                    },
                }
            )
        elif stripped.startswith("#"):
            flush_paragraph()
            level = min(len(stripped) - len(stripped.lstrip("#")), 3)
            text = stripped.lstrip("#").strip()
            key = f"heading_{level}"
            blocks.append({"type": key, key: {"rich_text": _rich_text(text)}})
        elif stripped.startswith(("- ", "* ")):
            flush_paragraph()
            blocks.append(
                {
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich_text(stripped[2:].strip())},
                }
            )
        elif stripped[:2].rstrip(".").isdigit() and ". " in stripped[:5]:
            flush_paragraph()
            text = stripped.split(". ", 1)[1]
            blocks.append(
                {
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": _rich_text(text)},
                }
            )
        elif stripped.startswith("> "):
            flush_paragraph()
            blocks.append({"type": "quote", "quote": {"rich_text": _rich_text(stripped[2:])}})
        elif stripped in ("---", "***", "___"):
            flush_paragraph()
            blocks.append({"type": "divider", "divider": {}})
        elif not stripped:
            flush_paragraph()
        else:
            paragraph.append(stripped)
        i += 1

    flush_paragraph()
    return blocks


def upload_note(
    title: str,
    markdown: str,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    source: str | None = None,
    database_id: str | None = None,
) -> str:
    """Create a "Needs Review" page in the blog database. Returns the page URL."""
    database_id = database_id or os.environ.get("NOTION_DATABASE_ID")
    if not database_id:
        raise NotionError("NOTION_DATABASE_ID is not set")

    properties: dict[str, Any] = {
        "Name": {"title": [{"type": "text", "text": {"content": title[:200]}}]},
        "Status": {"select": {"name": STATUS_NEEDS_REVIEW}},
    }
    if tags:
        properties["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}
    if keywords:
        properties["SEO Keywords"] = {"multi_select": [{"name": kw} for kw in keywords]}
    if source:
        properties["Source"] = {"url": source}

    children = markdown_to_blocks(markdown)
    first_batch = children[:MAX_CHILDREN_PER_REQUEST]
    rest = children[MAX_CHILDREN_PER_REQUEST:]

    page = _request(
        "POST",
        "/pages",
        {
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": first_batch,
        },
    )
    page_id = page["id"]
    while rest:
        batch, rest = rest[:MAX_CHILDREN_PER_REQUEST], rest[MAX_CHILDREN_PER_REQUEST:]
        _request("PATCH", f"/blocks/{page_id}/children", {"children": batch})

    url = page.get("url", "")
    logger.info("Uploaded %r to Notion for review: %s", title, url)
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown_file", type=Path, help="Markdown note/report to upload")
    parser.add_argument("--title", help="Page title (default: first heading or filename)")
    parser.add_argument("--tags", nargs="*", default=[], help="Tags for the note")
    parser.add_argument("--keywords", nargs="*", default=[], help="SEO keywords")
    parser.add_argument("--source", help="URL of the underlying source (optional)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    markdown = args.markdown_file.read_text(encoding="utf-8")
    title = args.title
    if not title:
        for line in markdown.splitlines():
            if line.strip().startswith("#"):
                title = line.strip().lstrip("#").strip()
                break
        title = title or args.markdown_file.stem.replace("_", " ").replace("-", " ")

    url = upload_note(
        title=title,
        markdown=markdown,
        tags=args.tags,
        keywords=args.keywords,
        source=args.source,
    )
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
