from auth import get_kite
import pandas as pd
from datetime import datetime

def get_monthly_option_token(strike, option_type):
    kite = get_kite()
    instruments = kite.instruments()
    df = pd.DataFrame(instruments)

    options = df[
        (df["name"] == "NIFTY") &
        (df["instrument_type"] == option_type) &
        (df["strike"] == float(strike))
    ].copy()

    if options.empty:
        return None

    options["expiry"] = pd.to_datetime(options["expiry"])
    today = pd.Timestamp(datetime.now().date())

    future = options[options["expiry"] >= today].sort_values("expiry")
    if future.empty:
        return None

    future["month_key"] = future["expiry"].dt.to_period("M")
    monthly_candidates = future.groupby("month_key")["expiry"].max().reset_index()

    nearest_month = monthly_candidates.iloc[0]["expiry"]
    match = future[future["expiry"] == nearest_month]

    if match.empty:
        return None

    row = match.iloc[0]
    return {
        "instrument_token": int(row["instrument_token"]),
        "tradingsymbol": row["tradingsymbol"],
        "expiry": str(row["expiry"].date()),
        "strike": strike,
        "option_type": option_type
    }

if __name__ == "__main__":
    result = get_monthly_option_token(24000, "CE")
    print(result)
