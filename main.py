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

# === TSLA Data Fetching ===
def calculate_rsi(data, periods=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def get_tsla_data():
    try:
        # Fetch TSLA data using yfinance
        tsla = yf.Ticker("TSLA")
        info = tsla.info
        current_price = info.get("regularMarketPrice", "N/A")
        previous_close = info.get("previousClose", "N/A")
        
        if current_price == "N/A" or previous_close == "N/A":
            return "Error: Could not retrieve TSLA price data."
        
        # Calculate gains
        absolute_gain = current_price - previous_close
        percentage_gain = (absolute_gain / previous_close) * 100
        absolute_gain = round(absolute_gain, 2)
        percentage_gain = round(percentage_gain, 2)
        
        # Get 1-month historical data
        hist = tsla.history(period="1mo")
        if hist.empty:
            return "Error: Could not retrieve TSLA historical data."
        
        # Get last 5 days of closing prices
        closing_prices = hist["Close"].round(2).tail(5).to_dict()
        price_dev = ", ".join([f"{date.strftime('%Y-%m-%d')}: ${price}" for date, price in closing_prices.items()])
        
        # Calculate RSI
        rsi = calculate_rsi(hist["Close"]).iloc[-1]
        rsi_value = round(rsi, 2) if not pd.isna(rsi) else "N/A"
        
        # Additional stats
        market_cap = info.get("marketCap", "N/A")
        pe_ratio = info.get("trailingPE", "N/A")
        if market_cap != "N/A":
            market_cap = f"${market_cap / 1e9:.2f}B"
        if pe_ratio != "N/A":
            pe_ratio = f"{pe_ratio:.2f}"
        
        return (
            f"Current $TSLA data: Price: ${current_price:.2f}, "
            f"Gain: ${absolute_gain} ({percentage_gain}%), "
            f"Market Cap: {market_cap}, P/E Ratio: {pe_ratio}, "
            f"14-day RSI: {rsi_value}\n"
            f"Recent Price Development (last 5 days): {price_dev}"
        )
    except Exception as e:
        print(f"[ERROR] Failed to fetch TSLA data: {type(e).__name__}: {str(e)}")
        return "Error: Failed to fetch TSLA data."

# === Grok API Integration ===
async def query_grok(prompt: str) -> str:
    if not XAI_API_KEY:
        return "Error: xAI API key is not configured. Please contact the bot administrator."
    
    # Read system prompt from grokContent file
    try:
        with open(GROK_CONTENT_FILE, "r") as f:
            system_prompt = f.read().strip()
        print(f"[DEBUG] Loaded system prompt from {GROK_CONTENT_FILE}, length: {len(system_prompt)} characters")
    except FileNotFoundError:
        print(f"[ERROR] {GROK_CONTENT_FILE} not found")
        return f"Error: {GROK_CONTENT_FILE} not found. Please create it with the system prompt."
    except IOError as e:
        print(f"[ERROR] Failed to read {GROK_CONTENT_FILE}: {str(e)}")
        return f"Error: Failed to read {GROK_CONTENT_FILE} - {str(e)}"

    # Fetch TSLA data and append to user prompt
    tsla_data = await get_tsla_data()
    enhanced_prompt = f"{prompt}\n\n{tsla_data}"
    
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "grok-3-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": enhanced_prompt}
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

# === On Ready ===
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

# === Run ===
client.run(TOKEN)
