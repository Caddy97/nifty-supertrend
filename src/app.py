import threading
import time
import pandas as pd
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from kiteconnect import KiteTicker
import os
from dotenv import load_dotenv

from auth import get_kite
from data import get_historical_data
from supertrend import calculate_supertrend
from candle_reader import read_candles
from market_calendar import is_market_open, market_status
from strike_selector import get_atm_strike
from option_lookup import get_monthly_option_token
from black_scholes import black_scholes_price
from vix_data import get_vix_history, get_vix_on_date
from telegram_bot import send_signal_alert

load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")
NIFTY_TOKEN = 256265

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

current_interval = "15minute"

INTERVAL_DAYS = {
    "5minute": 15,
    "15minute": 30,
    "60minute": 90,
}

INTERVAL_NAME_MAP = {"5minute": "5m", "15minute": "15m", "60minute": "1h"}

INTERVAL_SECONDS = {"5minute": 300, "15minute": 900, "60minute": 3600}

last_acted_signal = {"time": None}

def build_chart_data(interval):
    name = INTERVAL_NAME_MAP.get(interval, "15m")

    # Always fetch full history from Kite (covers the configured window)
    kite_candles = get_historical_data(interval=interval, days=INTERVAL_DAYS.get(interval, 30))
    merged = {}
    for cd in kite_candles:
        t = int(cd["date"].timestamp())
        merged[t] = {"time": t, "open": cd["open"], "high": cd["high"], "low": cd["low"], "close": cd["close"]}

    # Overlay with parquet-accumulated candles — captures the live-forming candle
    # and any ticks not yet reflected in Kite's API response
    for cd in read_candles(name, limit=500):
        merged[cd["time"]] = cd

    candles = sorted(merged.values(), key=lambda x: x["time"])
    if not candles:
        return []

    df = calculate_supertrend(candles)
    out = []
    for _, row in df.iterrows():
        # Parquet candles have "time" only; Kite-fallback candles have both "date" and "time".
        # Always use "time" (already a unix int) - never rely on "date" being present.
        row_time = int(row["time"])
        out.append({
            "time": row_time,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "supertrend": None if pd.isna(row["supertrend"]) else float(row["supertrend"]),
            "direction": None if pd.isna(row["direction"]) else int(row["direction"]),
            "signal": row["signal"] if row["signal"] else None
        })

    if out:
        last = out[-1]
        if last["signal"] and last["time"] != last_acted_signal["time"]:
            side = last["signal"]
            spot = last["close"]
            strike = get_atm_strike(spot)
            opt_type = "CE" if side == "BUY" else "PE"
            info = get_monthly_option_token(strike, opt_type)
            if info:
                set_active_option(info["instrument_token"], info["tradingsymbol"])
                last_acted_signal["time"] = last["time"]
                print(f"New {side} signal -> tracking {info['tradingsymbol']}")
                try:
                    vix_df = get_vix_history(period="5d")
                    from datetime import datetime
                    vix_pct = get_vix_on_date(vix_df, datetime.now())
                    vol = (vix_pct / 100.0) if vix_pct else 0.15
                    from contract_specs import LOT_SIZE
                    from trading_days import trading_days_between
                    from premium_backtest import get_monthly_expiry
                    expiry = get_monthly_expiry(datetime.now())
                    dte = (expiry - datetime.now()).days
                    premium = black_scholes_price(spot, strike, max(dte, 0), vol, opt_type)
                    send_signal_alert(side, spot, strike, opt_type, info["tradingsymbol"], premium)
                except Exception as e:
                    print(f"Telegram alert failed: {e}")

    return out

active_option_token = None
active_option_symbol = None
ws_ref = None

