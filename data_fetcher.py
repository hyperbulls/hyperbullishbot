import yfinance as yf
from datetime import datetime
from config import TESLA_CHANNEL_ID, CEST, NEWS_API_KEY
from discord import Client, Forbidden
import re
import requests
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

async def get_tesla_channel_posts(client: Client):
    if TESLA_CHANNEL_ID == 0:
        return "Error: Tesla channel ID not configured in .env."
    
    try:
        channel = client.get_channel(TESLA_CHANNEL_ID)
        if not channel:
            return f"Error: Channel with ID {TESLA_CHANNEL_ID} not found or inaccessible."
        
        messages = []
        async for message in channel.history(limit=10):
            if message.content.strip():  # Skip bot messages and empty content
                timestamp = message.created_at.astimezone(CEST).strftime("%Y-%m-%d %H:%M:%S")
                content = message.content.strip()
                
                # Extract full tweet text and embed details (text only)
                tweet_text = content
                if message.embeds:
                    embed_details = []
                    for i, embed in enumerate(message.embeds, 1):
                        embed_dict = {
                            "index": i,
                            "title": embed.title if embed.title else "No title",
                            "description": embed.description if embed.description else "No description",
                            "fields": {field.name: field.value for field in embed.fields} if embed.fields else "No fields",
                            "url": embed.url if embed.url else "No URL",
                            "footer": embed.footer.text if embed.footer and embed.footer.text else "No footer"
                        }
                        embed_details.append(embed_dict)
                    if embed_details:
                        tweet_text = "\n".join(
                            f"Embed {d['index']}: Title: {d['title']}, Description: {d['description']}, "
                            f"Fields: {d['fields']}, URL: {d['url']}, Footer: {d['footer']}"
                            for d in embed_details
                        )
                
                # Extract X URL if present
                url_match = re.search(r'https?://x\.com/[^\s]+/status/(\d+)', content)
                url = url_match.group(0) if url_match else None
                
                # Format message with full details
                msg_line = f"[{timestamp} CEST] {message.author.name}: {tweet_text}"
                if url:
                    msg_line += f" (URL: {url})"
                
                messages.append(msg_line)
        
        # Log the number of posts imported
        if messages:
            print(f"[DEBUG] Imported {len(messages)} Tesla posts from channel {TESLA_CHANNEL_ID}:")
            for i, msg in enumerate(messages, 1):
                print(f"[DEBUG] Full Post {i}:\n{msg}")
        else:
            print(f"[DEBUG] No valid Tesla posts found in channel {TESLA_CHANNEL_ID}")
        
        if not messages:
            return "No recent Tesla-related posts found in the specified channel."
        
        return "Newest Tesla Posts:\n" + "\n".join(messages)
    except Forbidden:
        print(f"[ERROR] Missing permissions to read messages in channel {TESLA_CHANNEL_ID}")
        return f"Error: Missing permissions to read messages in channel {TESLA_CHANNEL_ID}."
    except Exception as e:
        print(f"[ERROR] Failed to fetch Tesla channel posts: {type(e).__name__}: {str(e)}")
        return f"Error: Failed to fetch Tesla channel posts - {str(e)}"

