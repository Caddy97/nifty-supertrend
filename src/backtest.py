from auth import get_kite
from supertrend import calculate_supertrend
from datetime import datetime, timedelta

NIFTY_TOKEN = 256265

def download_history(days=730, interval="15minute", chunk_days=190):
    """Paginates across multiple requests since Kite caps each call (e.g. ~200 days for 15min)."""
    kite = get_kite()
    end_date = datetime.now()
    overall_start = end_date - timedelta(days=days)

    all_candles = []
    chunk_end = end_date
    while chunk_end > overall_start:
        chunk_start = max(overall_start, chunk_end - timedelta(days=chunk_days))
        data = kite.historical_data(
            instrument_token=NIFTY_TOKEN,
            from_date=chunk_start,
            to_date=chunk_end,
            interval=interval
        )
        print(f"  chunk {chunk_start.date()} to {chunk_end.date()}: {len(data)} candles")
        all_candles = data + all_candles  # prepend since we're going backwards
        chunk_end = chunk_start - timedelta(seconds=1)

    # de-duplicate by timestamp, just in case chunk boundaries overlap
    seen = set()
    deduped = []
    for c in all_candles:
        key = c["date"]
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    print(f"Downloaded {len(deduped)} total candles ({interval}, {days} days)")
    return deduped

def run_backtest(candles):
    df = calculate_supertrend(candles)
    signals_df = df[df["signal"].notna()].reset_index(drop=True)

    trades = []
    position = None
    for _, row in signals_df.iterrows():
        if row["signal"] == "BUY":
            if position and position["side"] == "SHORT":
                pnl = position["entry"] - row["close"]
                trades.append({"side": "SHORT", "entry": position["entry"], "exit": row["close"], "pnl": pnl})
                position = None
            if not position:
                position = {"side": "LONG", "entry": row["close"]}
        elif row["signal"] == "SELL":
            if position and position["side"] == "LONG":
                pnl = row["close"] - position["entry"]
                trades.append({"side": "LONG", "entry": position["entry"], "exit": row["close"], "pnl": pnl})
                position = None
            if not position:
                position = {"side": "SHORT", "entry": row["close"]}

    total_pnl = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]

    equity = 0
    peak = 0
    max_dd = 0
    for t in trades:
        equity += t["pnl"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]

    print("\n" + "=" * 50)
    print(f"SUPERTREND BACKTEST - NIFTY 50 (spot points)")
    print("=" * 50)
    print(f"Total trades:     {len(trades)}")
    print(f"Wins:             {len(wins)}")
    print(f"Losses:           {len(losses)}")
    print(f"Win rate:         {len(wins)/len(trades)*100:.1f}%" if trades else "Win rate: --")
    print(f"Total P&L:        {total_pnl:,.2f} points")
    if wins:
        print(f"Avg win:          {sum(t['pnl'] for t in wins)/len(wins):,.2f} points")
    if losses:
        print(f"Avg loss:         {sum(t['pnl'] for t in losses)/len(losses):,.2f} points")
    print(f"Max drawdown:     {max_dd:,.2f} points")
    print(f"Buy & hold P&L:   {last_close - first_close:,.2f} points")
    print("=" * 50)
    print("\nNOTE: This is SPOT points, not real option P&L.")
    print("No brokerage, spread, or theta decay included yet.")

if __name__ == "__main__":
    candles = download_history(days=730, interval="15minute")
    run_backtest(candles)
