import os
import discord
from dotenv import load_dotenv
import aiohttp
import asyncio
import yfinance as yf
import pandas as pd

# === Load .env and constants ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
GROK_CONTENT_FILE = "grokContent"
DISCORD_MAX_MESSAGE_LENGTH = 2000

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# === TSLA and Market Data Fetching ===
def calculate_rsi(data, periods=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def get_tsla_data():
    try:
        # Fetch TSLA data
        tsla = yf.Ticker("TSLA")
        tsla_info = tsla.info
        current_price = tsla_info.get("regularMarketPrice", "N/A")
        previous_close = tsla_info.get("previousClose", "N/A")
        
        if current_price == "N/A" or previous_close == "N/A":
            return "Error: Could not retrieve TSLA price data."
        
        # Calculate TSLA gains
        absolute_gain = current_price - previous_close
        percentage_gain = (absolute_gain / previous_close) * 100
        absolute_gain = round(absolute_gain, 2)
        percentage_gain = round(percentage_gain, 2)
        
        # Get TSLA 1-month historical data
        tsla_hist = tsla.history(period="1mo")
        if tsla_hist.empty:
            return "Error: Could not retrieve TSLA historical data."
        
        # Get last 5 days of TSLA closing prices
        closing_prices = tsla_hist["Close"].round(2).tail(5).to_dict()
        price_dev = ", ".join([f"{date.strftime('%Y-%m-%d')}: ${price}" for date, price in closing_prices.items()])
        
        # Calculate TSLA RSI
        rsi = calculate_rsi(tsla_hist["Close"]).iloc[-1]
        rsi_value = round(rsi, 2) if not pd.isna(rsi) else "N/A"
        
        # TSLA additional stats
        market_cap = tsla_info.get("marketCap", "N/A")
        pe_ratio = tsla_info.get("trailingPE", "N/A")
        if market_cap != "N/A":
            market_cap = f"${market_cap / 1e9:.2f}B"
        if pe_ratio != "N/A":
            pe_ratio = f"{pe_ratio:.2f}"
        
        tsla_data = (
            f"Current $TSLA data: Price: ${current_price:.2f}, "
            f"Gain: ${absolute_gain} ({percentage_gain}%), "
            f"Market Cap: {market_cap}, P/E Ratio: {pe_ratio}, "
            f"14-day RSI: {rsi_value}\n"
            f"Recent Price Development (last
