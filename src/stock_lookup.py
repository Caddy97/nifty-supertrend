from auth import get_kite
import pandas as pd
from datetime import datetime

def get_stock_future(symbol):
    """Return nearest unexpired monthly future token for a stock."""
    kite = get_kite()
    instruments = kite.instruments("NFO")
    df = pd.DataFrame(instruments)

    futs = df[
        (df["name"] == symbol) &
        (df["instrument_type"] == "FUT")
    ].copy()

    if futs.empty:
        return None

    futs["expiry"] = pd.to_datetime(futs["expiry"])
    today = pd.Timestamp(datetime.now().date())
    upcoming = futs[futs["expiry"] >= today].sort_values("expiry")

    if upcoming.empty:
        return None

    row = upcoming.iloc[0]
    return {
        "instrument_token": int(row["instrument_token"]),
        "tradingsymbol":    row["tradingsymbol"],
        "expiry":           str(row["expiry"].date()),
        "lot_size":         int(row["lot_size"]),
    }

if __name__ == "__main__":
    for sym in ["ULTRACEMCO", "AMBER", "DIXON", "BAJFINANCE"]:
        print(sym, get_stock_future(sym))
