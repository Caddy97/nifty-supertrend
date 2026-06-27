from datetime import datetime, timedelta
from auth import get_kite
from vix_data import get_vix_history, get_vix_on_date
from option_lookup import get_monthly_option_token
from implied_vol import implied_volatility
from trading_days import trading_days_between

NIFTY_TOKEN = 256265

def analyze_skew(strikes, option_type="CE", days=20):
    kite = get_kite()
    vix_df = get_vix_history(period="2y")

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    spot_candles = kite.historical_data(
        instrument_token=NIFTY_TOKEN, from_date=from_date, to_date=to_date, interval="day"
    )
    spot_by_date = {c["date"].date(): c["close"] for c in spot_candles}

    print(f"{'Strike':>8} {'Moneyness':>10} {'Date':12} {'Spot':>8} {'RealPx':>8} {'FlatVIX':>8} {'ImpliedVol':>11} {'Skew_pp':>8}")

    rows = []
    for strike in strikes:
        info = get_monthly_option_token(strike, option_type)
        if not info:
            print(f"Strike {strike}: no contract found")
            continue
        expiry_date = datetime.strptime(info["expiry"], "%Y-%m-%d")

        real_candles = kite.historical_data(
            instrument_token=info["instrument_token"],
            from_date=from_date, to_date=to_date, interval="day"
        )

        for rc in real_candles:
            t = rc["date"].replace(tzinfo=None)
            spot = spot_by_date.get(t.date())
            if not spot:
                continue
            vix_pct = get_vix_on_date(vix_df, t)
            if vix_pct is None:
                continue
            dte = trading_days_between(t, expiry_date)
            if dte <= 0:
                continue

            iv = implied_volatility(rc["close"], spot, strike, dte, option_type)
            if iv is None:
                continue

            moneyness = (strike - spot) / spot * 100  # % OTM (positive) or ITM (negative) for CE
            skew_pp = (iv * 100) - vix_pct  # percentage points difference from flat VIX

            rows.append({
                "strike": strike, "moneyness": round(moneyness, 2), "date": t.date(),
                "spot": spot, "real_price": rc["close"], "flat_vix": vix_pct,
                "implied_vol_pct": round(iv * 100, 2), "skew_pp": round(skew_pp, 2)
            })
            print(f"{strike:>8} {moneyness:>9.2f}% {str(t.date()):12} {spot:>8.0f} {rc['close']:>8.2f} {vix_pct:>8.2f} {iv*100:>10.2f}% {skew_pp:>+7.2f}")

    return rows

if __name__ == "__main__":
    strikes = [23500, 23700, 23900, 24000, 24100, 24300, 24500]
    analyze_skew(strikes, option_type="CE", days=10)
