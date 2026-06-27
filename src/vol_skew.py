import numpy as np

# Measured average implied vol by moneyness, from REAL Kite data (~10 trading days, June 2026 expiry)
# moneyness = (strike - spot) / spot * 100

MEASURED_SKEW_CE = {
    -2.08: 16.18,
    -1.25: 14.95,
    -0.42: 14.13,
    0.00: 13.85,
    0.42: 13.65,
    1.25: 13.48,
    2.08: 13.82,
}

MEASURED_SKEW_PE = {
    -2.18: 15.58,
    -1.41: 14.52,
    -0.65: 13.88,
    -0.07: 13.44,
    0.12: 13.13,
    1.06: 12.16,
    1.94: 12.88,
}

def _build_interp(skew_dict):
    points = sorted(skew_dict.keys())
    ivs = [skew_dict[p] for p in points]
    return points, ivs

_ce_points, _ce_ivs = _build_interp(MEASURED_SKEW_CE)
_pe_points, _pe_ivs = _build_interp(MEASURED_SKEW_PE)

def skewed_vol(flat_vix_pct, spot, strike, option_type):
    """
    Adjusts a flat VIX% into a strike-appropriate implied volatility,
    using the SEPARATELY measured CE/PE skew shapes, scaled to current VIX level.
    Returns volatility as a DECIMAL, ready for black_scholes_price.
    """
    moneyness = (strike - spot) / spot * 100

    if option_type == "CE":
        points, ivs = _ce_points, _ce_ivs
        atm_measured = MEASURED_SKEW_CE[0.00]
    else:
        points, ivs = _pe_points, _pe_ivs
        atm_measured = MEASURED_SKEW_PE[-0.07]  # closest to ATM in our PE sample

    interpolated_iv = np.interp(moneyness, points, ivs)
    scale_factor = flat_vix_pct / atm_measured if atm_measured else 1.0
    adjusted_iv_pct = interpolated_iv * scale_factor
    return adjusted_iv_pct / 100.0

if __name__ == "__main__":
    print("CE tests:")
    for strike in [23500, 24000, 24500]:
        v = skewed_vol(13.2, 24000, strike, "CE")
        print(f"  strike {strike}: {v*100:.2f}%")
    print("\nPE tests:")
    for strike in [23500, 24000, 24500]:
        v = skewed_vol(13.2, 24000, strike, "PE")
        print(f"  strike {strike}: {v*100:.2f}%")
