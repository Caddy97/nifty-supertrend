from scipy.optimize import brentq
from black_scholes import black_scholes_price

def implied_volatility(real_price, spot, strike, days_to_expiry, option_type, risk_free_rate=0.065):
    """
    Solves for the volatility that makes Black-Scholes match the real market price.
    Returns None if no solution found (e.g. price below intrinsic value).
    """
    if days_to_expiry <= 0 or real_price <= 0:
        return None

    def diff(vol):
        return black_scholes_price(spot, strike, days_to_expiry, vol, option_type, risk_free_rate) - real_price

    try:
        iv = brentq(diff, 0.01, 2.0)
        return iv
    except ValueError:
        return None

if __name__ == "__main__":
    test_price = black_scholes_price(24000, 24000, 15, 0.15, "CE")
    recovered_iv = implied_volatility(test_price, 24000, 24000, 15, "CE")
    print(f"Test price at 15% vol: {test_price:.2f}")
    print(f"Recovered IV: {recovered_iv:.4f} (should be ~0.15)")
