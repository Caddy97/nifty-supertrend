import threading
import time
import pandas as pd
from flask import Flask, render_template, request, redirect, session, url_for
from functools import wraps
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
from telegram_bot import send_signal_alert, send_exit_alert
from paper_trades import init_db, open_trade, close_open_trade, get_open_trade, get_open_trades, close_trade_by_id, get_trade_history

load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")
NIFTY_TOKEN = 256265

DASHBOARD_USER = os.getenv("DASHBOARD_USER", "vishal")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "nifty2026")

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv("SECRET_KEY", "nifty-supertrend-secret-2026")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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
            last_acted_signal["time"] = last["time"]
            if info:
                set_active_option(info["instrument_token"], info["tradingsymbol"])
            print(f"New {side} signal @ {spot}")
            try:
                kite_inst = get_kite()

                def get_live_price(tradingsymbol):
                    try:
                        key = f"NFO:{tradingsymbol}"
                        q = kite_inst.quote([key])
                        price = q[key]["last_price"]
                        return price if price and price > 0 else None
                    except Exception as ex:
                        print(f"Quote failed for {tradingsymbol}: {ex}")
                        return None

                # Close all existing open trades if signal reversed
                for existing in get_open_trades():
                    if existing["side"] != side:
                        if existing.get("trade_type") == "FUT":
                            exit_price = spot
                        else:
                            exit_price = get_live_price(existing["symbol"]) or existing["entry_premium"]
                        result = close_trade_by_id(existing["id"], spot, exit_price, "signal")
                        if result:
                            send_exit_alert(existing["side"], spot, existing["symbol"],
                                            existing["entry_premium"], exit_price)
                socketio.emit("trade_history", get_trade_history(), namespace="/")

                # 1. Open Futures paper trade at spot price
                open_trade(side, "FUT", 0, "NIFTY-FUT", spot, spot, trade_type="FUT")

                # 2. Open Option paper trade at live Kite quote
                if info:
                    opt_premium = get_live_price(info["tradingsymbol"])
                    if opt_premium:
                        open_trade(side, opt_type, strike, info["tradingsymbol"], spot, opt_premium, trade_type="OPT")
                    else:
                        print(f"Live quote unavailable for {info['tradingsymbol']}, skipping OPT trade")

                send_signal_alert(side, spot, strike, opt_type,
                                  info["tradingsymbol"] if info else "N/A",
                                  get_live_price(info["tradingsymbol"]) if info else 0)
                socketio.emit("trade_history", get_trade_history(), namespace="/")
            except Exception as e:
                print(f"Paper trade / Telegram error: {e}")

    return out

active_option_token = None
active_option_symbol = None
ws_ref = None

# In-memory forming candle per interval (updated tick by tick)
_forming = {}   # { "5minute": {time, open, high, low, close}, ... }

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

def _update_forming(price):
    ts = int(time.time())
    for interval, secs in INTERVAL_SECONDS.items():
        bucket = (ts // secs) * secs
        cur = _forming.get(interval)
        if cur is None or cur["time"] != bucket:
            _forming[interval] = {"time": bucket, "open": price, "high": price, "low": price, "close": price}
        else:
            cur["close"] = price
            cur["high"]  = max(cur["high"], price)
            cur["low"]   = min(cur["low"],  price)
        socketio.emit("tick_update", {"interval": interval, "candle": _forming[interval]}, namespace="/")


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
                        price = t["last_price"]
                        socketio.emit("live_price", {"price": price}, namespace="/")
                        _update_forming(price)
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
    refresh_chart_cache(current_interval)
    emit("historical_data", _chart_cache.get(current_interval, []))
    emit("trade_history", get_trade_history())
    # Emit last known option price on connect (shows closing price after hours)
    try:
        opt_trades = [t for t in get_open_trades() if t.get("trade_type") == "OPT"]
        sym = active_option_symbol or (opt_trades[0]["symbol"] if opt_trades else None)
        if sym:
            kite_inst = get_kite()
            key = f"NFO:{sym}"
            q = kite_inst.quote([key])
            price = q[key]["last_price"]
            if price and price > 0:
                emit("live_option_price", {"price": price, "symbol": sym})
    except Exception:
        pass

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
    init_db()
    print("Pre-warming chart cache before accepting connections...")
    refresh_chart_cache(current_interval)
    print("Cache ready. Starting ticker and server...")

    thread = threading.Thread(target=start_ticker)
    thread.daemon = True
    thread.start()

    refresh_thread = threading.Thread(target=chart_refresh_loop)
    refresh_thread.daemon = True
    refresh_thread.start()

    socketio.run(app, debug=False, host="0.0.0.0", port=5001, allow_unsafe_werkzeug=True)
