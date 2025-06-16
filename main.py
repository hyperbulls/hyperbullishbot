import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp
import asyncio

# === Load .env and constants ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
GROK_CONTENT_FILE = "grokContent"
DISCORD_MAX_MESSAGE_LENGTH = 2000

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(intents=intents)

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

    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "grok-3-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
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