def get_market_and_news_data():
    try:
        # Get current date and time in CEST (set to 10:25 PM CEST, June 27, 2025)
        current_time = datetime(2025, 6, 27, 22, 25).replace(tzinfo=CEST).strftime("%Y-%m-%d %H:%M:%S")
        timestamp = f"Data as of: {current_time} CEST"
        
        # Fetch TSLA data
        tsla = yf.Ticker("TSLA")
        tsla_info = tsla.info
        current_price = tsla_info.get("regularMarketPrice", "N/A")
        previous_close = tsla_info.get("previousClose", "N/A")
        
        if current_price == "N/A" or previous_close == "N/A":
            tsla_data = "Error: Could not retrieve TSLA price data."
        else:
            absolute_gain = current_price - previous_close
            percentage_gain = (absolute_gain / previous_close) * 100
            absolute_gain = round(absolute_gain, 2)
            percentage_gain = round(percentage_gain, 2)
            
            tsla_hist = tsla.history(period="1mo")
            if tsla_hist.empty:
                tsla_data = "Error: Could not retrieve TSLA historical data."
            else:
                closing_prices = tsla_hist["Close"].round(2).tail(5).to_dict()
                price_dev = ", ".join([f"{date.strftime('%Y-%m-%d')}: ${price}" for date, price in closing_prices.items()])
                rsi = calculate_rsi(tsla_hist["Close"]).iloc[-1]
                rsi_value = round(rsi, 2) if rsi is not None and not pd.isna(rsi) else "N/A"
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
                    f"Recent Price Development (last 5 days): {price_dev}"
                )
        
        earnings = tsla.quarterly_financials
        if earnings.empty:
            earnings_data = "Error: Could not retrieve TSLA earnings data."
        else:
            latest_quarter = earnings.columns[0]
            revenue = earnings.loc["Total Revenue", latest_quarter] / 1e9 if "Total Revenue" in earnings.index else "N/A"
            net_income = earnings.loc["Net Income", latest_quarter] / 1e6 if "Net Income" in earnings.index else "N/A"
            eps = tsla_info.get("trailingEps", "N/A")
            if revenue != "N/A":
                revenue = f"${revenue:.2f}B"
            if net_income != "N/A":
                net_income = f"${net_income:.2f}M"
            if eps != "N/A":
                eps = f"${eps:.2f}"
            earnings_data = (
                f"Q1 2025 Earnings: Revenue: {revenue}, EPS: {eps}, Net Income: {net_income}"
            )
        
        vix = yf.Ticker("^VIX")
        spy = yf.Ticker("SPY")
        vix_value = vix.info.get("regularMarketPrice", "N/A")
        spy_current = spy.info.get("regularMarketPrice", "N/A")
        spy_previous_close = spy.info.get("previousClose", "N/A")
        
        spy_hist = spy.history(period="max")
        if spy_hist.empty or vix_value == "N/A" or spy_current == "N/A" or spy_previous_close == "N/A":
            market_mood = "Error: Could not retrieve VIX or SPY data."
        else:
            spy_ath = spy_hist["High"].max()
            spy_percent_from_ath = ((spy_current - spy_ath) / spy_ath) * 100
            spy_percent_from_ath = round(spy_percent_from_ath, 2)
            spy_absolute_gain = spy_current - spy_previous_close
            spy_percentage_gain = (spy_absolute_gain / spy_previous_close) * 100
            spy_absolute_gain = round(spy_absolute_gain, 2)
            spy_percentage_gain = round(spy_percentage_gain, 2)
            vix_sentiment = (
                "Optimism (low volatility)" if vix_value < 15 else
                "Normal" if 15 <= vix_value <= 25 else
                "Turbulence" if 25 < vix_value <= 30 else
                "High fear"
            )
            market_mood = (
                f"Market Mood: VIX: {vix_value:.2f} ({vix_sentiment}), "
                f"SPY: ${spy_current:.2f} (Gain: ${spy_absolute_gain} ({spy_percentage_gain}%), "
                f"{spy_percent_from_ath}% from ATH)"
            )
        
        if not NEWS_API_KEY:
            news_data = "Error: News API key is not configured."
        else:
            news_url = (
                f"https://newsapi.org/v2/top-headlines?"
                f"category=general&language=en&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
            )
            response = requests.get(news_url)
            if response.status_code == 200:
                news_json = response.json()
                articles = news_json.get("articles", [])[:3]
                if not articles:
                    news_data = "No recent world news available."
                else:
                    news_items = [
                        f"{i+1}. {article['title']} ({article['source']['name']}, "
                        f"{datetime.strptime(article['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')})"
                        for i, article in enumerate(articles)
                    ]
                    news_data = "Recent World News:\n" + "\n".join(news_items)
            else:
                news_data = f"Error: Failed to fetch news (status {response.status_code})."
        
        return f"{tsla_data}\n\n{earnings_data}\n\n{market_mood}\n\n{news_data}\n\n{timestamp}"
    except Exception as e:
        print(f"[ERROR] Failed to fetch market, earnings, news, or timestamp data: {type(e).__name__}: {str(e)}")
        return "Error: Failed to fetch TSLA, earnings, market, news, or timestamp data."
