def get_atm_strike(spot_price):
    """
    Rounds Nifty spot price to the nearest 100-strike per the rule:
    - last two digits 1-50  -> round down
    - last two digits 51-99 -> round up
    - last two digits 00    -> stays (already a round hundred)
    """
    base = int(spot_price // 100) * 100
    remainder = spot_price - base

    if remainder == 0:
        return base
    elif 1 <= remainder <= 50:
        return base
    else:  # 51-99
        return base + 100

def get_option_symbol(spot_price, side):
    """
    side: 'BUY' -> CE, 'SELL' -> PE
    Returns the strike and option type.
    """
    strike = get_atm_strike(spot_price)
    option_type = "CE" if side == "BUY" else "PE"
    return strike, option_type

if __name__ == "__main__":
    test_cases = [24030, 24050, 24051, 24099, 24000, 24100, 23999, 24149, 24150, 24151]
    print(f"{'Spot':>10} | {'Strike':>10}")
    print("-" * 25)
    for spot in test_cases:
        strike = get_atm_strike(spot)
        print(f"{spot:>10} | {strike:>10}")
