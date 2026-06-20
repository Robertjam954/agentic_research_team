"""
Azure Cosmos DB for MongoDB (vCore) document store.

Durable record for the agentic research app: agent run records (task / progress
ledger snapshots), conversation history, study metadata JSON, extracted
entities, and community summaries. This is the **Mongo wire protocol** offering -
connect with `pymongo`, NOT the `azure-cosmos` SDK.

Endpoint comes from `AZURE_DOCDB_CONNECTION_STRING` (an `mongodb+srv://...
mongocluster.cosmos.azure.com` string). All writes are best-effort and become
no-ops when that variable is unset or pymongo is missing, so local-only runs
keep working without Azure.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional

try:
    from pymongo import MongoClient
except ImportError:  # pymongo is optional until the data tier is wired
    MongoClient = None  # type: ignore[assignment,misc]

DEFAULT_DB = "agentic_research"

# One collection per concern (see CLAUDE.md "Data and storage tier").
RUNS = "runs"                    # agent run records: query, ledgers, output, cost
CONVERSATIONS = "conversations"  # turn-by-turn history keyed by session
STUDIES = "studies"              # study metadata JSON
ENTITIES = "entities"            # GraphRAG extracted entities
SUMMARIES = "summaries"          # community summaries (leaf / intermediate / root)


def _conn_str() -> Optional[str]:
    return os.environ.get("AZURE_DOCDB_CONNECTION_STRING")


def enabled() -> bool:
    """True when a connection string is configured and pymongo is installed."""
    return bool(_conn_str()) and MongoClient is not None


@lru_cache(maxsize=1)
def get_client():  # -> Optional[MongoClient]
    """Cached client. vCore requires TLS; the SRV string already sets tls=true."""
    conn = _conn_str()
    if not conn or MongoClient is None:
        return None
    return MongoClient(conn, appname="agentic_research_team")


def get_db(name: Optional[str] = None):
    client = get_client()
    if client is None:
        return None
    return client[name or os.environ.get("AZURE_DOCDB_DATABASE", DEFAULT_DB)]


def get_collection(name: str):
    db = get_db()
    return None if db is None else db[name]


def ping() -> bool:
    """Verify connectivity to the cluster. False if unconfigured or unreachable."""
    client = get_client()
    if client is None:
        return False
    client.admin.command("ping")
    return True


def save_run_record(record: Dict[str, Any]) -> Optional[str]:
    """Persist one agent run record. Best-effort: returns the inserted id or None."""
    coll = get_collection(RUNS)
    if coll is None:
        return None
    return str(coll.insert_one(record).inserted_id)
