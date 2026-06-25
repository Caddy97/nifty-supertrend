from kiteconnect import KiteTicker
from auth import get_kite
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")

NIFTY_TOKEN = 256265

kite = get_kite()
access_token = kite.access_token

kws = KiteTicker(API_KEY, access_token)

def on_ticks(ws, ticks):
    for t in ticks:
        print(f"LTP: {t['last_price']}  |  Token: {t['instrument_token']}")

def on_connect(ws, response):
    print("Connected! Subscribing to Nifty 50...")
    ws.subscribe([NIFTY_TOKEN])
    ws.set_mode(ws.MODE_FULL, [NIFTY_TOKEN])

def on_close(ws, code, reason):
    print(f"Connection closed: {code} {reason}")

def on_error(ws, code, reason):
    print(f"Error: {code} {reason}")

kws.on_ticks = on_ticks
kws.on_connect = on_connect
kws.on_close = on_close
kws.on_error = on_error

print("Connecting to Kite WebSocket...")
kws.connect()
