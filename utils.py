import pandas as pd
import os

def calculate_rsi(data, periods=14):
    """Calculate the Relative Strength Index (RSI) for the given data."""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def cleanup_files(filenames):
    """Remove temporary files after use."""
    for filename in filenames:
        if os.path.exists(filename):
            os.remove(filename)
            print(f"[DEBUG] Cleaned up: {filename}")