def set_active_option(token, symbol):
    """Called when a new option position opens - swaps the live subscription."""
    global active_option_token, active_option_symbol
    if ws_ref and active_option_token and active_option_token != token:
        try:
            ws_ref.unsubscribe([active_option_token])
        except Exception:
            pass
    active_option_token = token
    active_option_symbol = symbol
    if ws_ref and token:
        ws_ref.subscribe([token])
        ws_ref.set_mode(ws_ref.MODE_FULL, [token])
        print(f"Now tracking live option: {symbol} (token {token})")

def start_ticker():
    global ws_ref
    kite = get_kite()
    access_token = kite.access_token

    while True:
        try:
            kws = KiteTicker(API_KEY, access_token)
            ws_ref = kws

            def on_ticks(ws, ticks):
                for t in ticks:
                    if t["instrument_token"] == NIFTY_TOKEN:
                        socketio.emit("live_price", {"price": t["last_price"]}, namespace="/")
                    elif active_option_token and t["instrument_token"] == active_option_token:
                        socketio.emit("live_option_price", {"price": t["last_price"], "symbol": active_option_symbol}, namespace="/")

            def on_connect(ws, response):
                print("Kite ticker connected!")
                ws.subscribe([NIFTY_TOKEN])
                ws.set_mode(ws.MODE_FULL, [NIFTY_TOKEN])
                if active_option_token:
                    ws.subscribe([active_option_token])
                    ws.set_mode(ws.MODE_FULL, [active_option_token])

            def on_close(ws, code, reason):
                print(f"Ticker closed: {code} {reason}")

            def on_error(ws, code, reason):
                print(f"Ticker error: {code} {reason}")

            kws.on_ticks = on_ticks
            kws.on_connect = on_connect
            kws.on_close = on_close
            kws.on_error = on_error
            kws.connect(threaded=False)
        except Exception as e:

            print(f"Ticker crashed: {e}")
        print("Reconnecting ticker in 5s...")
        time.sleep(5)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/market_status")
def api_market_status():
    return {"status": market_status(), "is_open": is_market_open()}

_chart_cache = {}

def refresh_chart_cache(interval):
    import traceback
    try:
        _chart_cache[interval] = build_chart_data(interval)
        print(f"Chart cache refreshed for {interval}: {len(_chart_cache[interval])} rows")
    except Exception as e:
        print(f"Failed to refresh chart cache for {interval}: {e}")
        traceback.print_exc()

@socketio.on("connect")
def handle_connect(auth=None):
    print("Client connected!")
    refresh_chart_cache(current_interval)  # always get fresh data, never trust a stale cache
    emit("historical_data", _chart_cache.get(current_interval, []))

@socketio.on("change_interval")
def handle_interval(payload):
    global current_interval
    current_interval = payload["interval"]
    print(f"Interval changed to {current_interval}")
    data = build_chart_data(current_interval)
    emit("historical_data", data)

def chart_refresh_loop():
    """Wakes up at each candle boundary for the current interval and pushes fresh data to all clients."""
    while True:
        interval = current_interval
        period = INTERVAL_SECONDS.get(interval, 900)
        now = time.time()
        # sleep until the next candle boundary + a small buffer for the candle to be written
        next_boundary = (int(now / period) + 1) * period + 5
        time.sleep(max(0, next_boundary - time.time()))

        if not is_market_open():
            continue

        refresh_chart_cache(current_interval)
        data = _chart_cache.get(current_interval, [])
        if data:
            socketio.emit("historical_data", data, namespace="/")
            print(f"Auto-pushed chart refresh ({current_interval}): {len(data)} candles")


if __name__ == "__main__":
    print("Authenticating with Kite (one-time, before starting server)...")
    get_kite()
    print("Pre-warming chart cache before accepting connections...")
    refresh_chart_cache(current_interval)
    print("Cache ready. Starting ticker and server...")

    thread = threading.Thread(target=start_ticker)
    thread.daemon = True
    thread.start()

    refresh_thread = threading.Thread(target=chart_refresh_loop)
    refresh_thread.daemon = True
    refresh_thread.start()

    socketio.run(app, debug=False, port=5001, allow_unsafe_werkzeug=True)
