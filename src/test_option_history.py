from auth import get_kite
from option_lookup import get_monthly_option_token
from datetime import datetime, timedelta

kite = get_kite()

# Test 1: current month's ATM-ish option (still trading)
print("=" * 60)
print("TEST 1: Current month option (24000 CE)")
print("=" * 60)
info = get_monthly_option_token(24000, "CE")
print(info)

if info:
    to_date = datetime.now()
    from_date = to_date - timedelta(days=30)
    data = kite.historical_data(
        instrument_token=info["instrument_token"],
        from_date=from_date,
        to_date=to_date,
        interval="15minute"
    )
    print(f"Got {len(data)} candles for this option")
    if data:
        print("First:", data[0])
        print("Last:", data[-1])
