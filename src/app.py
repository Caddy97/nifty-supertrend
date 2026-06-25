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

def start_ticker():
    kite = get_kite()
    access_token = kite.access_token

    while True:
        try:
            kws = KiteTicker(API_KEY, access_token)

            def on_ticks(ws, ticks):
                print(f"DEBUG: received {len(ticks)} tick(s)")
                for t in ticks:
                    print(f"DEBUG: token={t['instrument_token']} price={t['last_price']}")
                    if t["instrument_token"] == NIFTY_TOKEN:
                        print(f"DEBUG: emitting live_price {t['last_price']}")
                        socketio.emit("live_price", {"price": t["last_price"]}, namespace="/")

            def on_connect(ws, response):
                print("Kite ticker connected!")
                ws.subscribe([NIFTY_TOKEN])
                ws.set_mode(ws.MODE_FULL, [NIFTY_TOKEN])

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
