import os
import pandas as pd

DATA_DIR = "data"

def read_candles(interval_name, limit=200):
    """
    interval_name: '1m', '5m', '15m', '1h'
    Returns list of dicts: time, open, high, low, close
    """
    path = os.path.join(DATA_DIR, f"nifty_{interval_name}.parquet")
    if not os.path.exists(path):
        return []
    df = pd.read_parquet(path)
    df = df.sort_values("time").tail(limit)
    return df.to_dict("records")

if __name__ == "__main__":
    for name in ["1m", "5m", "15m", "1h"]:
        candles = read_candles(name)
        print(f"{name}: {len(candles)} candles")
        if candles:
            print("  latest:", candles[-1])
