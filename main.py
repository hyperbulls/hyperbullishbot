import os
import discord
from discord import app_commands, File
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv
import random
import yfinance as yf
import matplotlib.pyplot as plt
import io

# === Load .env ===
load_dotenv()

# === Discord Bot Setup ===
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# === Forecasting Logic ===
def calculate_tsla_forecast():
    current_year = datetime.now().year
    stock = yf.Ticker("TSLA")
    data = stock.history(period="1d")
    current_price = data['Close'].iloc[-1] if not data.empty else 250  # fallback

    forecast = []
    for i in range(11):
        year = current_year + i
        base = current_price * (2 ** i)
        forecast.append({
            "year": year,
            "bear": base * 0.5,
            "normal": base,
            "bull": base * 1.5,
            "hyperbull": base * 2
        })
    return forecast

# === /table Command ===
@tree.command(name="table", description="Show Tesla valuation forecast as a table")
async def table(interaction: discord.Interaction):
    forecast = calculate_tsla_forecast()
    lines = ["```", f"{'Year':<6}{'Bear':>12}{'Normal':>12}{'Bull':>12}{'Hyperbull':>12}"]
    for row in forecast:
        lines.append(f"{row['year']:<6}${row['bear']:>11,.0f}${row['normal']:>11,.0f}${row['bull']:>11,.0f}${row['hyperbull']:>11,.0f}")
    lines.append("```")
    await interaction.response.send_message("\n".join(lines))

# === /chart Command ===
@tree.command(name="chart", description="Show Tesla valuation forecast as a chart")
async def chart(interaction: discord.Interaction):
    await interaction.response.defer()
    forecast = calculate_tsla_forecast()

    years = [f["year"] for f in forecast]
    bear = [f["bear"] for f in forecast]
    normal = [f["normal"] for f in forecast]
    bull = [f["bull"] for f in forecast]
    hyper = [f["hyperbull"] for f in forecast]

    plt.figure(figsize=(10, 6))
    plt.plot(years, bear, label="Bear", linestyle='dashed')
    plt.plot(years, normal, label="Normal", linewidth=2)
    plt.plot(years, bull, label="Bull", linestyle='dotted')
    plt.plot(years, hyper, label="Hyperbull", linestyle='dashdot')

    plt.title("Tesla Valuation Forecast")
    plt.xlabel("Year")
    plt.ylabel("Stock Price ($)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await interaction.followup.send("Tesla Valuation Forecast Chart:", file=File(buf, filename="tsla_forecast.png"))

# === On Ready Event ===
@client.event
async def on_ready():
    activity = discord.Game(name="TSLA valuations")
    await client.change_presence(status=discord.Status.online, activity=activity)
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    try:
        synced = await tree.sync()
        print(f"🌍 Synced {len(synced)} global slash command(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"⚠️ Global sync failed: {e}")

# === Run Bot ===
client.run(os.getenv("TOKEN"))
