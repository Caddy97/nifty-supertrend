import os
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Comma-separated list of chat/group IDs - e.g. "821614163,-1001234567890"
CHAT_IDS = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]

IST = timezone(timedelta(hours=5, minutes=30))


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    ok = True
    for chat_id in CHAT_IDS:
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"Telegram send failed for chat_id={chat_id}: {e}")
            ok = False
    return ok


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


def send_eod_summary(trades):
    """Send end-of-day P&L summary. trades = list of dicts from get_trade_history()."""
    today = datetime.now(IST).strftime("%d %b %Y")
    closed_today = [
        t for t in trades
        if t.get("status") == "CLOSED"
        and t.get("exit_time", "").startswith(today)
        and t.get("pnl_rupees") is not None
    ]
    open_trades = [t for t in trades if t.get("status") == "OPEN"]

    if not closed_today and not open_trades:
        send_message(f"<b>EOD Summary — {today}</b>\nNo trades today.")
        return

    lines = [f"<b>EOD Summary — {today}</b>\n"]

    if closed_today:
        fut = [t for t in closed_today if t.get("trade_type") == "FUT"]
        opt = [t for t in closed_today if t.get("trade_type") == "OPT"]
        total_inr = sum(t["pnl_rupees"] for t in closed_today)
        fut_inr   = sum(t["pnl_rupees"] for t in fut)
        opt_inr   = sum(t["pnl_rupees"] for t in opt)
        wins      = sum(1 for t in closed_today if t["pnl_rupees"] > 0)
        losses    = len(closed_today) - wins

        lines.append(f"Closed trades : {len(closed_today)}  ({wins}W / {losses}L)")
        if fut:
            sign = "+" if fut_inr >= 0 else ""
            lines.append(f"Futures P&L   : {sign}₹{fut_inr:,.0f}")
        if opt:
            sign = "+" if opt_inr >= 0 else ""
            lines.append(f"Options P&L   : {sign}₹{opt_inr:,.0f}")
        sign = "+" if total_inr >= 0 else ""
        lines.append(f"<b>Total P&L     : {sign}₹{total_inr:,.0f}</b>")

    if open_trades:
        lines.append(f"\nOpen positions: {len(open_trades)}")
        for t in open_trades:
            lines.append(f"  {t['symbol']} ({t.get('trade_type','OPT')}) {t['side']} @ {t['entry_premium']:.2f}")

    send_message("\n".join(lines))


if __name__ == "__main__":
    ok = send_message("<b>Nifty Alert Bot is live and connected.</b>\nYou will receive BUY/SELL signals here.")
    print("Test message sent!" if ok else "Failed — check token and chat ID.")
