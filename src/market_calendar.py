from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# NSE trading holidays 2026 (source: NSE circular NSE/CMTR/71775, Dec 12 2025)
NSE_HOLIDAYS_2026 = {
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Holi
    "2026-03-26",  # Shri Ram Navami
    "2026-03-31",  # Shri Mahavir Jayanti
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-28",  # Bakri Id
    "2026-06-26",  # Muharram
    "2026-09-14",  # Ganesh Chaturthi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-10",  # Diwali-Balipratipada
    "2026-11-24",  # Guru Nanak Dev Jayanti
    "2026-12-25",  # Christmas
}

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# How long after MARKET_CLOSE to wait before running end-of-day jobs (tick
# conversion, etc.) - ticks have been observed trickling in past the nominal
# close, so this buffer avoids racing a still-active writer.
EOD_BUFFER_MINUTES = 15

def now_ist():
    return datetime.now(IST)

def eod_trigger_time():
    """Time of day (IST) at which end-of-day jobs should run: MARKET_CLOSE + EOD_BUFFER_MINUTES."""
    base = datetime(2000, 1, 1, MARKET_CLOSE.hour, MARKET_CLOSE.minute)
    trigger = base + timedelta(minutes=EOD_BUFFER_MINUTES)
    return trigger.time()

def is_holiday(dt=None):
    dt = dt or now_ist()
    return dt.strftime("%Y-%m-%d") in NSE_HOLIDAYS_2026

def is_weekend(dt=None):
    dt = dt or now_ist()
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday

def is_market_open(dt=None):
    """True only if: weekday, not a holiday, and within 9:15-15:30 IST."""
    dt = dt or now_ist()
    if is_weekend(dt):
        return False
    if is_holiday(dt):
        return False
    return MARKET_OPEN <= dt.time() <= MARKET_CLOSE

def market_status(dt=None):
    """Returns a human-readable reason, useful for logging/UI."""
    dt = dt or now_ist()
    if is_weekend(dt):
        return "closed (weekend)"
    if is_holiday(dt):
        return "closed (NSE holiday)"
    if dt.time() < MARKET_OPEN:
        return "closed (pre-market)"
    if dt.time() > MARKET_CLOSE:
        return "closed (after hours)"
    return "open"

if __name__ == "__main__":
    dt = now_ist()
    print(f"Current IST time: {dt.strftime('%Y-%m-%d %H:%M:%S %A')}")
    print(f"Market status: {market_status(dt)}")
    print(f"is_market_open(): {is_market_open(dt)}")
