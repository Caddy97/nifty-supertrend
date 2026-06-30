import os
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

IST = timezone(timedelta(hours=5, minutes=30))


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


def send_signal_alert(side, spot, strike, opt_type, symbol, premium):
    now_ist = datetime.now(IST).strftime("%d %b %Y  %I:%M %p")
    action = "BUY" if side == "BUY" else "SELL"
    direction_label = "Buy CE (bullish)" if side == "BUY" else "Buy PE (bearish)"

    text = (
        f"<b>NIFTY SUPERTREND — {action} SIGNAL</b>\n"
        f"Time     : {now_ist} IST\n"
        f"Spot     : {spot:,.2f}\n"
        f"Option   : {symbol}\n"
        f"Strike   : {strike}  |  {opt_type}\n"
        f"Est. Premium : {premium:.2f} pts\n"
        f"Strategy : {direction_label}"
    )
    return send_message(text)


def send_exit_alert(side, spot, symbol, entry_premium, exit_premium):
    pnl = (exit_premium - entry_premium) if side == "BUY" else (entry_premium - exit_premium)
    now_ist = datetime.now(IST).strftime("%d %b %Y  %I:%M %p")

    text = (
        f"<b>NIFTY SUPERTREND — EXIT (signal reversal)</b>\n"
        f"Time     : {now_ist} IST\n"
        f"Spot     : {spot:,.2f}\n"
        f"Option   : {symbol}\n"
        f"Entry Premium : {entry_premium:.2f}\n"
        f"Exit Premium  : {exit_premium:.2f}\n"
        f"P&amp;L (pts) : {pnl:+.2f}"
    )
    return send_message(text)


if __name__ == "__main__":
    ok = send_message("<b>Nifty Alert Bot is live and connected.</b>\nYou will receive BUY/SELL signals here.")
    print("Test message sent!" if ok else "Failed — check token and chat ID.")
