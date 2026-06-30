import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contract_specs import LOT_SIZE

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "paper_trades.db"
IST = timezone(timedelta(hours=5, minutes=30))


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                side          TEXT    NOT NULL,
                opt_type      TEXT    NOT NULL,
                strike        INTEGER NOT NULL,
                symbol        TEXT    NOT NULL,
                entry_spot    REAL    NOT NULL,
                entry_premium REAL    NOT NULL,
                entry_time    TEXT    NOT NULL,
                exit_spot     REAL,
                exit_premium  REAL,
                exit_time     TEXT,
                exit_reason   TEXT,
                pnl_points    REAL,
                pnl_rupees    REAL,
                status        TEXT    NOT NULL DEFAULT 'OPEN',
                trade_type    TEXT    NOT NULL DEFAULT 'OPT'
            )
        """)
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN trade_type TEXT NOT NULL DEFAULT 'OPT'")
        except Exception:
            pass  # column already exists


def open_trade(side, opt_type, strike, symbol, entry_spot, entry_premium, trade_type="OPT"):
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p")
    with _conn() as conn:
        conn.execute("""
            INSERT INTO trades
                (side, opt_type, strike, symbol, entry_spot, entry_premium, entry_time, status, trade_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (side, opt_type, strike, symbol, entry_spot, entry_premium, now, trade_type))
    print(f"[Paper] Opened {side} {symbol} ({trade_type}) @ {entry_premium:.2f}")


def get_open_trades():
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
    return [dict(r) for r in rows]


def get_open_trade():
    trades = get_open_trades()
    return trades[0] if trades else None


def close_trade_by_id(trade_id, exit_spot, exit_premium, exit_reason):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return None
        trade = dict(row)
    if trade["side"] == "BUY":
        pnl_pts = exit_premium - trade["entry_premium"]
    else:
        pnl_pts = trade["entry_premium"] - exit_premium
    pnl_inr = pnl_pts * LOT_SIZE
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p")
    with _conn() as conn:
        conn.execute("""
            UPDATE trades
            SET exit_spot=?, exit_premium=?, exit_time=?, exit_reason=?,
                pnl_points=?, pnl_rupees=?, status='CLOSED'
            WHERE id=?
        """, (exit_spot, exit_premium, now, exit_reason, pnl_pts, pnl_inr, trade_id))
    print(f"[Paper] Closed {trade['symbol']} ({trade.get('trade_type','OPT')}) P&L: {pnl_pts:+.2f} pts  ₹{pnl_inr:+,.0f}")
    return {"pnl_points": pnl_pts, "pnl_rupees": pnl_inr, "symbol": trade["symbol"], "trade_type": trade.get("trade_type", "OPT")}


def close_open_trade(exit_spot, exit_premium, exit_reason):
    trade = get_open_trade()
    if not trade:
        return None
    return close_trade_by_id(trade["id"], exit_spot, exit_premium, exit_reason)


def get_trade_history(limit=30):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print("DB initialised at", DB_PATH)
    history = get_trade_history()
    print(f"{len(history)} trades in log.")
