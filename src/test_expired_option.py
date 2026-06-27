from auth import get_kite
import pandas as pd
from datetime import datetime, timedelta

kite = get_kite()
instruments = kite.instruments()
df = pd.DataFrame(instruments)

# Find a NIFTY option that expired a few months ago, around a round strike
options = df[
    (df["name"] == "NIFTY") &
    (df["instrument_type"] == "CE")
].copy()
options["expiry"] = pd.to_datetime(options["expiry"])

# Look for one that expired roughly 3 months ago
target_date = pd.Timestamp(datetime.now() - timedelta(days=90))
options["days_diff"] = (options["expiry"] - target_date).abs()
candidate = options.sort_values("days_diff").iloc[0]

print(f"Testing expired contract: {candidate['tradingsymbol']}, expired {candidate['expiry'].date()}, strike {candidate['strike']}")

token = int(candidate["instrument_token"])
# Try to get data covering its actual trading lifetime
to_date = candidate["expiry"] + pd.Timedelta(days=1)
from_date = candidate["expiry"] - pd.Timedelta(days=35)

try:
    data = kite.historical_data(
        instrument_token=token,
        from_date=from_date,
        to_date=to_date,
        interval="15minute"
    )
    print(f"Got {len(data)} candles for this EXPIRED option")
    if data:
        print("First:", data[0])
        print("Last:", data[-1])
    else:
        print("No data returned (empty list)")
except Exception as e:
    print(f"ERROR: {e}")
