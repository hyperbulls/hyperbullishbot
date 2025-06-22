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
                if message.embeds:
                    embed = message.embeds[0]  # First embed for the original tweet
                    if embed.description:  # Tweet text is often in the description field
                        tweet_text = embed.description.strip()
                    elif embed.title:  # Fallback to title if description is absent
                        tweet_text = embed.title.strip()
                    
                    # Handle second embed (quoted tweet) if it exists
                    if len(message.embeds) > 1:
                        quoted_embed = message.embeds[1]
                        quoted_text = quoted_embed.description.strip() if quoted_embed.description else quoted_embed.title.strip() if quoted_embed.title else "Quoted tweet text unavailable"
                        tweet_text += f" quoted: {quoted_text}"
                
                # Extract X URL if present
                url_match = re.search(r'https?://x\.com/[^\s]+/status/(\d+)', content)
                url = url_match.group(0) if url_match else None
                
                # Format message with timestamp, author, and tweet text (including quoted text if present)
                msg_line = f"[{timestamp} CEST] {message.author.name}: {tweet_text}"
                if url:
                    msg_line += f" (URL: {url})"
                
                messages.append(msg_line)  # No character limit to capture full tweet text
        
        # Log the number of posts imported with a preview
        if messages:
            print(f"[DEBUG] Imported {len(messages)} Tesla posts from channel {TESLA_CHANNEL_ID}:")
            for i, msg in enumerate(messages, 1):
                preview = msg[50:]  # Skip timestamp and author for preview
                preview = preview[:
