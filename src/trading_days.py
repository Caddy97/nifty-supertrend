from datetime import timedelta

def trading_days_between(start_date, end_date):
    """
    Counts trading days (Mon-Fri) between start_date and end_date, exclusive of start, inclusive of end.
    Does NOT account for NSE holidays yet - see market_calendar.py for the holiday list,
    this is a deliberate first-pass improvement (calendar->weekday-aware), holiday-awareness can be layered on next.
    """
    if end_date <= start_date:
        return 0
    count = 0
    current = start_date + timedelta(days=1)
    while current <= end_date:
        if current.weekday() < 5:  # Mon-Fri
            count += 1
        current += timedelta(days=1)
    return count

if __name__ == "__main__":
    from datetime import datetime
    # Friday June 19 -> Monday June 22: should be 1 trading day, not 3 calendar days
    fri = datetime(2026, 6, 19)
    mon = datetime(2026, 6, 22)
    print(f"Calendar days Fri->Mon: {(mon - fri).days}")
    print(f"Trading days Fri->Mon: {trading_days_between(fri, mon)}")

    # Sanity: Monday to Thursday same week, should be 3 trading days = 3 calendar days
    thu = datetime(2026, 6, 18)
    print(f"\nCalendar days Mon->Thu: {(thu - datetime(2026,6,15)).days}")
    print(f"Trading days Mon->Thu: {trading_days_between(datetime(2026,6,15), thu)}")
