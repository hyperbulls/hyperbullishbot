import os
import discord
from dotenv import load_dotenv
import aiohttp
import asyncio
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import tweepy
import re
import json

# === Load .env and Constants ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TESLA_CHANNEL_ID = int(os.getenv("TESLA_CHANNEL_ID", "0"))
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
GROK_CONTENT_FILE = "grokContent"
DISCORD_MAX_MESSAGE_LENGTH = 2000
TWEET_CACHE_FILE = "tweet_cache.json"

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
client = discord.Client(intents=intents)

# === Tweet Cache Functions ===
def load_tweet_cache():
    """Load cached tweets from file."""
    if os.path.exists(TWEET_CACHE_FILE):
        try:
            with open(TWEET_CACHE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"[ERROR] Invalid JSON in {TWEET_CACHE_FILE}, resetting cache")
            return {}
    return {}

def save_tweet_cache(cache):
    """Save cached tweets to file."""
    try:
        with open(TWEET_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except IOError as e:
        print(f"[ERROR] Failed to save tweet cache: {str(e)}")

# === Helper Function to Fetch Discord Channel Posts ===
async def get_tesla_channel_posts():
    """Fetch recent posts from the Tesla Discord channel (no X API calls)."""
    if TESLA_CHANNEL_ID == 0:
        return "Error: Tesla channel ID not configured in .env."
    
    try:
        channel = client.get_channel(TESLA_CHANNEL_ID)
        if not channel:
            return f"Error: Channel with ID {TESLA_CHANNEL_ID} not found or inaccessible."
        
        messages = []
        async for message in channel.history(limit=10):
            if message.content.strip() and not message.author.bot:
                timestamp = message.created_at.astimezone(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M:%S")
                content = message.content.strip()
                msg_line = f"[{timestamp} CEST] {message.author.name}: {content[:200]}"
                messages.append(msg_line)
        
        if messages:
            print(f"[DEBUG] Imported {len(messages)} Tesla posts from channel {TESLA_CHANNEL_ID}")
        else:
            print(f"[DEBUG] No valid Tesla posts found in channel {TESLA_CHANNEL_ID}")
        
        return "Newest Tesla Posts:\n" + "\n".join(messages) if messages else "No recent Tesla-related posts found."
    except discord.errors.Forbidden:
        print(f"[ERROR] Missing permissions to read messages in channel {TESLA_CHANNEL_ID}")
        return f"Error: Missing permissions to read messages in channel {TESLA_CHANNEL_ID}."
    except Exception as e:
        print(f"[ERROR] Failed to fetch Tesla channel posts: {type(e).__name__}: {str(e)}")
        return f"Error: Failed to fetch Tesla channel posts - {str(e)}"

# === Fetch Tweet Content (Only When X Link Provided) ===
async def fetch_tweet_content(tweet_id: str, x_client: tweepy.Client):
    """Fetch tweet content from X API or cache, with error handling."""
    cache = load_tweet_cache()
    if tweet_id in cache:
        print(f"[DEBUG] Loaded tweet {tweet_id} from cache")
        return cache[tweet_id][:200]
    
    try:
        tweet = x_client.get_tweet(id=tweet_id, tweet_fields=["created_at", "text"])
        if tweet.data:
            text = tweet.data.text[:200]
            cache[tweet_id] = text
            save_tweet_cache(cache)
            print(f"[DEBUG] Fetched tweet {tweet_id}: {text[:50]}...")
            return text
        else:
            print(f"[DEBUG] No data returned for tweet {tweet_id}")
            return f"No data available for X post {tweet_id}"
    except tweepy.TweepyException as e:
        print(f"[ERROR] Failed to fetch X post {tweet_id}: {str(e)}")
        if "401" in str(e):
            return f"Error: Unauthorized access to X post {tweet_id} (check credentials or tweet visibility)"
        elif "404" in str(e):
            return f"Error: X post {tweet_id} not found (may be deleted or private)"
        elif "429" in str(e):
            return f"Error: Exceeded Free tier read limit (100 requests/month) for X post {tweet_id}"
        else:
            return f"Error fetching X post {tweet_id}: {str(e)}"

# === Market, News, and Earnings Data ===
def calculate_rsi(data, periods=14):
    """Calculate 14-day RSI for a given price series."""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def get_market_and_news_data():
    """Fetch TSLA, market, earnings, and news data."""
    try:
        cest = ZoneInfo("Europe/Amsterdam")
        current_time = datetime.now(cest).strftime("%Y-%m-%d %H:%M:%S")
        timestamp = f"Data as of: {current_time} CEST"
        
        # TSLA Data
        tsla = yf.Ticker("TSLA")
        tsla_info = tsla.info
        current_price = tsla_info.get("regularMarketPrice", "N/A")
        previous_close = tsla_info.get("previousClose", "N/A")
        
        if current_price == "N/A" or previous_close == "N/A":
            tsla_data = "Error: Could not retrieve TSLA price data."
        else:
            absolute_gain = round(current_price - previous_close, 2)
            percentage_gain = round((absolute_gain / previous_close) * 100, 2)
            tsla_hist = tsla.history(period="1mo")
            if tsla_hist.empty:
                tsla_data = "Error: Could not retrieve TSLA historical data."
            else:
                closing_prices = tsla_hist["Close"].round(2).tail(5).to_dict()
                price_dev = ", ".join([f"{date.strftime('%Y-%m-%d')}: ${price}" for date, price in closing_prices.items()])
                rsi = calculate_rsi(tsla_hist["Close"]).iloc[-1]
                rsi_value = round(rsi, 2) if not pd.isna(rsi) else "N/A"
                market_cap = tsla_info.get("marketCap", "N/A")
                pe_ratio = tsla_info.get("trailingPE", "N/A")
                market_cap = f"${market_cap / 1e9:.2f}B" if market_cap != "N/A" else "N/A"
                pe_ratio = f"{pe_ratio:.2f}" if pe_ratio != "N/A" else "N/A"
                tsla_data = (
                    f"Current $TSLA data: Price: ${current_price:.2f}, "
                    f"Gain: ${absolute_gain} ({percentage_gain}%), "
                    f"Market Cap: {market_cap}, P/E Ratio: {pe_ratio}, "
                    f"14-day RSI: {rsi_value}\n"
                    f"Recent Price Development: {price_dev}"
                )
        
        # Earnings Data
        earnings = tsla.quarterly_financials
        if earnings.empty:
            earnings_data = "Error: Could not retrieve TSLA earnings data."
        else:
            latest_quarter = earnings.columns[0]
            revenue = earnings.loc["Total Revenue", latest_quarter] / 1e9 if "Total Revenue" in earnings.index else "N/A"
            net_income = earnings.loc["Net Income", latest_quarter] / 1e6 if "Net Income" in earnings.index else "N/A"
            eps = tsla_info.get("trailingEps", "N/A")
            revenue = f"${revenue:.2f}B" if revenue != "N/A" else "N/A"
            net_income = f"${net_income:.2f}M" if net_income != "N/A" else "N/A"
            eps = f"${eps:.2f}" if eps != "N/A" else "N/A"
            earnings_data = (
                f"Q1 2025 Earnings: Revenue: {revenue}, EPS: {eps}, Net Income: {net_income}"
            )
        
        # Market Mood (VIX, SPY)
        vix = yf.Ticker("^VIX")
        spy = yf.Ticker("SPY")
        vix_value = vix.info.get("regularMarketPrice", "N/A")
        spy_current = spy.info.get("regularMarketPrice", "N/A")
        spy_previous_close = spy.info.get("previousClose", "N/A")
        
        if vix_value == "N/A" or spy_current == "N/A" or spy_previous_close == "N/A":
            market_mood = "Error: Could not retrieve VIX or SPY data."
        else:
            spy_hist = spy.history(period="max")
            spy_ath = spy_hist["High"].max()
            spy_percent_from_ath = round(((spy_current - spy_ath) / spy_ath) * 100, 2)
            spy_absolute_gain = round(spy_current - spy_previous_close, 2)
            spy_percentage_gain = round((spy_absolute_gain / spy_previous_close) * 100, 2)
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
        
        # News Data
        if not NEWS_API_KEY:
            news_data = "Error: News API key is not configured."
        else:
            news_url = (
                f"https://newsapi.org/v2/top-headlines?"
                f"category=general&language=en&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(news_url) as response:
                    if response.status == 200:
                        news_json = await response.json()
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
                        news_data = f"Error: Failed to fetch news (status {response.status})."
        
        return f"{tsla_data}\n\n{earnings_data}\n\n{market_mood}\n\n{news_data}\n\n{timestamp}"
    except Exception as e:
        print(f"[ERROR] Failed to fetch market/news data: {type(e).__name__}: {str(e)}")
        return f"Error: Failed to fetch market/news data - {str(e)}"

# === Grok API Integration ===
async def query_grok(prompt: str, x_post_text: str = None):
    """Query Grok API with market data, channel posts, and optional X post content."""
    if not XAI_API_KEY:
        return "Error: xAI API key is not configured."
    
    try:
        with open(GROK_CONTENT_FILE, "r") as f:
            static_system_prompt = f.read().strip()
        print(f"[DEBUG] Loaded system prompt from {GROK_CONTENT_FILE}")
    except FileNotFoundError:
        print(f"[ERROR] {GROK_CONTENT_FILE} not found")
        return f"Error: {GROK_CONTENT_FILE} not found."
    except IOError as e:
        print(f"[ERROR] Failed to read {GROK_CONTENT_FILE}: {str(e)}")
        return f"Error: Failed to read {GROK_CONTENT_FILE} - {str(e)}"

    # Fetch market/news data and Tesla channel posts
    market_and_news_data = await get_market_and_news_data()
    tesla_posts = await get_tesla_channel_posts()
    
    # Construct system prompt
    enhanced_system_prompt = (
        f"{static_system_prompt}\n\n"
        f"Market, earnings, news, and timestamp data:\n{market_and_news_data}\n\n"
        f"Tesla Discord channel posts:\n{tesla_posts}"
    )
    if x_post_text:
        enhanced_system_prompt += f"\n\nX Post Content:\n{x_post_text}"
    
    print(f"[DEBUG] System prompt length: {len(enhanced_system_prompt)} chars")
    
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "grok-3-mini",
        "messages": [
            {"role": "system", "content": enhanced_system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    timeout = aiohttp.ClientTimeout(total=20)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    print(f"[DEBUG] Grok API request attempt {attempt + 1}, status: {response.status}")
                    if response.status == 200:
                        result = await response.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "No response from Grok.")
                        if len(content) > DISCORD_MAX_MESSAGE_LENGTH:
                            content = content[:DISCORD_MAX_MESSAGE_LENGTH - 50] + "... (truncated)"
                        return content
                    else:
                        error_body = await response.text()
                        return f"Error: Grok API request failed (status {response.status}): {error_body[:100]}..."
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"[ERROR] Grok API attempt {attempt + 1} failed: {type(e).__name__}: {str(e)}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            continue
    return "Error: Failed to connect to Grok API after 3 attempts."

# === On Message Handler ===
@client.event
async def on_message(message: discord.Message):
    """Handle bot mentions and process X links only when provided."""
    if message.author.bot:
        return

    bot_mentioned = client.user in message.mentions or message.content.lower().startswith(client.user.name.lower())
    if not bot_mentioned:
        return

    # Extract query
    query = message.content
    if client.user in message.mentions:
        query = query.replace(f"<@{client.user.id}>", "").strip()
        query = query.replace(f"<@!{client.user.id}>", "").strip()
    elif message.content.lower().startswith(client.user.name.lower()):
        query = query[len(client.user.name):].strip()

    if not query:
        try:
            await message.channel.send("Please provide a query or X link after mentioning me!")
        except discord.errors.Forbidden:
            print(f"[ERROR] Missing permissions to send in channel {message.channel.id}")
        return

    try:
        async with message.channel.typing():
            # Check for X link in query
            url_match = re.search(r'https?://x\.com/[^\s]+/status/(\d+)', query)
            x_post_text = None
            if url_match:
                tweet_id = url_match.group(1)
                print(f"[DEBUG] Found X link with tweet ID: {tweet_id}")
                print(f"[DEBUG] X API credentials: API_KEY={X_API_KEY[:5]}..., API_SECRET={X_API_SECRET[:5]}..., ACCESS_TOKEN={X_ACCESS_TOKEN[:5]}..., ACCESS_TOKEN_SECRET={X_ACCESS_TOKEN_SECRET[:5]}...")
                
                x_client = tweepy.Client(
                    consumer_key=X_API_KEY,
                    consumer_secret=X_API_SECRET,
                    access_token=X_ACCESS_TOKEN,
                    access_token_secret=X_ACCESS_TOKEN_SECRET
                )
                print("[DEBUG] Initialized Tweepy client for X API (Free tier: 100 reads/month)")
                
                x_post_text = await fetch_tweet_content(tweet_id, x_client)
                print(f"[DEBUG] Tweet content for {tweet_id}: {x_post_text[:50]}...")
            else:
                print("[DEBUG] No X link found in query, skipping X API request")

            # Query Grok with or without X post content
            response = await query_grok(query, x_post_text)
            print(f"[DEBUG] Sending response: {response[:50]}...")
            await message.channel.send(response)
    except discord.errors.Forbidden:
        print(f"[ERROR] Missing permissions in channel {message.channel.id}")
        try:
            await message.author.send(
                f"I can't respond in {message.channel.name} due to missing permissions. "
                "Please grant me Send Messages permission or try another channel."
            )
        except discord.errors.Forbidden:
            print(f"[ERROR] Unable to DM user {message.author.id}")
    except discord.errors.HTTPException as e:
        print(f"[ERROR] Failed to send response: {type(e).__name__}: {str(e)}")
        try:
            await message.channel.send("Error: Failed to send response.")
        except discord.errors.Forbidden:
            print(f"[ERROR] Missing permissions to send error in channel {message.channel.id}")

# === On Ready ===
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

# === Run ===
client.run(TOKEN)
