import discord
from dotenv import load_dotenv
from config import TOKEN, TESLA_CHANNEL_ID
from data_fetcher import get_tesla_channel_posts, get_market_and_news_data
from grok_api import query_grok
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
        # Build the full query with direct message, quoted message, and replies
        query = message.content
        context = []

        # Clean the direct message
        if client.user in message.mentions:
            query = query.replace(f"<@{client.user.id}>", "").strip()
            query = query.replace(f"<@!{client.user.id}>", "").strip()
        elif message.content.lower().startswith(client.user.name.lower()):
            query = query[len(client.user.name):].strip()

        # Add quoted message (if exists)
        if message.reference and message.reference.message_id:
            try:
                quoted_message = await message.channel.fetch_message(message.reference.message_id)
                if quoted_message:
                    quoted_text = quoted_message.content.strip() or "No content"
                    context.append(f"Quoted by {quoted_message.author.name}: {quoted_text}")
            except discord.errors.NotFound:
                print(f"[DEBUG] Quoted message {message.reference.message_id} not found")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to fetch quoted message in channel {message.channel.id}")

        # Add replies to the original message
        async for reply in message.channel.history(limit=10, around=message.created_at):
            if reply.reference and reply.reference.message_id == message.id and reply.id != message.id:
                reply_text = reply.content.strip() or "No content"
                context.append(f"Reply by {reply.author.name}: {reply_text}")

        # Combine context with the direct query
        full_query = query
        if context:
            full_query = f"{query}\n\nContext:\n" + "\n".join(context)

        if not full_query.strip():
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
                response = await query_grok(full_query, market_and_news_data, tesla_posts)
                print(f"[DEBUG] Sending mention response: {response[:50]}...")
                
                # Send the response (text only)
                print("[DEBUG] Sending text response")
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
            print(f"[DEBUG] Unexpected error in on_message: {type(e).__name__}: {str(e)}")
            try:
                await message.channel.send("Error: An unexpected error occurred.")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to send error message in channel {message.channel.id}")

# === Start the Bot ===
if __name__ == "__main__":
    client.run(TOKEN)
