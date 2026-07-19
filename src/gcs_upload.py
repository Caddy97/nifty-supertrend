import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

GCS_BUCKET = os.getenv("GCS_TICK_BUCKET")

_client = None
_warned = False


def _get_client():
    global _client
    if _client is None:
        from google.cloud import storage
        _client = storage.Client()
    return _client


def upload_file(local_path, year, month, day, filename, dataset="ticks", folder=None):
    """Best-effort upload to gs://<bucket>/<dataset>/year=YYYY/month=MM/day=DD/[<folder>/]<filename>.
    `dataset` namespaces the capture (e.g. "ticks" for the dashboard,
    "options_chain" for the standalone chain capturer) so separate processes
    never overwrite each other's files. `folder` further groups by instrument
    (e.g. "24200_CE") when the caller provides one. No-ops (with a one-time
    warning) if GCS isn't configured yet, so local tick capture keeps working
    even before a bucket/service-account exists."""
    global _warned
    if not GCS_BUCKET:
        if not _warned:
            print("[gcs_upload] GCS_TICK_BUCKET not set - skipping GCS upload, keeping local parquet only")
            _warned = True
        return
    try:
        bucket = _get_client().bucket(GCS_BUCKET)
        prefix = f"{dataset}/year={year}/month={month}/day={day}"
        blob_path = f"{prefix}/{folder}/{filename}" if folder else f"{prefix}/{filename}"
        bucket.blob(blob_path).upload_from_filename(local_path)
    except Exception as e:
        print(f"[gcs_upload] upload failed for {local_path}: {e}")
