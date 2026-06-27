import math
from scipy.stats import norm

def black_scholes_price(spot, strike, days_to_expiry, volatility, option_type, risk_free_rate=0.065):
    """
    spot: current Nifty spot price
    strike: option strike price
    days_to_expiry: calendar days remaining (will be converted to years)
    volatility: annualized volatility as a decimal (e.g. 0.15 for 15%, typically from VIX/100)
    option_type: 'CE' or 'PE'
    risk_free_rate: annualized, as a decimal

    Returns theoretical premium (in index points, same units as spot).
    """
    if days_to_expiry <= 0:
        # At/after expiry, price = intrinsic value only
        if option_type == "CE":
            return max(spot - strike, 0)
        else:
            return max(strike - spot, 0)

    T = days_to_expiry / 365.0
    sigma = volatility
    r = risk_free_rate

    if sigma <= 0 or T <= 0:
        if option_type == "CE":
            return max(spot - strike, 0)
        else:
            return max(strike - spot, 0)

    d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "CE":
        price = spot * norm.cdf(d1) - strike * math.exp(-r * T) * norm.cdf(d2)
    else:  # PE
        price = strike * math.exp(-r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1)

    return max(price, 0)

if __name__ == "__main__":
    # Sanity check: ATM call, 15 days to expiry, 12% vol
    price = black_scholes_price(
        spot=24000, strike=24000, days_to_expiry=15,
        volatility=0.12, option_type="CE"
    )
    print(f"ATM CE, spot=24000, strike=24000, 15 DTE, 12% vol -> theoretical premium: {price:.2f}")

    # OTM put, same conditions
    price2 = black_scholes_price(
        spot=24000, strike=23800, days_to_expiry=15,
        volatility=0.12, option_type="PE"
    )
    print(f"OTM PE, spot=24000, strike=23800, 15 DTE, 12% vol -> theoretical premium: {price2:.2f}")
