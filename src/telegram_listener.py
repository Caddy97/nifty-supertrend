import os
import sys
import time
import requests
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from kiteconnect import KiteConnect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telegram_bot import send_eod_summary
from paper_trades import get_trade_history

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# TELEGRAM_CHAT_ID may now be a comma-separated list (personal + friends' group)
# for signal broadcasts, but login/admin commands must stay restricted to the
# owner - always the first ID in that list.
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").split(",")[0].strip()
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
TOKEN_FILE = BASE_DIR / "access_token.txt"
IST = timezone(timedelta(hours=5, minutes=30))

last_update_id = 0
login_url_sent_date = None
eod_sent_date = None


def send_message(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram send error: {e}")


def send_login_url():
    kite = KiteConnect(api_key=API_KEY)
    url = kite.login_url()
    send_message(
        f"<b>Good Morning! Daily Kite Login</b>\n\n"
        f"1. Click the link below to login:\n{url}\n\n"
        f"2. After login, copy the <b>full redirect URL</b> from browser address bar\n"
        f"3. Paste it here in this chat"
    )
    print("Sent morning login URL to Telegram")


def process_redirect_url(text):
    try:
        if "request_token=" in text:
            request_token = text.split("request_token=")[1].split("&")[0]
        else:
            request_token = text.strip()

        kite = KiteConnect(api_key=API_KEY)
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = data["access_token"]

        with open(TOKEN_FILE, "w") as f:
            f.write(access_token)

        send_message(
            f"<b>Login Successful!</b>\n"
            f"User  : {data['user_name']} ({data['user_id']})\n"
            f"Token valid until midnight.\n"
            f"Restarting dashboard..."
        )

        subprocess.run(["sudo", "systemctl", "restart", "nifty"], check=True)
        send_message("Dashboard restarted successfully.")
        print(f"Token saved, app restarted for {data['user_name']}")

    except Exception as e:
        send_message(f"Login failed: {e}")
        print(f"Token processing error: {e}")


def init_offset():
    global last_update_id
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"limit": 1, "offset": -1},
            timeout=10
        )
        results = resp.json().get("result", [])
        if results:
            last_update_id = results[-1]["update_id"]
    except Exception:
        pass


def poll_updates():
    global last_update_id
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 30},
            timeout=35
        )
        for update in resp.json().get("result", []):
            last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if chat_id != CHAT_ID:
                continue

            print(f"Received: {text[:80]}")

            if text.lower() == "/login":
                send_login_url()
            elif text.lower() == "/status":
                result = subprocess.run(
                    ["sudo", "systemctl", "is-active", "nifty"],
                    capture_output=True, text=True
                )
                send_message(f"Dashboard status: <b>{result.stdout.strip()}</b>")
            elif text.lower() == "/restart":
                subprocess.run(["sudo", "systemctl", "restart", "nifty"])
                send_message("Dashboard restarted.")
            elif "request_token=" in text or (text.startswith("http") and "kite" in text.lower()):
                process_redirect_url(text)

    except Exception as e:
        print(f"Poll error: {e}")


def main():
    global login_url_sent_date
    print("Telegram bot listener started...")
    init_offset()
    send_message(
        "<b>Nifty Bot is online.</b>\n\n"
        "Commands:\n"
        "/login — get today's Kite login URL\n"
        "/status — check dashboard status\n"
        "/restart — restart dashboard"
    )

    while True:
        now = datetime.now(IST)
        today = now.date()

        # Auto-send login URL at 8:50 AM IST on weekdays
        if now.weekday() < 5 and now.hour == 8 and now.minute == 50:
            if login_url_sent_date != today:
                send_login_url()
                login_url_sent_date = today

        # Auto-send EOD P&L summary at 3:31 PM IST on weekdays
        if now.weekday() < 5 and now.hour == 15 and now.minute == 31:
            if eod_sent_date != today:
                try:
                    send_eod_summary(get_trade_history(limit=100))
                    eod_sent_date = today
                except Exception as e:
                    print(f"EOD summary error: {e}")

        poll_updates()
        time.sleep(2)


if __name__ == "__main__":
    main()
