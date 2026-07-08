import os

GCS_BUCKET = os.getenv("GCS_TICK_BUCKET")

_client = None
_warned = False


def _get_client():
    global _client
    if _client is None:
        from google.cloud import storage
        _client = storage.Client()
    return _client


def upload_file(local_path, year, month, day, filename):
    """Best-effort upload to gs://<bucket>/ticks/year=YYYY/month=MM/day=DD/<filename>.
    No-ops (with a one-time warning) if GCS isn't configured yet, so local tick
    capture keeps working even before a bucket/service-account exists."""
    global _warned
    if not GCS_BUCKET:
        if not _warned:
            print("[gcs_upload] GCS_TICK_BUCKET not set - skipping GCS upload, keeping local parquet only")
            _warned = True
        return
    try:
        bucket = _get_client().bucket(GCS_BUCKET)
        blob_path = f"ticks/year={year}/month={month}/day={day}/{filename}"
        bucket.blob(blob_path).upload_from_filename(local_path)
    except Exception as e:
        print(f"[gcs_upload] upload failed for {local_path}: {e}")
