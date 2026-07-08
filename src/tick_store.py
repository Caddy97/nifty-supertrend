import os
import threading
import time
import pandas as pd

import gcs_upload

DATA_DIR = "data/ticks"

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


def _flush():
    with _lock:
        if not _buffer:
            return
        rows = _buffer[:]
        _buffer.clear()

    df = pd.DataFrame(rows)
    for col in _INT32_COLS:
        if col in df.columns:
            df[col] = df[col].astype("Int32")
    for col in _FLOAT64_COLS:
        if col in df.columns:
            df[col] = df[col].astype("float64")

    now = time.localtime()
    year, month, day = time.strftime("%Y", now), time.strftime("%m", now), time.strftime("%d", now)
    out_dir = os.path.join(DATA_DIR, f"{year}-{month}-{day}")
    os.makedirs(out_dir, exist_ok=True)
    hhmmss = time.strftime("%H%M%S", now)
    for token, group in df.groupby("instrument_token"):
        filename = f"{token}_{hhmmss}.parquet"
        path = os.path.join(out_dir, filename)
        group.to_parquet(path, index=False)
        gcs_upload.upload_file(path, year, month, day, filename)
    print(f"[tick_store] flushed {len(df)} ticks across {df['instrument_token'].nunique()} instruments -> {out_dir}/")


def start_flush_thread(interval_sec=30):
    def loop():
        while True:
            time.sleep(interval_sec)
            try:
                _flush()
            except Exception as e:
                print(f"[tick_store] flush failed: {e}")

    thread = threading.Thread(target=loop)
    thread.daemon = True
    thread.start()
    return thread
