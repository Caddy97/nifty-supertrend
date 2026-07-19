import os
import json
import shutil
import threading
import time
from datetime import datetime, timedelta

import gcs_upload
import market_calendar

# Dataset name — namespaces the intraday JSONL dir (data/live/<DATASET>), the
# converted-archive dir (data/archive/<DATASET>) and the GCS prefix
# (<DATASET>/year=.../). Defaults to "ticks" so the dashboard (app.py) is
# unchanged. A separate capturer (e.g. options_chain_store.py) calls
# set_dataset() to write to its own namespace and never collide.
DATASET = "ticks"
LIVE_DIR = os.path.join("data", "live", DATASET)
ARCHIVE_DIR = os.path.join("data", "archive", DATASET)

RETENTION_DAYS = 60                          # local archive: prune parquet older than this
RETENTION_MAX_BYTES = 10 * 1024 * 1024 * 1024  # ...or oldest-first once the archive exceeds 10GB
JSONL_BUFFER_DAYS = 1                        # keep raw JSONL this many days after a successful conversion


def set_dataset(name):
    """Point this process's capture at its own dataset namespace (local + GCS).
    Must be called before start_flush_thread() / any record_tick()."""
    global DATASET, LIVE_DIR, ARCHIVE_DIR
    DATASET = name
    LIVE_DIR = os.path.join("data", "live", name)
    ARCHIVE_DIR = os.path.join("data", "archive", name)


# token -> human-readable name (e.g. "NIFTY26JUL24000CE"), stored as the real
# `symbol` column in every row - the true, expiry-specific identity. A token
# with no registered name falls back to the raw token.
_symbol_map = {}


def register_symbol(token, name):
    if name:
        _symbol_map[int(token)] = str(name).strip()


def register_symbols(mapping):
    """Bulk version of register_symbol({token: name, ...})."""
    for token, name in mapping.items():
        register_symbol(token, name)


# token -> stable, query-friendly output key (e.g. "24200_CE", "NIFTY_SPOT"),
# used ONLY to decide the EOD parquet filename/grouping - deliberately kept
# separate from _symbol_map so the real tradingsymbol (which changes weekly)
# never leaks into the filename, while the filename stays stable week to week.
# Falls back to the registered symbol, then the raw token, if unset.
_folder_map = {}


def register_folder(token, folder):
    if folder:
        _folder_map[int(token)] = str(folder).strip()


def register_folders(mapping):
    """Bulk version of register_folder({token: folder, ...})."""
    for token, folder in mapping.items():
        register_folder(token, folder)


_buffer = []
_lock = threading.Lock()

_DEPTH_SIDES = ("buy", "sell")


def _flatten_depth(tick):
    row = {}
    depth = tick.get("depth") or {}
    for side in _DEPTH_SIDES:
        levels = depth.get(side) or []
        for i in range(5):
            level = levels[i] if i < len(levels) else {}
            row[f"{side}_price_{i+1}"] = level.get("price")
            row[f"{side}_qty_{i+1}"] = level.get("quantity")
            row[f"{side}_orders_{i+1}"] = level.get("orders")
    return row


def record_tick(tick):
    """Flatten a raw KiteTicker Full-mode tick dict (incl. depth) and buffer it for the next flush."""
    ohlc = tick.get("ohlc") or {}
    row = {
        "instrument_token": tick.get("instrument_token"),
        "ltp": tick.get("last_price"),
        "last_traded_qty": tick.get("last_traded_quantity"),
        "avg_traded_price": tick.get("average_traded_price"),
        "volume_traded": tick.get("volume_traded") if tick.get("volume_traded") is not None else tick.get("volume"),
        "buy_qty": tick.get("total_buy_quantity"),
        "sell_qty": tick.get("total_sell_quantity"),
        "ohlc_open": ohlc.get("open"),
        "ohlc_high": ohlc.get("high"),
        "ohlc_low": ohlc.get("low"),
        "ohlc_close": ohlc.get("close"),
        "change": tick.get("change"),
        "oi": tick.get("oi"),
        "oi_day_high": tick.get("oi_day_high"),
        "oi_day_low": tick.get("oi_day_low"),
        "last_trade_time": tick.get("last_trade_time"),
        "exchange_timestamp": tick.get("exchange_timestamp") or tick.get("timestamp"),
        "ingest_ts": time.time(),
    }
    row.update(_flatten_depth(tick))

    with _lock:
        _buffer.append(row)


