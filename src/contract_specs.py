# Centralized Nifty contract specifications.
# Update here if NSE revises lot size, strike spacing, etc.

LOT_SIZE = 65              # revised Jan 2026 (was 75)
STRIKE_SPACING = 50        # Nifty strikes trade at 50-point intervals
RISK_FREE_RATE = 0.065     # approx India 6-month T-bill / repo-linked rate, adjust as needed

if __name__ == "__main__":
    print(f"LOT_SIZE = {LOT_SIZE}")
    print(f"STRIKE_SPACING = {STRIKE_SPACING}")
    print(f"RISK_FREE_RATE = {RISK_FREE_RATE}")
