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
import re

# === Load .env and constants ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
TESLA_CHANNEL_ID = int(os.getenv("TESLA_CHANNEL_ID", "0"))  # Add channel ID to .env
GROK_CONTENT_FILE = "grokContent"
DISCORD_MAX_MESSAGE_LENGTH = 2000

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True  # Ensure message history intent is enabled
client = discord.Client(intents=intents)

# === Helper Function to Fetch Discord Messages and X Post Content ===
async def get_tesla_channel_posts():
    if TESLA_CHANNEL_ID == 0:
        return "Error: Tesla channel ID not configured in .env."
    
    try:
        channel = client.get_channel(TESLA_CHANNEL_ID)
        if not channel:
            return f"Error: Channel with ID {TESLA_CHANNEL_ID} not found or inaccessible."
        
        messages = []
        async for message in channel.history(limit=10):
            if message.content.strip():  # Skip bot messages and empty content
                timestamp = message.created_at.astimezone(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d %H:%M:%S")
                content = message.content.strip()
                
                # Extract tweet text from embed if available
                tweet_text = content
                image_urls = []
                if message.embeds:
                    embed = message.embeds[0]  # First embed for the original tweet
                    if embed.description:  # Tweet text is often in the description field
                        tweet_text = embed.description.strip()
                    elif embed.title:  # Fallback to title if description is absent
                        tweet_text = embed.title.strip()
                    
                    # Extract image URL from the first embed
                    if embed.image and embed.image.url:
                        image_urls.append(embed.image.url)
                    
                    # Handle second embed (quoted tweet) if it exists
                    if len(message.embeds) > 1:
                        quoted_embed = message.embeds[1]
                        quoted_text = None
                        # Try description first
                        if quoted_embed.description:
                            quoted_text = quoted_embed.description.strip()
                        # Try title as fallback
                        elif quoted_embed.title:
                            quoted_text = quoted_embed.title.strip()
                        # Try footer text or fields if available
                        elif quoted_embed.footer and quoted_embed.footer.text:
                            quoted_text = quoted_embed.footer.text.strip()
                        elif quoted_embed.fields:
                            quoted_text = " ".join(field.value.strip() for field in quoted_embed.fields if field.value)
                        
                        # If still no text, use a more informative fallback
                        if quoted_text is None:
                            print(f"[DEBUG] No text fields in second embed: {quoted_embed.to_dict()}")
                            quoted_text = "Quoted tweet text unavailable (check embed structure)"
                        tweet_text += f" quoted: {quoted_text}"
                        
                        # Extract image URL from the quoted embed
                        if quoted_embed.image and quoted_embed.image.url:
                            image_urls.append(quoted_embed.image.url)
                
                # Extract X URL if present
                url_match = re.search(r'https?://x\.com/[^\s]+/status/(\d+)', content)
                url = url_match.group(0) if url_match else None
                
                # Format message with timestamp, author, and tweet text (including quoted text if present)
                msg_line = f"[{timestamp} CEST] {message.author.name}: {tweet_text}"
                if url:
                    msg_line += f" (URL: {url})"
                
                messages.append((msg_line, image_urls))  # Store as tuple with list of image URLs
        
        # Log the number of posts imported with full content and preview
        if messages:
            print(f"[DEBUG] Imported {len(messages)} Tesla posts from channel {TESLA_CHANNEL_ID}:")
            for i, (msg, img_urls) in enumerate(messages, 1):
                print(f"[DEBUG] Full Post {i}: {msg}")  # Log full length post
                if img_urls:
                    for j, img_url in enumerate(img_urls):
                        print(f"[DEBUG] Full Post {i} Image URL {j}: {img_url}")
                preview = msg[50:]  # Skip timestamp and author for preview
                preview = preview[:50] + "..." if len(preview) > 50 else preview
                print(f"[DEBUG] Post {i} Preview: {preview}")
        else:
            print(f"[DEBUG] No valid Tesla posts found in channel {TESLA_CHANNEL_ID}")
        
        if not messages:
            return "No recent Tesla-related posts found in the specified channel."
        
        return "Newest Tesla Posts:\n" + "\n".join(msg for msg, _ in messages)
    except discord.errors.Forbidden:
        print(f"[ERROR] Missing permissions to read messages in channel {TESLA_CHANNEL_ID}")
        return f"Error: Missing permissions to read messages in channel {TESLA_CHANNEL_ID}."
    except Exception as e:
        print(f"[ERROR] Failed to fetch Tesla channel posts: {type(e).__name__}: {str(e)}")
        return f"Error: Failed to fetch Tesla channel posts - {str(e)}"

# === Market, News, Earnings, and Timestamp Data Fetching ===
def calculate_rsi(data, periods=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def get_market_and_news_data():
    try:
        # Get current date and time in CEST (set to 12:21 PM CEST, June 22, 2025 for this context)
        cest = ZoneInfo("Europe/Amsterdam")
        current_time = datetime(2025, 6, 22, 12, 21).replace(tzinfo=cest).strftime("%Y-%m-%d %H:%M:%S")
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
                rsi_value = round(rsi, 2) if not pd.isna(rsi) else "N/A"
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
        print(f"[ERROR] Failed to fetch market, earnings, news, or timestamp data: {type(e).__name__}: {str(e)}")
        return "Error: Failed to fetch TSLA, earnings, market, news, or timestamp data."

# === Grok API Integration ===
async def query_grok(prompt: str) -> str:
    if not XAI_API_KEY:
        return "Error: xAI API key is not configured. Please contact the bot administrator."
    
    try:
        with open(GROK_CONTENT_FILE, "r") as f:
            static_system_prompt = f.read().strip()
        print(f"[DEBUG] Loaded system prompt from {GROK_CONTENT_FILE}, length: {len(static_system_prompt)} characters")
    except FileNotFoundError:
        print(f"[ERROR] Failed to read {GROK_CONTENT_FILE}: File not found")
        return f"Error: {GROK_CONTENT_FILE} not found. Please create it with the system prompt."
    except IOError as e:
        print(f"[ERROR] Failed to read {GROK_CONTENT_FILE}: {str(e)}")
        return f"Error: Failed to read {GROK_CONTENT_FILE} - {str(e)}"

    # Fetch market, news, and Tesla channel posts
    market_and_news_data = await get_market_and_news_data()
    tesla_posts = await get_tesla_channel_posts()
    
    # Construct enhanced system prompt
    enhanced_system_prompt = (
        f"{static_system_prompt}\n\n"
        f"Use the following TSLA, earnings, market, news, and timestamp data in your analysis:\n"
        f"{market_and_news_data}\n\n"
        f"{tesla_posts}"
    )
    
    # Log the full prompt
    full_prompt = (
        f"[DEBUG] Full prompt sent to Grok API:\n"
        f"System Prompt:\n{enhanced_system_prompt}\n\n"
        f"User Query:\n{prompt}"
    )
    print(full_prompt)
    
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
                    print(f"[DEBUG] API request attempt {attempt + 1}, status: {response.status}")
                    if response.status == 200:
                        result = await response.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "No response received from Grok.")
                        print(f"[DEBUG] Grok response length: {len(content)} characters")
                        if len(content) > DISCORD_MAX_MESSAGE_LENGTH:
                            content = content[:DISCORD_MAX_MESSAGE_LENGTH - 50] + "... (truncated due to length)"
                        return content
                    else:
                        error_body = await response.text()
                        return f"Error: API request failed with status {response.status}: {response.reason}\nHeaders: {response.headers}\nBody: {error_body[:1000]}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"[ERROR] API request attempt {attempt + 1} failed: {type(e).__name__}: {str(e)}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            continue
        except Exception as e:
            print(f"[ERROR] Unexpected error in API request: {type(e).__name__}: {str(e)}")
            return f"Error: Failed to connect to Grok API - {str(e)}"
    return "Error: Failed to connect to Grok API after 3 attempts."

# === On Message: Handle Bot Mentions ===
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    bot_mentioned = client.user in message.mentions or message.content.lower().startswith(client.user.name.lower())
    
    if bot_mentioned:
        query = message.content
        if client.user in message.mentions:
            query = query.replace(f"<@{client.user.id}>", "").strip()
            query = query.replace(f"<@!{client.user.id}>", "").strip()
        elif message.content.lower().startswith(client.user.name.lower()):
            query = query[len(client.user.name):].strip()

        if not query:
            try:
                await message.channel.send("Please ask a question after mentioning me!")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to send message in channel {message.channel.id}")
            return

        try:
            async with message.channel.typing():
                response = await query_grok(query)
                print(f"[DEBUG] Sending mention response: {response[:50]}...")
                
                # Fetch the latest Tesla post and its image
                channel = client.get_channel(TESLA_CHANNEL_ID)
                async for msg in channel.history(limit=1):
                    if msg.embeds and msg.embeds[0].image and msg.embeds[0].image.url:
                        image_url = msg.embeds[0].image.url
                        async with aiohttp.ClientSession() as session:
                            async with session.get(image_url) as resp:
                                if resp.status == 200:
                                    image_data = await resp.read()
                                    with open("temp_image.png", "wb") as f:
                                        f.write(image_data)
                                    file = discord.File("temp_image.png", filename="image.png")
                                    await message.channel.send(content=response, file=file)
                                    os.remove("temp_image.png")  # Cleanup
                                    return
                
                # If no image or error, send text only
                await message.channel.send(response)
        except discord.errors.Forbidden:
            print(f"[ERROR] Missing permissions in channel {message.channel.id}")
            try:
                await message.author.send(
                    f"I can't respond in {message.channel.name} due to missing permissions. "
                    "Please ask a server admin to grant me Send Messages permission, or try another channel."
                )
            except discord.errors.Forbidden:
                print(f"[ERROR] Unable to DM user {message.author.id} about permission issue")
        except discord.errors.HTTPException as e:
            print(f"[ERROR] Failed to send mention response: {type(e).__name__}: {str(e)}")
            try:
                await message.channel.send("Error: Failed to send response.")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to send error message in channel {message.channel.id}")
        except Exception as e:
            print(f"[ERROR] Unexpected error in on_message: {type(e).__name__}: {str(e)}")
            try:
                await message.channel.send("Error: An unexpected error occurred.")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to send error message in channel {message.channel.id}")

# === On Ready ===
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

# === Run ===
client.run(TOKEN)