_INT32_COLS = [
    "instrument_token", "last_traded_qty", "volume_traded", "buy_qty", "sell_qty",
    "oi", "oi_day_high", "oi_day_low",
] + [f"{side}_qty_{i+1}" for side in _DEPTH_SIDES for i in range(5)] \
  + [f"{side}_orders_{i+1}" for side in _DEPTH_SIDES for i in range(5)]

_FLOAT64_COLS = [
    "ltp", "avg_traded_price", "ohlc_open", "ohlc_high", "ohlc_low", "ohlc_close", "change",
] + [f"{side}_price_{i+1}" for side in _DEPTH_SIDES for i in range(5)]


def _jsonl_path(date_str):
    return os.path.join(LIVE_DIR, f"{date_str}.jsonl")


def _json_default(o):
    # last_trade_time / exchange_timestamp arrive as datetime objects from
    # KiteTicker - not natively JSON serializable, so encode as ISO-8601.
    # DuckDB casts these back to TIMESTAMP at EOD conversion time.
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def _flush():
    """Append the buffered ticks as JSON lines to today's live file. Parquet
    conversion + GCS upload happens once, end-of-day, via _convert_and_upload() -
    not on every flush like before."""
    with _lock:
        if not _buffer:
            return
        rows = _buffer[:]
        _buffer.clear()

    for row in rows:
        token = int(row["instrument_token"])
        row["symbol"] = _symbol_map.get(token, str(token))
        row["_bucket"] = _folder_map.get(token, row["symbol"])

    now = time.localtime()
    date_str = time.strftime("%Y-%m-%d", now)
    os.makedirs(LIVE_DIR, exist_ok=True)
    path = _jsonl_path(date_str)
    lines = "\n".join(json.dumps(row, default=_json_default) for row in rows) + "\n"
    with open(path, "a") as f:
        f.write(lines)

    tokens = {r["instrument_token"] for r in rows}
    print(f"[tick_store] flushed {len(rows)} ticks across {len(tokens)} instruments -> {path}")


def _trim_last_line_if_needed(path):
    """Best-effort crash recovery: if the file's last line isn't valid JSON
    (the process died mid-write), drop just that line and keep everything
    before it - every prior line was already a complete, flushed write()."""
    with open(path, "rb") as f:
        content = f.read()
    if not content:
        return
    lines = content.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    if not lines:
        return
    try:
        json.loads(lines[-1])
        return  # last line is fine - the read error was something else
    except Exception:
        pass
    with open(path, "wb") as f:
        f.write(b"\n".join(lines[:-1]) + (b"\n" if len(lines) > 1 else b""))
    print(f"[tick_store] dropped a torn last line from {path}")


def _build_select_clause():
    """SELECT list that types every column explicitly (TRY_CAST - never
    errors the whole conversion on one bad value, just nulls it) rather than
    trusting DuckDB's auto-inference on a JSON file that may have all-null
    columns for some instruments (e.g. OI is always null for the spot index)."""
    parts = []
    for c in _INT32_COLS:
        parts.append(f'TRY_CAST("{c}" AS INTEGER) AS "{c}"')
    for c in _FLOAT64_COLS:
        parts.append(f'TRY_CAST("{c}" AS DOUBLE) AS "{c}"')
    parts.append('TRY_CAST("ingest_ts" AS DOUBLE) AS "ingest_ts"')
    parts.append('TRY_CAST("last_trade_time" AS TIMESTAMP) AS "last_trade_time"')
    parts.append('TRY_CAST("exchange_timestamp" AS TIMESTAMP) AS "exchange_timestamp"')
    parts.append('"symbol"')
    return ", ".join(parts)


