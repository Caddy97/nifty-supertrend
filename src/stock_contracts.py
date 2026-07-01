LOT_SIZES = {
    "ULTRACEMCO": 50,
    "AMBER":      100,
    "DIXON":      50,
    "BAJFINANCE": 750,
}

STOCK_SYMBOLS = list(LOT_SIZES.keys())

def get_lot_size(symbol):
    return LOT_SIZES.get(symbol, 1)
