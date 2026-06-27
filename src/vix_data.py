import yfinance as yf
import pandas as pd

def get_vix_history(period="2y"):
    """
    Returns a DataFrame indexed by date with VIX close values.
    Source: Yahoo Finance (^INDIAVIX) - chosen because Kite's VIX
    history only goes back to Dec 2025, too short for our 2-year backtest.
    """
    vix = yf.Ticker("^INDIAVIX")
    hist = vix.history(period=period)
    hist = hist[["Close"]].rename(columns={"Close": "vix"})
    hist.index = hist.index.tz_localize(None)  # strip timezone for easier matching
    return hist

def get_vix_on_date(vix_df, target_date):
    """
    Returns the VIX close on or just before the given date
    (handles weekends/holidays where VIX wasn't published that exact day).
    """
    available = vix_df[vix_df.index.date <= target_date.date()]
    if available.empty:
        return None
    return available.iloc[-1]["vix"]

if __name__ == "__main__":
    df = get_vix_history()
    print(f"Got {len(df)} VIX daily values")
    print("Range:", df.index.min().date(), "to", df.index.max().date())
    print("\nMin/Max/Mean VIX over period:")
    print(df["vix"].describe())