def _convert_and_upload(date_str):
    """Read the day's JSONL, split by _bucket (the stable output key), write
    one snappy parquet per instrument, upload each to GCS. Returns True only
    if every instrument converted+uploaded successfully - a False return
    leaves the day unmarked so the next flush-loop tick retries the whole
    thing (safe: GCS uploads overwrite, and the JSONL source isn't touched
    until _prune_retention() confirms success separately)."""
    import duckdb

    path = _jsonl_path(date_str)
    if not os.path.exists(path):
        return True  # nothing captured that day (e.g. a holiday) - trivially done

    year, month, day = date_str.split("-")
    con = duckdb.connect()

    def _load():
        con.execute(f"CREATE OR REPLACE TEMP TABLE _ticks AS SELECT * FROM read_json_auto('{path}')")

    try:
        _load()
    except Exception as e:
        print(f"[tick_store] EOD: JSONL read failed ({e}) - retrying after trimming a possible torn last line")
        _trim_last_line_if_needed(path)
        _load()

    buckets = [r[0] for r in con.execute(
        'SELECT DISTINCT "_bucket" FROM _ticks WHERE "_bucket" IS NOT NULL'
    ).fetchall()]
    if not buckets:
        con.close()
        print(f"[tick_store] EOD: no instruments found in {path}")
        return True

    out_dir = os.path.join(ARCHIVE_DIR, date_str)
    os.makedirs(out_dir, exist_ok=True)
    select_clause = _build_select_clause()

    all_ok = True
    for bucket in buckets:
        out_path = os.path.join(out_dir, f"{bucket}.parquet")
        try:
            con.execute(
                f'COPY (SELECT {select_clause} FROM _ticks WHERE "_bucket" = ?) '
                f"TO '{out_path}' (FORMAT PARQUET, COMPRESSION SNAPPY)",
                [bucket],
            )
            gcs_upload.upload_file(out_path, year, month, day, f"{bucket}.parquet", dataset=DATASET)
        except Exception as e:
            print(f"[tick_store] EOD: failed for {bucket}: {e}")
            all_ok = False

    con.close()
    print(f"[tick_store] EOD: converted {len(buckets)} instruments for {date_str} -> {out_dir}/ (all_ok={all_ok})")
    return all_ok


def _dir_size_bytes(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _prune_stale_jsonl():
    """Delete a day's raw JSONL only once its parquet conversion is confirmed
    on disk AND it's at least JSONL_BUFFER_DAYS old - a short safety buffer
    against a conversion bug, per the retention plan (parquet is the
    long-term copy, not the raw JSONL)."""
    if not os.path.isdir(LIVE_DIR):
        return
    cutoff = market_calendar.now_ist().date() - timedelta(days=JSONL_BUFFER_DAYS)
    for fname in os.listdir(LIVE_DIR):
        if not fname.endswith(".jsonl"):
            continue
        date_str = fname[: -len(".jsonl")]
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date > cutoff:
            continue
        archive_day_dir = os.path.join(ARCHIVE_DIR, date_str)
        if os.path.isdir(archive_day_dir) and os.listdir(archive_day_dir):
            os.remove(os.path.join(LIVE_DIR, fname))
            print(f"[tick_store] pruned converted JSONL: {fname}")


def _prune_archive():
    """Local parquet archive retention: delete day-folders older than
    RETENTION_DAYS, then (if still over RETENTION_MAX_BYTES) delete
    remaining day-folders oldest-first until under the cap."""
    if not os.path.isdir(ARCHIVE_DIR):
        return
    day_dirs = sorted(
        d for d in os.listdir(ARCHIVE_DIR) if os.path.isdir(os.path.join(ARCHIVE_DIR, d))
    )  # YYYY-MM-DD names sort lexicographically == chronologically
    today = market_calendar.now_ist().date()

    remaining = []
    for d in day_dirs:
        try:
            day_date = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            remaining.append(d)
            continue
        if (today - day_date).days > RETENTION_DAYS:
            shutil.rmtree(os.path.join(ARCHIVE_DIR, d), ignore_errors=True)
            print(f"[tick_store] pruned archive day (age > {RETENTION_DAYS}d): {d}")
        else:
            remaining.append(d)

    total = _dir_size_bytes(ARCHIVE_DIR)
    i = 0
    while total > RETENTION_MAX_BYTES and i < len(remaining):
        d = remaining[i]
        size = _dir_size_bytes(os.path.join(ARCHIVE_DIR, d))
        shutil.rmtree(os.path.join(ARCHIVE_DIR, d), ignore_errors=True)
        total -= size
        print(f"[tick_store] pruned archive day (10GB size cap): {d} (-{size/1e6:.1f}MB)")
        i += 1


def _prune_retention():
    _prune_stale_jsonl()
    _prune_archive()


_last_eod_date = None


def _maybe_run_eod():
    """Checked every flush-loop tick; only does real work once per day, at
    market close + EOD_BUFFER_MINUTES. A failed conversion leaves the date
    unmarked so it retries on the next tick."""
    global _last_eod_date
    now = market_calendar.now_ist()
    if now.time() < market_calendar.eod_trigger_time():
        return
    today_str = now.strftime("%Y-%m-%d")
    if _last_eod_date == today_str:
        return
    ok = _convert_and_upload(today_str)
    if ok:
        _last_eod_date = today_str
        _prune_retention()


def start_flush_thread(interval_sec=30):
    def loop():
        while True:
            time.sleep(interval_sec)
            try:
                _flush()
            except Exception as e:
                print(f"[tick_store] flush failed: {e}")
            try:
                _maybe_run_eod()
            except Exception as e:
                print(f"[tick_store] EOD check failed: {e}")

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
    return thread
