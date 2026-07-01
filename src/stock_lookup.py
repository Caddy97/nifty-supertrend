from auth import get_kite
import pandas as pd
from datetime import datetime, date

_nfo_cache = {}   # { symbol: {instrument_token, tradingsymbol, expiry, lot_size} }
_cache_date = None


def _refresh_cache():
    global _nfo_cache, _cache_date
    kite = get_kite()
    instruments = kite.instruments("NFO")
    df = pd.DataFrame(instruments)
    df["expiry"] = pd.to_datetime(df["expiry"])
    today = pd.Timestamp(datetime.now().date())
    futs = df[df["instrument_type"] == "FUT"].copy()
    upcoming = futs[futs["expiry"] >= today].sort_values("expiry")

    _nfo_cache = {}
    for sym, grp in upcoming.groupby("name"):
        row = grp.iloc[0]
        _nfo_cache[sym] = {
            "instrument_token": int(row["instrument_token"]),
            "tradingsymbol":    row["tradingsymbol"],
            "expiry":           str(row["expiry"].date()),
            "lot_size":         int(row["lot_size"]),
        }
    _cache_date = date.today()
    print(f"[StockLookup] NFO cache refreshed — {len(_nfo_cache)} futures loaded")


def get_stock_future(symbol):
    """Return nearest unexpired monthly future token for a stock (cached per day)."""
    global _cache_date
    if _cache_date != date.today() or symbol not in _nfo_cache:
        try:
            _refresh_cache()
        except Exception as e:
            print(f"[StockLookup] Cache refresh failed: {e}")
            return None
    return _nfo_cache.get(symbol)


def preload_cache():
    """Call once at startup to warm the cache."""
    try:
        _refresh_cache()
    except Exception as e:
        print(f"[StockLookup] Preload failed: {e}")


if __name__ == "__main__":
    preload_cache()
    for sym in ["ULTRACEMCO", "AMBER", "DIXON", "BAJFINANCE"]:
        print(sym, get_stock_future(sym))
