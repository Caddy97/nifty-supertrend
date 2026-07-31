from auth import get_kite
import pandas as pd
from datetime import datetime

def _future_expiries(strike, option_type):
    """Shared lookup: all not-yet-expired NIFTY contracts for this strike/type,
    sorted nearest-expiry-first. Returns None if nothing matches."""
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
    return future if not future.empty else None

def _to_result(row, strike, option_type):
    return {
        "instrument_token": int(row["instrument_token"]),
        "tradingsymbol": row["tradingsymbol"],
        "expiry": str(row["expiry"].date()),
        "strike": strike,
        "option_type": option_type
    }

def get_monthly_option_token(strike, option_type):
    future = _future_expiries(strike, option_type)
    if future is None:
        return None

    future["month_key"] = future["expiry"].dt.to_period("M")
    monthly_candidates = future.groupby("month_key")["expiry"].max().reset_index()

    nearest_month = monthly_candidates.iloc[0]["expiry"]
    match = future[future["expiry"] == nearest_month]

    if match.empty:
        return None

    return _to_result(match.iloc[0], strike, option_type)

def get_weekly_option_token(strike, option_type):
    """Nearest upcoming expiry overall - the weekly contract if one exists
    before the next monthly, otherwise whatever's nearest."""
    future = _future_expiries(strike, option_type)
    if future is None:
        return None
    return _to_result(future.iloc[0], strike, option_type)

def get_token_for_symbol(tradingsymbol):
    """Looks up an exact NFO tradingsymbol directly (works for both monthly
    and weekly formats, unlike parsing strike/expiry out of the symbol
    string). Returns None if Kite doesn't currently list it (e.g. expired)."""
    kite = get_kite()
    df = pd.DataFrame(kite.instruments())
    match = df[df["tradingsymbol"] == tradingsymbol]
    if match.empty:
        return None
    row = match.iloc[0]
    return {"instrument_token": int(row["instrument_token"]), "tradingsymbol": tradingsymbol}

if __name__ == "__main__":
    result = get_monthly_option_token(24000, "CE")
    print(result)
    print(get_weekly_option_token(24000, "CE"))
