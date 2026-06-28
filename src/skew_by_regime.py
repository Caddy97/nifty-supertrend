from datetime import datetime, timedelta
from auth import get_kite
from vix_data import get_vix_history, get_vix_on_date
from option_lookup import get_monthly_option_token
from implied_vol import implied_volatility
from trading_days import trading_days_between

NIFTY_TOKEN = 256265

def skew_at_date(target_date, strikes, option_type="CE"):
    kite = get_kite()
    vix_df = get_vix_history(period="2y")

    # pull a small window of spot+option data AROUND the target date
    from_date = target_date - timedelta(days=3)
    to_date = target_date + timedelta(days=1)

    spot_candles = kite.historical_data(
        instrument_token=NIFTY_TOKEN, from_date=from_date, to_date=to_date, interval="day"
    )
    if not spot_candles:
        print(f"No spot data near {target_date.date()}")
        return []

    spot_row = min(spot_candles, key=lambda c: abs((c["date"].replace(tzinfo=None) - target_date).total_seconds()))
    spot = spot_row["close"]
    t = spot_row["date"].replace(tzinfo=None)
    vix_pct = get_vix_on_date(vix_df, t)

    results = []
    for strike in strikes:
        info = get_monthly_option_token(strike, option_type)
        if not info:
            continue
        expiry_date = datetime.strptime(info["expiry"], "%Y-%m-%d")

        opt_candles = kite.historical_data(
            instrument_token=info["instrument_token"], from_date=from_date,
            to_date=to_date, interval="day"
        )
        if not opt_candles:
            continue
        opt_row = min(opt_candles, key=lambda c: abs((c["date"].replace(tzinfo=None) - target_date).total_seconds()))

        dte = trading_days_between(t, expiry_date)
        if dte <= 0:
            continue

        iv = implied_volatility(opt_row["close"], spot, strike, dte, option_type)
        if iv is None:
            continue

        moneyness = (strike - spot) / spot * 100
        results.append({
            "date": t.date(), "vix": vix_pct, "strike": strike,
            "moneyness": round(moneyness, 2), "iv_pct": round(iv * 100, 2)
        })
    return results

if __name__ == "__main__":
    regime_dates = [
        datetime(2026, 6, 18),
        datetime(2026, 6, 1),
        datetime(2026, 4, 23),
        datetime(2026, 3, 30),
    ]
    strikes = [23500, 23700, 23900, 24000, 24100, 24300, 24500]

    for d in regime_dates:
        print(f"\n=== Regime date: {d.date()} ===")
        rows = skew_at_date(d, strikes, "CE")
        for r in rows:
            print(f"  VIX={r['vix']:.2f}  strike={r['strike']}  moneyness={r['moneyness']:+.2f}%  IV={r['iv_pct']:.2f}%")
