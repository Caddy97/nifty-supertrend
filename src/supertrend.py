import pandas as pd
import numpy as np

def calculate_supertrend(candles, period=10, multiplier=3):
    df = pd.DataFrame(candles)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    df["prev_close"] = df["close"].shift(1)
    df["tr1"] = df["high"] - df["low"]
    df["tr2"] = (df["high"] - df["prev_close"]).abs()
    df["tr3"] = (df["low"] - df["prev_close"]).abs()
    df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
    df["atr"] = df["tr"].rolling(window=period).mean()

    df["basic_upper"] = (df["high"] + df["low"]) / 2 + multiplier * df["atr"]
    df["basic_lower"] = (df["high"] + df["low"]) / 2 - multiplier * df["atr"]

    final_upper = [np.nan] * len(df)
    final_lower = [np.nan] * len(df)
    supertrend = [np.nan] * len(df)
    direction = [1] * len(df)

    for i in range(len(df)):
        if i < period:
            continue

        if i == period:
            final_upper[i] = df["basic_upper"].iloc[i]
        else:
            if df["basic_upper"].iloc[i] < final_upper[i-1] or df["close"].iloc[i-1] > final_upper[i-1]:
                final_upper[i] = df["basic_upper"].iloc[i]
            else:
                final_upper[i] = final_upper[i-1]

        if i == period:
            final_lower[i] = df["basic_lower"].iloc[i]
        else:
            if df["basic_lower"].iloc[i] > final_lower[i-1] or df["close"].iloc[i-1] < final_lower[i-1]:
                final_lower[i] = df["basic_lower"].iloc[i]
            else:
                final_lower[i] = final_lower[i-1]

        if i == period:
            direction[i] = 1 if df["close"].iloc[i] > final_upper[i] else -1
        else:
            if direction[i-1] == 1:
                direction[i] = -1 if df["close"].iloc[i] < final_lower[i] else 1
            else:
                direction[i] = 1 if df["close"].iloc[i] > final_upper[i] else -1

        supertrend[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

    df["final_upper"] = final_upper
    df["final_lower"] = final_lower
    df["supertrend"] = supertrend
    df["direction"] = direction

    df["signal"] = None
    df.loc[(df["direction"] == 1) & (df["direction"].shift(1) == -1), "signal"] = "BUY"
    df.loc[(df["direction"] == -1) & (df["direction"].shift(1) == 1), "signal"] = "SELL"

    return df

if __name__ == "__main__":
    from data import get_historical_data
    candles = get_historical_data(interval="15minute", days=10)
    df = calculate_supertrend(candles)

    signals = df[df["signal"].notna()]
    print(f"Total candles: {len(df)}")
    print(f"Signals found: {len(signals)}")
    print(signals[["date", "close", "supertrend", "direction", "signal"]].to_string())
