"""
Standalone options-chain tick capture.

Subscribes to a fixed slice of the NIFTY universe and archives every full-mode
tick (incl. 5-level market depth) via tick_store — the same buffering / 30s
flush / parquet / GCS-mirror path the main app already uses.

Captured instruments (24 total):
  - NIFTY 50 spot index          (token 256265)
  - NIFTY nearest-expiry FUTURE  (monthly — no weekly NIFTY futures exist)
  - 11 CE strikes: ATM and 5 above + 5 below
  - 11 PE strikes: ATM and 5 above + 5 below

Runs as its own process with its own Kite session and WebSocket connection,
mirroring candle_store.py. Start it after the daily Kite login.
"""

import os
import time
import threading
from pathlib import Path
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from kiteconnect import KiteTicker

from auth import get_kite
from market_calendar import is_market_open, market_status
import tick_store

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("KITE_API_KEY")

NIFTY_TOKEN = 256265            # NIFTY 50 spot index
NIFTY_LTP_KEY = "NSE:NIFTY 50"  # for centering strikes on live spot

# ── Capture config (change these to adjust the captured slice) ────────────────
NUM_STRIKES_EACH_SIDE = 5       # 5 above + 5 below + ATM = 11 strikes per side
OPTION_EXPIRY_MODE = "weekly"   # "weekly" = nearest expiry, "monthly" = nearest monthly
FUTURE_EXPIRY_MODE = "monthly"  # NIFTY futures are monthly only


def _target_expiry(expiries, mode):
    """Pick the target expiry Timestamp from a set of future expiries."""
    future = sorted(e for e in expiries if e >= pd.Timestamp(datetime.now().date()))
    if not future:
        return None
    if mode == "weekly":
        return future[0]                       # nearest expiry overall
    # monthly: nearest month, its latest (monthly) expiry
    nearest_month = min(future).to_period("M")
    same_month = [e for e in future if e.to_period("M") == nearest_month]
    return max(same_month)


def resolve_instruments(kite):
    """Resolve the 24 instruments to subscribe. Returns (tokens, meta, symbols, folders, info):
      - meta:    token -> display label incl. tags like "ATM", for logging
      - symbols: token -> real tradingsymbol (e.g. "NIFTY2671424200CE"), stored as the
                 `symbol` column inside each row — the true, expiry-specific identity.
      - folders: token -> stable, query-friendly grouping key used for the storage path
                 (e.g. "24200_CE", "NIFTY_SPOT", "NIFTY_FUT") — deliberately decoupled
                 from the tradingsymbol's cryptic weekly-expiry encoding. Unambiguous
                 within a single day= partition, since only one contract per
                 strike+type is ever active on a given day.
    """
    instruments = pd.DataFrame(kite.instruments("NFO"))
    instruments["expiry"] = pd.to_datetime(instruments["expiry"])
    nifty = instruments[instruments["name"] == "NIFTY"]

    # --- nearest future ---
    futs = nifty[nifty["instrument_type"] == "FUT"]
    fut_expiry = _target_expiry(set(futs["expiry"]), FUTURE_EXPIRY_MODE)
    fut_row = futs[futs["expiry"] == fut_expiry].iloc[0] if fut_expiry is not None else None

    # --- options for the target expiry ---
    opts = nifty[nifty["instrument_type"].isin(["CE", "PE"])]
    opt_expiry = _target_expiry(set(opts["expiry"]), OPTION_EXPIRY_MODE)
    opts = opts[opts["expiry"] == opt_expiry]

    # centre strikes on live spot
    spot = kite.ltp([NIFTY_LTP_KEY])[NIFTY_LTP_KEY]["last_price"]

    strikes = sorted(opts["strike"].unique())
    # index of the strike nearest to spot
    atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    lo = max(0, atm_idx - NUM_STRIKES_EACH_SIDE)
    hi = min(len(strikes), atm_idx + NUM_STRIKES_EACH_SIDE + 1)
    selected_strikes = strikes[lo:hi]

    tokens = [NIFTY_TOKEN]
    meta = {NIFTY_TOKEN: "NIFTY50-SPOT"}
    symbols = {NIFTY_TOKEN: "NIFTY50-SPOT"}  # index has no real tradingsymbol; use the same clean label
    folders = {NIFTY_TOKEN: "NIFTY_SPOT"}

    if fut_row is not None:
        t = int(fut_row["instrument_token"])
        tokens.append(t)
        symbols[t] = fut_row["tradingsymbol"]
        folders[t] = "NIFTY_FUT"
        meta[t] = f"{fut_row['tradingsymbol']} (FUT {fut_expiry.date()})"

    for strike in selected_strikes:
        for opt_type in ("CE", "PE"):
            match = opts[(opts["strike"] == strike) & (opts["instrument_type"] == opt_type)]
            if match.empty:
                continue
            row = match.iloc[0]
            t = int(row["instrument_token"])
            tokens.append(t)
            symbols[t] = row["tradingsymbol"]
            folders[t] = f"{int(strike)}_{opt_type}"
            tag = "ATM" if strike == strikes[atm_idx] else ""
            meta[t] = f"{row['tradingsymbol']} {tag}".strip()

    return tokens, meta, symbols, folders, {
        "spot": spot,
        "opt_expiry": str(opt_expiry.date()) if opt_expiry is not None else None,
        "fut_expiry": str(fut_expiry.date()) if fut_expiry is not None else None,
        "atm_strike": strikes[atm_idx],
        "n_strikes": len(selected_strikes),
    }


def start():
    kite = get_kite()
    access_token = kite.access_token

    tokens, meta, symbols, folders, info = resolve_instruments(kite)
    print(f"[options_chain] Market: {market_status()}")
    print(f"[options_chain] Spot {info['spot']}  ATM {info['atm_strike']}  "
          f"opt-expiry {info['opt_expiry']}  fut-expiry {info['fut_expiry']}")
    print(f"[options_chain] Subscribing to {len(tokens)} instruments:")
    for t in tokens:
        print(f"    {t:>10}  {meta[t]}  ->  {folders[t]}/<HHMMSS>.parquet")

    # Write to a separate namespace so this never collides with the dashboard's
    # own tick archive (app.py uses the default "ticks" dataset).
    tick_store.set_dataset("options_chain")
    tick_store.register_symbols(symbols)
    tick_store.register_folders(folders)
    tick_store.start_flush_thread()

    while True:
        try:
            kws = KiteTicker(API_KEY, access_token)

            def on_ticks(ws, ticks):
                for t in ticks:
                    tick_store.record_tick(t)

            def on_connect(ws, response):
                print(f"[options_chain] Connected. Subscribing {len(tokens)} tokens in FULL mode.")
                ws.subscribe(tokens)
                ws.set_mode(ws.MODE_FULL, tokens)

            def on_close(ws, code, reason):
                print(f"[options_chain] Closed: {code} {reason}")

            def on_error(ws, code, reason):
                print(f"[options_chain] Error: {code} {reason}")

            kws.on_ticks = on_ticks
            kws.on_connect = on_connect
            kws.on_close = on_close
            kws.on_error = on_error
            kws.connect(threaded=False)
        except Exception as e:
            print(f"[options_chain] Crashed: {e}")
        print("[options_chain] Reconnecting in 5s...")
        time.sleep(5)


if __name__ == "__main__":
    start()
