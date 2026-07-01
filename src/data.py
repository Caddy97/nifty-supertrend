from auth import get_kite
from datetime import datetime, timedelta, timezone

NIFTY_TOKEN = 256265  # Nifty 50 index
IST = timezone(timedelta(hours=5, minutes=30))

def get_historical_data(interval="15minute", days=5):
    """
    interval options: minute, 3minute, 5minute, 10minute, 15minute,
                       30minute, 60minute, day
    """
    kite = get_kite()
    now_ist   = datetime.now(IST).replace(tzinfo=None)
    to_date   = now_ist.replace(hour=23, minute=59, second=59)  # end of today IST
    from_date = now_ist - timedelta(days=days)

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
