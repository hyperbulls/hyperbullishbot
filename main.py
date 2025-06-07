import os
import discord
from discord import app_commands
import yfinance as yf
from flask import Flask
from threading import Thread
from datetime import datetime
import random  # add this at the top of your file

# === Flask Web Server to Keep Replit Alive ===
app = Flask('')


@app.route('/')
def home():
    return "I'm alive!"


def run():
    app.run(host='0.0.0.0', port=8080)


Thread(target=run).start()

# === Discord Bot Setup ===
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# === Slash Command: Hello ===
@tree.command(name="predict", description="Predict Tesla's stock price")
@app_commands.describe(year="Target year (must be this year or later)")
async def tesla(interaction: discord.Interaction, year: int):
    current_year = datetime.now().year
    if year < current_year:
        await interaction.response.send_message(
            "❌ Please enter a year that is this year or later.")
        return

    stock = yf.Ticker("TSLA")
    data = stock.history(period="1d")
    if data.empty:
        await interaction.response.send_message(
            "❌ Couldn't fetch Tesla stock data.")
        return

    current_price = data['Close'].iloc[-1]
    years_ahead = year - current_year
    base_prediction = current_price * (2**years_ahead)

    # 🎲 Add random variation ±10%
    fluctuation = random.uniform(-0.10, 0.10)
    final_prediction = base_prediction * (1 + fluctuation)

    await interaction.response.send_message(
        f"📈 Tesla stock in {current_year}: ${current_price:.2f}\n"
        f"🔮 Predicted price in {year}: "
        f"**${final_prediction:,.2f}**")


# === Sync Commands When Bot Is Ready ===
@client.event
async def on_ready():

    # 🎮 Set activity status
    activity = discord.Game(name="with its balls")
    await client.change_presence(status=discord.Status.online,
                                 activity=activity)

    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    try:
        synced = await tree.sync()  # global sync
        print(
            f"🌍 Synced {len(synced)} global slash command(s): {[cmd.name for cmd in synced]}"
        )
    except Exception as e:
        print(f"⚠️ Global sync failed: {e}")


# === Run the Bot ===
client.run(os.getenv("TOKEN"))
