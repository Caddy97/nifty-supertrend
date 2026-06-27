from datetime import datetime, timedelta
from auth import get_kite
from black_scholes import black_scholes_price
from vix_data import get_vix_history, get_vix_on_date
from option_lookup import get_monthly_option_token
from trading_days import trading_days_between

def check_opens(strike=24000, option_type="CE", days=10):
    kite = get_kite()
    vix_df = get_vix_history(period="2y")
    info = get_monthly_option_token(strike, option_type)
    expiry_date = datetime.strptime(info["expiry"], "%Y-%m-%d")

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    real_candles = kite.historical_data(
        instrument_token=info["instrument_token"],
        from_date=from_date, to_date=to_date, interval="15minute"
    )
    spot_candles = kite.historical_data(
        instrument_token=256265,
        from_date=from_date, to_date=to_date, interval="15minute"
    )
    spot_by_time = {c["date"].replace(tzinfo=None): c for c in spot_candles}

    seen_dates = set()
    print(f"{'Date':12} {'SpotOpen':>10} {'RealOpen':>10} {'BS_Open':>10} {'VIX_used':>9} {'Diff':>8} {'Diff%':>8}")
    for rc in real_candles:
        t = rc["date"].replace(tzinfo=None)
        date_key = t.date()
        if date_key in seen_dates:
            continue  # only look at FIRST candle of each day
        seen_dates.add(date_key)

        sc = spot_by_time.get(t)
        if not sc:
            continue
        vix_pct = get_vix_on_date(vix_df, t)
        if vix_pct is None:
            continue
        vol = vix_pct / 100.0
        dte = max(trading_days_between(t, expiry_date), 0)

        bs_open = black_scholes_price(sc["open"], strike, dte, vol, option_type)
        diff = bs_open - rc["open"]
        pct = (diff / rc["open"] * 100) if rc["open"] else None

        print(f"{str(date_key):12} {sc['open']:>10.1f} {rc['open']:>10.2f} {bs_open:>10.2f} {vix_pct:>9.2f} {diff:>8.2f} {pct:>7.1f}%")

if __name__ == "__main__":
    check_opens(strike=24000, option_type="CE", days=15)
