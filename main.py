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

# === Load .env and constants ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
SETTINGS_FILE = "user_settings.json"

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
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree  # already initialized by discord.py

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

# === Chart: Divisions at one bull level ===
@tree.command(name="chartdivisions", description="Valuation per division at selected bullishness level")
@app_commands.describe(bullishness="Choose a bullishness level")
async def chartdivisions(interaction: discord.Interaction, bullishness: str = "normal"):
    await interaction.response.defer()

    user_id = str(interaction.user.id)
    timeline = generate_timeline()
    labels = [f"{y}Q{q}" for (y, q) in timeline]
    total = [0] * len(timeline)
    plt.figure()

    for component in supported_components:
        values = project_component(user_id, component, bullishness)
        plt.plot(labels, values, label=component)
        total = [a + b for a, b in zip(total, values)]

    plt.plot(labels, total, label="total", linewidth=2, linestyle="--")
    plt.xticks(rotation=45, fontsize=6)
    plt.title(f"Tesla Valuation by Component ({bullishness})")
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    await interaction.followup.send(file=discord.File(buf, "chartdivisions.png"))

# === Chart: One division across all bull levels ===
@tree.command(name="chartbulllevels", description="Compare bullishness levels for one division")
@app_commands.describe(division="cars, energy, fsd, robotaxi, optimus, dojo or total")
async def chartbulllevels(interaction: discord.Interaction, division: str = "total"):
    await interaction.response.defer()

    user_id = str(interaction.user.id)
    timeline = generate_timeline()
    labels = [f"{y}Q{q}" for (y, q) in timeline]

    plt.figure()
    if division == "total":
        for level in supported_bull_levels:
            total = [0] * len(timeline)
            for component in supported_components:
                values = project_component(user_id, component, level)
                total = [a + b for a, b in zip(total, values)]
            plt.plot(labels, total, label=level)
    else:
        if division not in supported_components:
            await interaction.followup.send("Invalid division name.")
            return
        for level in supported_bull_levels:
            values = project_component(user_id, division, level)
            plt.plot(labels, values, label=level)

    plt.xticks(rotation=45, fontsize=6)
    plt.title(f"{division.capitalize()} Valuation across Bullishness Levels")
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    await interaction.followup.send(file=discord.File(buf, "chartbulllevels.png"))

# === On Ready ===
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    try:
        synced = await tree.sync()
        print(f"🌍 Synced {len(synced)} global slash command(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"⚠️ Global sync failed: {e}")

# === Run ===
client.run(TOKEN)
