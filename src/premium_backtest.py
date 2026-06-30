import pandas as pd
from datetime import datetime, timedelta
from auth import get_kite
from supertrend import calculate_supertrend
from strike_selector import get_atm_strike
from black_scholes import black_scholes_price
from vix_data import get_vix_history, get_vix_on_date
from vol_skew import skewed_vol
from trading_days import trading_days_between
from contract_specs import LOT_SIZE

NIFTY_TOKEN = 256265

def download_nifty_history(days=730, interval="15minute", chunk_days=190):
    kite = get_kite()
    end_date = datetime.now()
    overall_start = end_date - timedelta(days=days)
    all_candles = []
    chunk_end = end_date
    while chunk_end > overall_start:
        chunk_start = max(overall_start, chunk_end - timedelta(days=chunk_days))
        data = kite.historical_data(
            instrument_token=NIFTY_TOKEN, from_date=chunk_start,
            to_date=chunk_end, interval=interval
        )
        all_candles = data + all_candles
        chunk_end = chunk_start - timedelta(seconds=1)
    seen = set()
    deduped = []
    for c in all_candles:
        if c["date"] not in seen:
            seen.add(c["date"])
            deduped.append(c)
    print(f"Downloaded {len(deduped)} Nifty candles")
    return deduped

def last_tuesday_of_month(year, month):
    """Approximate monthly expiry: last Tuesday of the given month."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - 1) % 7  # Tuesday = 1
    return last_day - timedelta(days=offset)

def get_monthly_expiry(trade_date):
    expiry = last_tuesday_of_month(trade_date.year, trade_date.month)
    if trade_date.date() > expiry.date():
        # already past this month's expiry, use next month's
        if trade_date.month == 12:
            expiry = last_tuesday_of_month(trade_date.year + 1, 1)
        else:
            expiry = last_tuesday_of_month(trade_date.year, trade_date.month + 1)
    return expiry

def run_premium_backtest(candles, vix_df):
    df = calculate_supertrend(candles)

    trades = []
    position = None
    exit_counts = {"signal": 0, "stop_loss": 0, "expiry": 0}

    for _, row in df.iterrows():
        sig_date = row["date"]
        if hasattr(sig_date, "tzinfo") and sig_date.tzinfo:
            sig_date = sig_date.replace(tzinfo=None)

        spot = row["close"]
        vix_pct = get_vix_on_date(vix_df, sig_date)
        if vix_pct is None:
            continue
        vol = vix_pct / 100.0

        # --- Check exit conditions on active position first ---
        if position:
            current_premium = price_option(position, spot, sig_date, vol)
            days_to_expiry = (position["expiry"] - sig_date).days

            if position["side"] == "LONG":
                pnl = current_premium - position["entry_premium"]
                # Exit 3: force close 1 day before expiry
                if days_to_expiry <= 1:
                    trades.append(make_trade_record(position, current_premium, pnl, sig_date, "expiry"))
                    position = None
                    exit_counts["expiry"] += 1

            elif position["side"] == "SHORT":
                pnl = position["entry_premium"] - current_premium
                # Exit 3: force close 1 day before expiry
                if days_to_expiry <= 1:
                    trades.append(make_trade_record(position, current_premium, pnl, sig_date, "expiry"))
                    position = None
                    exit_counts["expiry"] += 1

        # --- Exit 1: signal reversal + open new position ---
        if row["signal"] == "BUY":
            if position and position["side"] == "SHORT":
                exit_premium = price_option(position, spot, sig_date, vol)
                pnl = position["entry_premium"] - exit_premium
                trades.append(make_trade_record(position, exit_premium, pnl, sig_date, "signal"))
                position = None
                exit_counts["signal"] += 1
            if not position:
                position = open_position("LONG", "CE", spot, sig_date, vol)

        elif row["signal"] == "SELL":
            if position and position["side"] == "LONG":
                exit_premium = price_option(position, spot, sig_date, vol)
                pnl = exit_premium - position["entry_premium"]
                trades.append(make_trade_record(position, exit_premium, pnl, sig_date, "signal"))
                position = None
                exit_counts["signal"] += 1
            if not position:
                position = open_position("SHORT", "PE", spot, sig_date, vol)

    print(f"\nExit breakdown:")
    print(f"  Signal reversals : {exit_counts['signal']}")
    print(f"  Stop losses (50%): {exit_counts['stop_loss']}")
    print(f"  Expiry closes    : {exit_counts['expiry']}")
    return trades

def open_position(side, opt_type, spot, entry_date, vol):
    strike = get_atm_strike(spot)
    expiry = get_monthly_expiry(entry_date)
    days_to_expiry = (expiry - entry_date).days
    premium = black_scholes_price(spot, strike, max(days_to_expiry, 0), vol, opt_type)
    return {
        "side": side, "option_type": opt_type, "strike": strike,
        "expiry": expiry, "entry_date": entry_date, "entry_spot": spot,
        "entry_premium": premium
    }

def price_option(position, spot, current_date, vol_pct):
    days_to_expiry = (position["expiry"] - current_date).days
    adjusted_vol = skewed_vol(vol_pct, spot, position["strike"], position["option_type"])
    return black_scholes_price(spot, position["strike"], max(days_to_expiry, 0), adjusted_vol, position["option_type"])

def make_trade_record(position, exit_premium, pnl, exit_date, exit_reason):
    return {
        "side": position["side"], "option_type": position["option_type"],
        "strike": position["strike"], "entry_premium": position["entry_premium"],
        "exit_premium": exit_premium, "pnl_points": pnl,
        "pnl_rupees": pnl * LOT_SIZE,
        "entry_date": position["entry_date"], "exit_date": exit_date,
        "exit_reason": exit_reason
    }

def print_results(trades):
    if not trades:
        print("No trades generated.")
        return

    total_pnl_pts = sum(t["pnl_points"] for t in trades)
    total_pnl_inr = sum(t["pnl_rupees"] for t in trades)
    wins = [t for t in trades if t["pnl_points"] > 0]
    losses = [t for t in trades if t["pnl_points"] <= 0]

    equity = 0
    peak = 0
    max_dd_pts = 0
    for t in trades:
        equity += t["pnl_points"]
        peak = max(peak, equity)
        max_dd_pts = max(max_dd_pts, peak - equity)

    by_exit = {}
    for t in trades:
        r = t["exit_reason"]
        by_exit.setdefault(r, {"count": 0, "pnl": 0})
        by_exit[r]["count"] += 1
        by_exit[r]["pnl"] += t["pnl_points"]

    print("\n" + "=" * 55)
    print("PREMIUM-BASED BACKTEST - NIFTY MONTHLY OPTIONS")
    print("(Black-Scholes estimate using real spot + real VIX)")
    print("=" * 55)
    print(f"Total trades:       {len(trades)}")
    print(f"Wins:               {len(wins)}")
    print(f"Losses:             {len(losses)}")
    print(f"Win rate:           {len(wins)/len(trades)*100:.1f}%")
    print(f"Total P&L (points): {total_pnl_pts:,.2f}")
    print(f"Total P&L (₹):      {total_pnl_inr:,.2f}  (lot size {LOT_SIZE})")
    if wins:
        print(f"Avg win (points):   {sum(t['pnl_points'] for t in wins)/len(wins):,.2f}")
    if losses:
        print(f"Avg loss (points):  {sum(t['pnl_points'] for t in losses)/len(losses):,.2f}")
    print(f"Max drawdown (pts): {max_dd_pts:,.2f}")
    print(f"\nP&L by exit type:")
    for reason, stats in sorted(by_exit.items()):
        print(f"  {reason:<12}: {stats['count']:>4} trades  |  {stats['pnl']:>10,.2f} pts")
    print("=" * 55)
    print("\nNOTE: Premiums are Black-Scholes ESTIMATES (real VIX + real spot),")
    print("not actual traded option prices - Kite doesn't retain expired-contract history.")
    print("No brokerage/spread included. Validate against real premiums during paper trading.")

if __name__ == "__main__":
    candles = download_nifty_history(days=730, interval="15minute")
    vix_df = get_vix_history(period="2y")
    trades = run_premium_backtest(candles, vix_df)
    print_results(trades)
