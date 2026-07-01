import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from stock_contracts import get_lot_size

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_trades.db"
IST = timezone(timedelta(hours=5, minutes=30))


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_stock_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                stock         TEXT    NOT NULL,
                side          TEXT    NOT NULL,
                symbol        TEXT    NOT NULL,
                entry_spot    REAL    NOT NULL,
                entry_time    TEXT    NOT NULL,
                exit_spot     REAL,
                exit_time     TEXT,
                exit_reason   TEXT,
                pnl_points    REAL,
                pnl_rupees    REAL,
                status        TEXT    NOT NULL DEFAULT 'OPEN'
            )
        """)


def open_stock_trade(stock, side, symbol, entry_spot):
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p")
    with _conn() as conn:
        conn.execute("""
            INSERT INTO stock_trades
                (stock, side, symbol, entry_spot, entry_time, status)
            VALUES (?, ?, ?, ?, ?, 'OPEN')
        """, (stock, side, symbol, entry_spot, now))
    print(f"[Stock Paper] Opened {side} {stock} ({symbol}) @ {entry_spot:.2f}")


def get_open_stock_trades(stock=None):
    with _conn() as conn:
        if stock:
            rows = conn.execute(
                "SELECT * FROM stock_trades WHERE status='OPEN' AND stock=?", (stock,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stock_trades WHERE status='OPEN'"
            ).fetchall()
    return [dict(r) for r in rows]


def close_stock_trade_by_id(trade_id, exit_spot, exit_reason):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM stock_trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return None
        trade = dict(row)
    lot = get_lot_size(trade["stock"])
    pnl_pts = (exit_spot - trade["entry_spot"]) if trade["side"] == "BUY" else (trade["entry_spot"] - exit_spot)
    pnl_inr = pnl_pts * lot
    now = datetime.now(IST).strftime("%d %b %Y %I:%M %p")
    with _conn() as conn:
        conn.execute("""
            UPDATE stock_trades
            SET exit_spot=?, exit_time=?, exit_reason=?,
                pnl_points=?, pnl_rupees=?, status='CLOSED'
            WHERE id=?
        """, (exit_spot, now, exit_reason, pnl_pts, pnl_inr, trade_id))
    print(f"[Stock Paper] Closed {trade['stock']} P&L: {pnl_pts:+.2f} pts  ₹{pnl_inr:+,.0f}")
    return {"pnl_points": pnl_pts, "pnl_rupees": pnl_inr, "stock": trade["stock"]}


def get_stock_trade_history(stock=None, limit=50):
    with _conn() as conn:
        if stock:
            rows = conn.execute(
                "SELECT * FROM stock_trades WHERE stock=? ORDER BY id DESC LIMIT ?",
                (stock, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stock_trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_stock_db()
    print("Stock DB initialised at", DB_PATH)
