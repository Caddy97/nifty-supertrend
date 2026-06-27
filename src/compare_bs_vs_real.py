import pandas as pd
from datetime import datetime, timedelta
from auth import get_kite
from supertrend import calculate_supertrend
from strike_selector import get_atm_strike
from option_lookup import get_monthly_option_token
from black_scholes import black_scholes_price
from vix_data import get_vix_history, get_vix_on_date
from premium_backtest import get_monthly_expiry

NIFTY_TOKEN = 256265

def get_real_option_price_near(kite, instrument_token, target_date):
    from_date = target_date - timedelta(days=2)
    to_date = target_date + timedelta(days=1)
    try:
        data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date, to_date=to_date,
            interval="15minute"
        )
    except Exception:
        return None
    if not data:
        return None
    closest = min(data, key=lambda d: abs((d["date"].replace(tzinfo=None) - target_date).total_seconds()))
    return closest["close"]

def run_comparison(days=170):
    kite = get_kite()
    vix_df = get_vix_history(period="2y")

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    candles = kite.historical_data(
        instrument_token=NIFTY_TOKEN, from_date=from_date,
        to_date=to_date, interval="15minute"
    )
    print(f"Downloaded {len(candles)} Nifty candles\n")

    df = calculate_supertrend(candles)
    signals_df = df[df["signal"].notna()].reset_index(drop=True)

    rows = []
    for _, row in signals_df.iterrows():
        sig_date = row["date"].replace(tzinfo=None)
        spot = row["close"]
        strike = get_atm_strike(spot)
        opt_type = "CE" if row["signal"] == "BUY" else "PE"

        info = get_monthly_option_token(strike, opt_type)
        if not info:
            continue

        real_price = get_real_option_price_near(kite, info["instrument_token"], sig_date)
        if real_price is None:
            continue

        vix_pct = get_vix_on_date(vix_df, sig_date)
        if vix_pct is None:
            continue
        vol = vix_pct / 100.0

        expiry = get_monthly_expiry(sig_date)
        days_to_expiry = max((expiry - sig_date).days, 0)
        bs_price = black_scholes_price(spot, strike, days_to_expiry, vol, opt_type)

        diff = bs_price - real_price
        pct_diff = (diff / real_price * 100) if real_price > 0 else None

        rows.append({
            "date": sig_date.date(), "signal": row["signal"], "spot": round(spot, 1),
            "strike": strike, "type": opt_type, "vix": round(vix_pct, 2),
            "dte": days_to_expiry, "bs_price": round(bs_price, 2),
            "real_price": round(real_price, 2), "diff": round(diff, 2),
            "pct_diff": round(pct_diff, 1) if pct_diff is not None else None
        })

    result_df = pd.DataFrame(rows)
    if result_df.empty:
        print("No comparable signals found (no real data overlap).")
        return result_df

    print(result_df.to_string(index=False))
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Comparisons made: {len(result_df)}")
    print(f"Mean diff (BS - Real): {result_df['diff'].mean():.2f} points")
    print(f"Mean abs diff: {result_df['diff'].abs().mean():.2f} points")
    print(f"Mean % diff: {result_df['pct_diff'].mean():.1f}%")
    print(f"BS overpriced count: {(result_df['diff'] > 0).sum()}")
    print(f"BS underpriced count: {(result_df['diff'] < 0).sum()}")
    return result_df

if __name__ == "__main__":
    run_comparison(days=170)
