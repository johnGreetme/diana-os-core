import os
import pandas as pd
import yfinance as yf
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import traceback

def run_forecast(target: str, days_ahead: int) -> str:
    """
    Fetches historical data (via yfinance or CSV) and projects future values
    using Holt-Winters Exponential Smoothing.
    """
    try:
        target = target.strip()
        days_ahead = int(days_ahead)
        
        # 1. Fetch Data
        if os.path.exists(target) and target.endswith('.csv'):
            # Basic CSV parsing (assuming a 'date' or index and a 'value' column)
            try:
                df = pd.read_csv(target, parse_dates=True, index_col=0)
                # Take the first numeric column
                numeric_cols = df.select_dtypes(include='number').columns
                if not len(numeric_cols):
                    return "[FORECAST ERROR] No numeric columns found in CSV."
                ts_data = df[numeric_cols[0]].dropna()
            except Exception as e:
                return f"[FORECAST ERROR] Failed to parse CSV: {e}"
        else:
            # Assume it's a yfinance ticker
            ticker = yf.Ticker(target)
            # Fetch last 2 years of daily data for a decent baseline
            df = ticker.history(period="2y")
            if df.empty:
                return f"[FORECAST ERROR] yfinance could not find data for ticker '{target}'."
            # We forecast the 'Close' price
            ts_data = df['Close'].dropna()
            # yfinance returns timezone-aware index which statsmodels might not like sometimes,
            # so we ensure it's a standard daily frequency or just drop the tz
            ts_data.index = ts_data.index.tz_localize(None)

        if len(ts_data) < 14:
            return "[FORECAST ERROR] Not enough data points to compute Holt-Winters smoothing."

        # 2. Fit Holt-Winters Exponential Smoothing
        # We use additive trend. For seasonal, we can attempt additive with period=5 (trading week)
        # or 7 (calendar week). Let's use no seasonal component by default for stocks 
        # to prevent wild oscillations, treating it as a smoothed trend line as discussed.
        model = ExponentialSmoothing(
            ts_data,
            trend="add",
            seasonal=None, 
            initialization_method="estimated"
        )
        fit_model = model.fit()

        # 3. Forecast
        forecast_values = fit_model.forecast(steps=days_ahead)
        
        # 4. Summarize for the LLM
        current_val = ts_data.iloc[-1]
        projected_val = forecast_values.iloc[-1]
        delta = projected_val - current_val
        pct_change = (delta / current_val) * 100
        
        trend = "UPWARD" if delta > 0 else "DOWNWARD" if delta < 0 else "FLAT"
        
        report = (
            f"[FORECAST RESULTS FOR '{target}']\n"
            f"Algorithm: Holt-Winters Exponential Smoothing (Trend-Only)\n"
            f"Target Window: {days_ahead} days ahead\n"
            f"Latest Actual Value: {current_val:.2f}\n"
            f"Projected Final Value: {projected_val:.2f}\n"
            f"Projected Delta: {delta:+.2f} ({pct_change:+.2f}%)\n"
            f"Mathematical Trend: {trend}\n\n"
            f"Note to Agent: This is a mathematical baseline trendline based purely on historical momentum. "
            f"Quantitative smoothing algorithms cannot account for market volatility or external catalyst events."
        )
        
        return report

    except Exception as e:
        return f"[FORECAST ERROR] Engine failure: {str(e)}\n{traceback.format_exc()}"
