from skew_analysis import analyze_skew

strikes = [23500, 23700, 23900, 24000, 24100, 24300, 24500]
print("=== PE SKEW ===")
rows = analyze_skew(strikes, option_type="PE", days=10)
