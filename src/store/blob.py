"""
Azure Blob Storage for biomed files / artifacts.

Holds the non-document artifacts of the research stack: raw SR CSV exports,
GraphRAG outputs (parquet), and CoderAgent-generated figures / tables. Pairs
with the Mongo vCore document store (`docdb.py`), which owns JSON + history.

Auth: a connection string (`AZURE_STORAGE_CONNECTION_STRING`) wins if set;
otherwise `AZURE_STORAGE_ACCOUNT` + `DefaultAzureCredential` (az login / managed
identity - keyless). All ops are best-effort and no-op when nothing is
configured or the SDK is missing, so local-only runs keep working.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

try:
    from azure.storage.blob import BlobServiceClient
except ImportError:  # optional until the data tier is wired
    BlobServiceClient = None  # type: ignore[assignment,misc]

try:
    from azure.identity import DefaultAzureCredential
except ImportError:
    DefaultAzureCredential = None  # type: ignore[assignment,misc]


def _conn_str() -> Optional[str]:
    return os.environ.get("AZURE_STORAGE_CONNECTION_STRING")


def _account() -> Optional[str]:
    return os.environ.get("AZURE_STORAGE_ACCOUNT")


def _container() -> Optional[str]:
    return os.environ.get("AZURE_STORAGE_CONTAINER")


def enabled() -> bool:
    """True when the SDK is present and either a conn string or account is set."""
    return BlobServiceClient is not None and bool(_conn_str() or _account())


@lru_cache(maxsize=1)
def get_service_client():  # -> Optional[BlobServiceClient]
    if BlobServiceClient is None:
        return None
    conn = _conn_str()
    if conn:
        return BlobServiceClient.from_connection_string(conn)
    account = _account()
    if account and DefaultAzureCredential is not None:
        url = f"https://{account}.blob.core.windows.net"
        return BlobServiceClient(account_url=url, credential=DefaultAzureCredential())
    return None


def get_container_client(name: Optional[str] = None):
    svc = get_service_client()
    if svc is None:
        return None
    return svc.get_container_client(name or _container())


def ping() -> bool:
    """Verify the container is reachable. False if unconfigured or unreachable."""
    cc = get_container_client()
    if cc is None:
        return False
    cc.get_container_properties()
    return True


def upload_file(
    local_path: str,
    blob_name: Optional[str] = None,
    container: Optional[str] = None,
    overwrite: bool = True,
) -> Optional[str]:
    """Upload one file. Returns the blob name, or None if storage is unconfigured."""
    cc = get_container_client(container)
    if cc is None:
        return None
    name = blob_name or os.path.basename(local_path)
    with open(local_path, "rb") as fh:
        cc.upload_blob(name=name, data=fh, overwrite=overwrite)
    return name


def download_file(blob_name: str, local_path: str, container: Optional[str] = None) -> bool:
    """Download one blob to local_path. False if storage is unconfigured."""
    cc = get_container_client(container)
    if cc is None:
        return False
    with open(local_path, "wb") as fh:
        fh.write(cc.download_blob(blob_name).readall())
    return True


def list_blobs(container: Optional[str] = None, prefix: Optional[str] = None) -> List[str]:
    cc = get_container_client(container)
    if cc is None:
        return []
    return [b.name for b in cc.list_blobs(name_starts_with=prefix)]
