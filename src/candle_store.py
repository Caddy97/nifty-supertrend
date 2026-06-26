import os
import time
import pandas as pd
from kiteconnect import KiteTicker
from auth import get_kite
from market_calendar import is_market_open, market_status
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("KITE_API_KEY")
NIFTY_TOKEN = 256265
DATA_DIR = "data"

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
buckets = {name: None for name in INTERVALS}

def parquet_path(name):
    return os.path.join(DATA_DIR, f"nifty_{name}.parquet")

def append_candle(name, candle):
    path = parquet_path(name)
    row = pd.DataFrame([candle])
    if os.path.exists(path):
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, row], ignore_index=True)
    else:
        combined = row
    combined.to_parquet(path, index=False)
    print(f"[{name}] candle closed: {candle}")

def on_tick(price, ts):
    for name, secs in INTERVALS.items():
        bucket_time = (ts // secs) * secs
        cur = buckets[name]
        if cur is None:
            buckets[name] = {"time": bucket_time, "open": price, "high": price, "low": price, "close": price}
        elif bucket_time > cur["time"]:
            append_candle(name, cur)
            buckets[name] = {"time": bucket_time, "open": cur["close"], "high": price, "low": price, "close": price}
        else:
            cur["close"] = price
            cur["high"] = max(cur["high"], price)
            cur["low"] = min(cur["low"], price)

def start():
    kite = get_kite()
    access_token = kite.access_token
    while True:
        try:
            kws = KiteTicker(API_KEY, access_token)

            def on_ticks(ws, ticks):
                for t in ticks:
                    if t["instrument_token"] == NIFTY_TOKEN:
                        ts = int(time.time())
                        on_tick(t["last_price"], ts)

            def on_connect(ws, response):
                print(f"Candle accumulator connected to Kite. Market status: {market_status()}")
                ws.subscribe([NIFTY_TOKEN])
                ws.set_mode(ws.MODE_FULL, [NIFTY_TOKEN])

            def on_close(ws, code, reason):
                print(f"Closed: {code} {reason}")

            def on_error(ws, code, reason):
                print(f"Error: {code} {reason}")

            kws.on_ticks = on_ticks
            kws.on_connect = on_connect
            kws.on_close = on_close
            kws.on_error = on_error
            kws.connect(threaded=False)
        except Exception as e:
            print(f"Accumulator crashed: {e}")
        print("Reconnecting in 5s...")
        time.sleep(5)

if __name__ == "__main__":
    start()
