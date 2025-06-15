import os
import json
import math
import random
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import matplotlib.pyplot as plt
import yfinance as yf
from dotenv import load_dotenv
import io
import atexit
import aiohttp
import asyncio

# === Load .env and constants ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
SETTINGS_FILE = "user_settings.json"
DISCORD_MAX_MESSAGE_LENGTH = 2000

# === Global Data ===
user_settings = {}
supported_components = ["cars", "energy", "fsd", "robotaxi", "optimus", "dojo"]
supported_growths = ["linear", "exponential", "sigmoid", "log"]
supported_bull_levels = ["bear", "normal", "bull", "hyperbull"]
default_growth_settings = {
    "cars": {"growth": "log", "start": [2025, 1], "end": [2035, 4]},
    "energy": {"growth": "sigmoid", "start": [2025, 1], "end": [2035, 4]},
    "fsd": {"growth": "sigmoid", "start": [2025, 1], "end": [2032, 4]},
    "optimus": {"growth": "exponential", "start": [2027, 4], "end": [2035, 4]},
    "robotaxi": {"growth": "linear", "start": [2026, 2], "end": [2035, 4]},
    "dojo": {"growth": "linear", "start": [2025, 1], "end": [2035, 4]}
}

# === Load/Save Settings ===
def load_user_settings():
    global user_settings
    try:
        with open(SETTINGS_FILE, "r") as f:
            user_settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        user_settings = {}

def save_user_settings():
    with open(SETTINGS_FILE, "w") as f:
        json.dump(user_settings, f, indent=2)

atexit.register(save_user_settings)
load_user_settings()

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

# === Utility Functions ===
def get_growth_multiplier(progress: float, growth_type: str):
    progress = min(max(progress, 0.0), 1.0)
    if growth_type == "linear":
        return progress
    if growth_type == "exponential":
        return progress ** 2
    if growth_type == "sigmoid":
        x = (progress * 12) - 6
        return 1 / (1 + math.exp(-x))
    if growth_type == "log":
        return math.log1p(progress * (math.e - 1))
    return progress

def generate_timeline(start_year=2025, end_year=2035):
    return [(y, q) for y in range(start_year, end_year + 1) for q in range(1, 5)]

def quarters_between(start, end):
    return (end[0] - start[0]) * 4 + (end[1] - start[1]) + 1

def split_message(content: str, max_length: int = DISCORD_MAX_MESSAGE_LENGTH) -> list:
    """Split a message into chunks of up to max_length characters."""
    if len(content) <= max_length:
        return [content]
    
    chunks = []
    while content:
        if len(content) <= max_length:
            chunks.append(content)
            break
        # Find last space within max_length
        split_index = content[:max_length].rfind(" ")
        if split_index == -1:
            split_index = max_length
        chunks.append(content[:split_index].strip())
        content = content[split_index:].strip()
    
    return [chunk for chunk in chunks if chunk]

# === Valuation ===
def project_component(user_id, component, bullishness):
    settings = user_settings.get(str(user_id), {}).get(component, default_growth_settings[component])
    growth_type = settings['growth']
    start = settings['start']
    end = settings['end']
    timeline = generate_timeline()
    result = []

    for (y, q) in timeline:
        if (y, q) < tuple(start):
            result.append(0)
        elif (y, q) > tuple(end):
            result.append(1)
        else:
            total = quarters_between(start, end)
            now = quarters_between(start, (y, q))
            progress = now / total
            result.append(get_growth_multiplier(progress, growth_type))

    scale = {"bear": 0.5, "normal": 1.0, "bull": 1.5, "hyperbull": 2.5}[bullishness]
    base = {"cars": 100, "energy": 30, "fsd": 20, "robotaxi": 50, "optimus": 60, "dojo": 40}[component]

    return [v * base * scale for v in result]

# === Grok API Integration ===
async def query_grok(prompt: str) -> str:
    if not XAI_API_KEY:
        return "Error: xAI API key is not configured. Please contact the bot administrator."
    
    url = "https://api.x.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "grok-3-mini",
        "messages": [
            {"role": "system", "content": "You are Grok, a helpful AI assistant."},
            {"role": "user", "content": prompt}
        ]
    }

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("choices", [{}])[0].get("message", {}).get("content", "No response received from Grok.")
                else:
                    error_body = await response.text()
                    return f"Error: API request failed with status {response.status}: {response.reason}\nHeaders: {response.headers}\nBody: {error_body[:1000]}"
        except aiohttp.ClientTimeout:
            return "Error: xAI API request timed out."
        except Exception as e:
            return f"Error: Failed to connect to Grok API - {str(e)}"

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
            await message.channel.send("Please ask a question after mentioning me!")
            return

        async with message.channel.typing():
            context = (
                "You are assisting users with a Discord bot that projects Tesla's valuation based on components "
                "(cars, energy, fsd, robotaxi, optimus, dojo) and bullishness levels (bear, normal, bull, hyperbull). "
                "The bot uses growth models (linear, exponential, sigmoid, log) to project valuations from 2025 to 2035. "
                f"User question: {query}"
            )
            
            response = await query_grok(context)
            chunks = split_message(response)
            print(f"[DEBUG] Mention response chunks: {len(chunks)}")  # Debug log
            for i, chunk in enumerate(chunks):
                try:
                    print(f"[DEBUG] Sending chunk {i+1}/{len(chunks)}: {chunk[:50]}...")  # Log first 50 chars
                    await message.channel.send(chunk)
                    await asyncio.sleep(0.5)  # Delay to avoid rate limits
                except discord.errors.HTTPException as e:
                    print(f"[ERROR] Failed to send chunk {i+1}: {e}")
                    await message.channel.send("Error: Failed to send part of the response.")

    await client.process_commands(message)

# === Command: Ask Grok ===
@tree.command(name="askgrok", description="Ask Grok about Tesla valuation or related topics")
@app_commands.describe(question="Your question or prompt for Grok")
async def askgrok(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    
    context = (
        "You are assisting users with a Discord bot that projects Tesla's valuation based on components "
        "(cars, energy, fsd, robotaxi, optimus, dojo) and bullishness levels (bear, normal, bull,
