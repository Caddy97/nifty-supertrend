from auth import get_kite
from datetime import datetime, timedelta

NIFTY_TOKEN = 256265  # Nifty 50 index

def get_historical_data(interval="15minute", days=5):
    """
    interval options: minute, 3minute, 5minute, 10minute, 15minute,
                       30minute, 60minute, day
    """
    kite = get_kite()
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    data = kite.historical_data(
        instrument_token=NIFTY_TOKEN,
        from_date=from_date,
        to_date=to_date,
        interval=interval
    )
    return data

if __name__ == "__main__":
    candles = get_historical_data(interval="15minute", days=5)
    print(f"Fetched {len(candles)} candles")
    print("\nFirst candle:", candles[0] if candles else "none")
    print("Last candle:", candles[-1] if candles else "none")
