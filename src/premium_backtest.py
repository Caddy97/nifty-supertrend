import pandas as pd
from datetime import datetime, timedelta
from auth import get_kite
from supertrend import calculate_supertrend
from strike_selector import get_atm_strike
from black_scholes import black_scholes_price
from vix_data import get_vix_history, get_vix_on_date
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
    signals_df = df[df["signal"].notna()].reset_index(drop=True)

    trades = []
    position = None
    forced_closes = 0

    for _, row in signals_df.iterrows():
        sig_date = row["date"]
        if hasattr(sig_date, "tz_localize"):
            sig_date_naive = sig_date.tz_localize(None) if sig_date.tzinfo else sig_date
        else:
            sig_date_naive = sig_date

        spot = row["close"]
        vix_pct = get_vix_on_date(vix_df, sig_date_naive)
        if vix_pct is None:
            continue
        vol = vix_pct / 100.0

        if row["signal"] == "BUY":
            if position and position["side"] == "SHORT":
                exit_premium = price_option(position, spot, sig_date_naive, vol)
                pnl = position["entry_premium"] - exit_premium
                trades.append(make_trade_record(position, exit_premium, pnl, sig_date_naive, "signal"))
                position = None
            if not position:
                position = open_position("LONG", "CE", spot, sig_date_naive, vol)

        elif row["signal"] == "SELL":
            if position and position["side"] == "LONG":
                exit_premium = price_option(position, spot, sig_date_naive, vol)
                pnl = exit_premium - position["entry_premium"]
                trades.append(make_trade_record(position, exit_premium, pnl, sig_date_naive, "signal"))
                position = None
            if not position:
                position = open_position("SHORT", "PE", spot, sig_date_naive, vol)

    print(f"\nForced expiry closes (position held past monthly expiry): {forced_closes}")
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

def price_option(position, spot, current_date, vol):
    days_to_expiry = (position["expiry"] - current_date).days
    return black_scholes_price(spot, position["strike"], max(days_to_expiry, 0), vol, position["option_type"])

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
    print("=" * 55)
    print("\nNOTE: Premiums are Black-Scholes ESTIMATES (real VIX + real spot),")
    print("not actual traded option prices - Kite doesn't retain expired-contract history.")
    print("No brokerage/spread included. Validate against real premiums during paper trading.")

if __name__ == "__main__":
    candles = download_nifty_history(days=730, interval="15minute")
    vix_df = get_vix_history(period="2y")
    trades = run_premium_backtest(candles, vix_df)
    print_results(trades)
