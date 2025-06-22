# bot.py
import discord
from dotenv import load_dotenv
from config import TOKEN, TESLA_CHANNEL_ID
from data_fetcher import get_tesla_channel_posts, get_market_and_news_data
from grok_api import query_grok
from utils import cleanup_files
import aiohttp
import os

# Load environment variables (already handled in config.py, but included for safety)
load_dotenv()

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True  # Ensure message history intent is enabled
client = discord.Client(intents=intents)

# === On Ready ===
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

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
                # Fetch data for Grok
                market_and_news_data = await get_market_and_news_data()
                tesla_posts = await get_tesla_channel_posts(client)
                response = await query_grok(query, market_and_news_data, tesla_posts)
                print(f"[DEBUG] Sending mention response: {response[:50]}...")
                
                # Fetch the latest Tesla post and its images
                channel = client.get_channel(TESLA_CHANNEL_ID)
                async for msg in channel.history(limit=1):
                    if msg.embeds:
                        print(f"[DEBUG] Found {len(msg.embeds)} embeds in latest message")
                        image_urls = []
                        for i, embed in enumerate(msg.embeds):
                            print(f"[DEBUG] Processing embed {i + 1}: {embed.to_dict()}")
                            if embed.image and embed.image.url:
                                image_urls.append(embed.image.url)
                                print(f"[DEBUG] Extracted image URL from embed {i + 1}: {embed.image.url}")
                        
                        if image_urls:
                            files = []
                            for i, image_url in enumerate(image_urls):
                                print(f"[DEBUG] Attempting to download image {i} from: {image_url}")
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(image_url) as resp:
                                        print(f"[DEBUG] HTTP response status for {image_url}: {resp.status}")
                                        if resp.status == 200:
                                            image_data = await resp.read()
                                            filename = f"temp_image{i}.png"
                                            print(f"[DEBUG] Downloaded image, saving to: {filename}")
                                            with open(filename, "wb") as f:
                                                f.write(image_data)
                                            files.append(discord.File(filename, filename=f"image{i}.png"))
                                            print(f"[DEBUG] Added file object for: {filename}")
                                        else:
                                            print(f"[ERROR] Failed to download image from {image_url}, status: {resp.status}, reason: {resp.reason}")
                            
                            if files:
                                print(f"[DEBUG] Sending response with {len(files)} files")
                                try:
                                    await message.channel.send(content=response, files=files)
                                    print(f"[DEBUG] Successfully sent response with images")
                                except discord.errors.HTTPException as e:
                                    print(f"[ERROR] Failed to send message with files: {type(e).__name__}: {str(e)}")
                                except Exception as e:
                                    print(f"[ERROR] Unexpected error sending files: {type(e).__name__}: {str(e)}")
                                finally:
                                    cleanup_files([f"temp_image{i}.png" for i in range(len(image_urls))])
                                return
                
                # If no images or error, send text only
                print("[DEBUG] No images to send or error occurred, sending text only")
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

# === Start the Bot ===
if __name__ == "__main__":
    client.run(TOKEN)
