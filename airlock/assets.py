"""Assets live in GCS for the cloud (Agent Engine has no local files); the gates that need bytes
download them to a temp file, the gates that take a URI use it directly."""

from __future__ import annotations

import pathlib
import tempfile

from airlock import settings
from airlock.gates.base import Asset


def _storage_client():
    from google.cloud import storage

    return storage.Client(project=settings.project())


def download(gcs_uri: str, dest_dir: str | None = None) -> str:
    bucket_name, _, blob_name = gcs_uri.removeprefix("gs://").partition("/")
    dest_dir = dest_dir or tempfile.mkdtemp(prefix="airlock-")
    dest = pathlib.Path(dest_dir) / pathlib.Path(blob_name).name
    _storage_client().bucket(bucket_name).blob(blob_name).download_to_filename(str(dest))
    return str(dest)


def ensure_local(asset: Asset) -> Asset:
    """Give the asset a readable local path, downloading from GCS when it only has a URI."""
    if asset.path and pathlib.Path(asset.path).exists():
        return asset
    if not asset.gcs_uri:
        raise FileNotFoundError(f"asset {asset.asset_id} has neither a local file nor a GCS URI")
    asset.path = download(asset.gcs_uri)
    return asset


def from_message(text: str) -> Asset:
    """The pipeline's input: a GCS URI, a local path, or a JSON object with gcs_uri and asset_id."""
    import json

    text = text.strip()
    if text.startswith("{"):
        d = json.loads(text)
        uri = d.get("gcs_uri")
        path = d.get("path") or ""
        asset_id = d.get("asset_id") or pathlib.Path(uri or path).stem
        return Asset(asset_id=asset_id, path=path, gcs_uri=uri)
    if text.startswith("gs://"):
        return Asset(asset_id=pathlib.Path(text).stem, path="", gcs_uri=text)
    return Asset(asset_id=pathlib.Path(text).stem, path=text, gcs_uri=None)
