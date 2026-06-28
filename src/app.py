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

def build_chart_data(interval):
    name = INTERVAL_NAME_MAP.get(interval, "15m")
    candles = read_candles(name, limit=500)
    if not candles:
        # fallback to Kite historical data if Parquet store is empty (e.g. fresh start)
        candles = get_historical_data(interval=interval, days=INTERVAL_DAYS.get(interval, 30))
        for cd in candles:
            cd["time"] = int(cd["date"].timestamp())
    df = calculate_supertrend(candles)
    out = []
    for _, row in df.iterrows():
        out.append({
            "time": int(row["date"].timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "supertrend": None if pd.isna(row["supertrend"]) else float(row["supertrend"]),
            "direction": None if pd.isna(row["direction"]) else int(row["direction"]),
            "signal": row["signal"] if row["signal"] else None
        })
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

@socketio.on("connect")
def handle_connect():
    print("Client connected!")
    data = build_chart_data(current_interval)
    emit("historical_data", data)

@socketio.on("change_interval")
def handle_interval(payload):
    global current_interval
    current_interval = payload["interval"]
    print(f"Interval changed to {current_interval}")
    data = build_chart_data(current_interval)
    emit("historical_data", data)

if __name__ == "__main__":
    thread = threading.Thread(target=start_ticker)
    thread.daemon = True
    thread.start()
    socketio.run(app, debug=False, port=5001, allow_unsafe_werkzeug=True)
