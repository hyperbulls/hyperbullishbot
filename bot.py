import discord
from dotenv import load_dotenv
from config import TOKEN, TESLA_CHANNEL_ID
from data_fetcher import get_tesla_channel_posts, get_market_and_news_data
from grok_api import query_grok
import os
import re

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
        # Build the full query with direct message, quoted message, replies, and forwarded messages
        query = message.content
        context = []

        # Clean the direct message
        if client.user in message.mentions:
            query = query.replace(f"<@{client.user.id}>", "").strip()
            query = query.replace(f"<@!{client.user.id}>", "").strip()
        elif message.content.lower().startswith(client.user.name.lower()):
            query = query[len(client.user.name):].strip()
        print(f"[DEBUG] Direct query after cleaning: {query}")

        # Add quoted message (if exists)
        if message.reference and message.reference.message_id:
            print(f"[DEBUG] Detected quoted message with ID: {message.reference.message_id}")
            try:
                quoted_message = await message.channel.fetch_message(message.reference.message_id)
                if quoted_message:
                    quoted_text = quoted_message.content.strip() or "No content"
                    has_embeds = len(quoted_message.embeds) > 0
                    print(f"[DEBUG] Quoted message by {quoted_message.author.name} - Content: {quoted_text}, Has embeds: {has_embeds}")
                    if quoted_message.embeds:
                        for i, embed in enumerate(quoted_message.embeds, 1):
                            embed_text = []
                            if embed.title:
                                embed_text.append(f"Title: {embed.title}")
                            if embed.description:
                                embed_text.append(f"Description: {embed.description}")
                            if embed.fields:
                                for field in embed.fields:
                                    embed_text.append(f"Field - {field.name}: {field.value}")
                            embed_details = "\n".join(embed_text) if embed_text else "No embed details"
                            print(f"[DEBUG] Quoted embed {i}: {embed_details}")
                    context.append(f"quote: Quoted by {quoted_message.author.name}: {quoted_text}")
            except discord.errors.NotFound:
                print(f"[DEBUG] Quoted message {message.reference.message_id} not found")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to fetch quoted message in channel {message.channel.id}")

        # Add forwarded messages (detected via embeds with Discord message URLs) and process embeds
        if message.embeds:
            print(f"[DEBUG] Detected {len(message.embeds)} embeds in current message")
            for i, embed in enumerate(message.embeds, 1):
                if embed.url and "discord.com/channels" in embed.url:
                    print(f"[DEBUG] Embed {i} contains potential forwarded URL: {embed.url}")
                    match = re.search(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)", embed.url)
                    if match:
                        guild_id, channel_id, message_id = match.groups()
                        print(f"[DEBUG] Parsed forwarded message - Guild: {guild_id}, Channel: {channel_id}, Message ID: {message_id}")
                        if int(channel_id) == message.channel.id:  # Same channel
                            try:
                                forwarded_message = await message.channel.fetch_message(int(message_id))
                                if forwarded_message:
                                    forwarded_text = forwarded_message.content.strip() or "No content"
                                    has_embeds = len(forwarded_message.embeds) > 0
                                    print(f"[DEBUG] Forwarded message by {forwarded_message.author.name} - Content: {forwarded_text}, Has embeds: {has_embeds}")
                                    # Extract text from embeds in the forwarded message
                                    embed_text = ""
                                    if forwarded_message.embeds:
                                        for j, fwd_embed in enumerate(forwarded_message.embeds, 1):
                                            embed_parts = []
                                            if fwd_embed.title:
                                                embed_parts.append(f"Title: {fwd_embed.title}")
                                            if fwd_embed.description:
                                                embed_parts.append(f"Description: {fwd_embed.description}")
                                            if fwd_embed.fields:
                                                for field in fwd_embed.fields:
                                                    embed_parts.append(f"Field - {field.name}: {field.value}")
                                            embed_details = "\n".join(embed_parts) if embed_parts else "No embed details"
                                            print(f"[DEBUG] Forwarded embed {j}: {embed_details}")
                                            embed_text += f"\n{embed_details}" if embed_text else embed_details
                                    # Combine raw content and embed text
                                    full_forwarded_text = forwarded_text
                                    if embed_text:
                                        full_forwarded_text = f"{forwarded_text}\n{embed_text}" if forwarded_text else embed_text
                                    if full_forwarded_text:
                                        context.append(f"forwarded: Forwarded by {forwarded_message.author.name}: {full_forwarded_text}")
                            except discord.errors.NotFound:
                                print(f"[DEBUG] Forwarded message {message_id} not found")
                            except discord.errors.Forbidden:
                                print(f"[ERROR] Missing permissions to fetch forwarded message in channel {message.channel.id}")

        # Add replies to the original message
        print(f"[DEBUG] Scanning for replies to message ID: {message.id}")
        async for reply in message.channel.history(limit=10, around=message.created_at):
            if reply.reference and reply.reference.message_id == message.id and reply.id != message.id:
                reply_text = reply.content.strip() or "No content"
                has_embeds = len(reply.embeds) > 0
                print(f"[DEBUG] Reply by {reply.author.name} - Content: {reply_text}, Has embeds: {has_embeds}")
                if reply.embeds:
                    for i, embed in enumerate(reply.embeds, 1):
                        embed_text = []
                        if embed.title:
                            embed_text.append(f"Title: {embed.title}")
                        if embed.description:
                            embed_text.append(f"Description: {embed.description}")
                        if embed.fields:
                            for field in embed.fields:
                                embed_text.append(f"Field - {field.name}: {field.value}")
                        embed_details = "\n".join(embed_text) if embed_text else "No embed details"
                        print(f"[DEBUG] Reply embed {i}: {embed_details}")
                context.append(f"reply: Reply by {reply.author.name}: {reply_text}")

        # Combine context with the direct query
        full_query = query
        if context:
            full_query = f"{query}\n\nContext:\n" + "\n".join(context)
        print(f"[DEBUG] Full query to Grok: {full_query}")

        if not full_query.strip():
            try:
                await message.channel.send("Please ask a question after mentioning me!")
            except discord.errors.Forbidden:
                print(f"[ERROR] Missing permissions to send message in channel {message.channel.id}")
            return

        try:
            async with message.channel.typing():
                # Fetch data for Grok
                market_and_news_data = get_market_and_news_data()  # Synchronous call
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
