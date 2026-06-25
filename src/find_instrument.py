from auth import get_kite
import pandas as pd

kite = get_kite()

print("Downloading full instrument list...")
instruments = kite.instruments()
df = pd.DataFrame(instruments)

# Find Nifty 50 index
nifty = df[(df["name"] == "NIFTY 50") | (df["tradingsymbol"] == "NIFTY 50")]
print("\nNifty 50 index instrument:")
print(nifty[["instrument_token", "tradingsymbol", "name", "exchange"]])

# Also show a sample of Nifty options for reference
options = df[(df["name"] == "NIFTY") & (df["instrument_type"].isin(["CE", "PE"]))]
print(f"\nFound {len(options)} Nifty option contracts.")
print(options[["instrument_token", "tradingsymbol", "expiry", "strike", "instrument_type"]].head(10))
