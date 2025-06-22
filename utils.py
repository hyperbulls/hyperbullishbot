import pandas as pd

def calculate_rsi(prices):
    """
    Calculate the Relative Strength Index (RSI) for a series of prices.
    Args:
        prices (pd.Series): Series of closing prices.
    Returns:
        pd.Series: RSI values.
    """
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
