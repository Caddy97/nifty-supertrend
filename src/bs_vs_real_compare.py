from datetime import datetime, timedelta
from auth import get_kite
from black_scholes import black_scholes_price
from vix_data import get_vix_history, get_vix_on_date
from option_lookup import get_monthly_option_token
from trading_days import trading_days_between

NIFTY_TOKEN = 256265

def build_comparison_data(strike, option_type, days=30):
    kite = get_kite()
    vix_df = get_vix_history(period="2y")

    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    info = get_monthly_option_token(strike, option_type)
    if not info:
        print(f"No contract found for {strike}{option_type}")
        return []

    print(f"Using contract: {info['tradingsymbol']}, expiry {info['expiry']}")

    real_candles = kite.historical_data(
        instrument_token=info["instrument_token"],
        from_date=from_date, to_date=to_date, interval="15minute"
    )
    spot_candles = kite.historical_data(
        instrument_token=NIFTY_TOKEN,
        from_date=from_date, to_date=to_date, interval="15minute"
    )

    spot_by_time = {c["date"].replace(tzinfo=None): c for c in spot_candles}
    expiry_date = datetime.strptime(info["expiry"], "%Y-%m-%d")

    rows = []
    for rc in real_candles:
        t = rc["date"].replace(tzinfo=None)
        sc = spot_by_time.get(t)
        if not sc:
            continue

        vix_pct = get_vix_on_date(vix_df, t)
        if vix_pct is None:
            continue
        vol = vix_pct / 100.0

        dte = max(trading_days_between(t, expiry_date), 0)

        bs_o = black_scholes_price(sc["open"], strike, dte, vol, option_type)
        bs_h = black_scholes_price(sc["high"], strike, dte, vol, option_type)
        bs_l = black_scholes_price(sc["low"], strike, dte, vol, option_type)
        bs_c = black_scholes_price(sc["close"], strike, dte, vol, option_type)

        bs_vals = [bs_o, bs_h, bs_l, bs_c]

        rows.append({
            "time": int(t.timestamp()),
            "real_open": rc["open"], "real_high": rc["high"],
            "real_low": rc["low"], "real_close": rc["close"],
            "bs_open": bs_o, "bs_close": bs_c,
            "bs_high": max(bs_vals), "bs_low": min(bs_vals)
        })

    print(f"Built {len(rows)} aligned candles for {strike}{option_type}")
    return rows

if __name__ == "__main__":
    data = build_comparison_data(24000, "CE", days=30)
    if data:
        print("\nFirst:", data[0])
        print("Last:", data[-1])
