from datetime import datetime, timedelta
from vix_data import get_vix_history
from skew_analysis import analyze_skew

def find_vix_regime_dates(vix_df, n_samples=4):
    """Pick a spread of dates across the available VIX range (low/mid/high)."""
    recent = vix_df.tail(60)  # last ~60 trading days, where real option data exists
    sorted_by_vix = recent.sort_values("vix")
    n = len(sorted_by_vix)
    indices = [0, n//3, 2*n//3, n-1][:n_samples]
    picks = sorted_by_vix.iloc[indices]
    return picks

if __name__ == "__main__":
    vix_df = get_vix_history(period="2y")
    picks = find_vix_regime_dates(vix_df)
    print("Sampled VIX regime dates:")
    print(picks)
