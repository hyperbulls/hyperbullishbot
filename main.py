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
tree = client.tree

# === Growth Function ===
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

# === Time Series ===
def generate_timeline(start_year=2025, end_year=2035):
    return [(y, q) for y in range(start_year, end_year + 1) for q in range(1, 5)]

def quarters_between(start, end):
    return (end[0] - start[0]) * 4 + (end[1] - start[1]) + 1

# === Component Projection ===
def project_component(user_id, component, bullishness):
    settings = user_settings.get(str(user_id), {}).get(component, default_growth_settings[component])
    growth_type = settings['growth']
    start = settings['start']
    end = settings['end']
    result = []

    for (y, q) in generate_timeline():
        if (y, q) < tuple(start):
            result.append(0)
        elif (y, q) > tuple(end):
            result.append(1)
        else:
            t_total = quarters_between(start, end)
            t_now = quarters_between(start, (y, q))
            progress = t_now / t_total
            result.append(get_growth_multiplier(progress, growth_type))

    scale = {
        "bear": 0.5,
        "normal": 1.0,
        "bull": 1.5,
        "hyperbull": 2.5
    }[bullishness]
    base_value = {
        "cars": 100,
        "energy": 30,
        "fsd": 20,
        "robotaxi": 50,
        "optimus": 60,
        "dojo": 40
    }[component]

    return [v * base_value * scale for v in result]

# === /setgrowth ===
@tree.command(name="setgrowth", description="Set growth settings per component")
@app_commands.describe(
    component="cars, energy, fsd, robotaxi, optimus, dojo",
    growth="linear, exponential, sigmoid, log",
    start_year="e.g. 2025", start_quarter="1-4",
    end_year="e.g. 2032", end_quarter="1-4"
)
async def setgrowth(interaction: discord.Interaction, component: str, growth: str, start_year: int, start_quarter: int, end_year: int, end_quarter: int):
    if component not in supported_components:
        await interaction.response.send_message("❌ Invalid component")
        return
    if growth not in supported_growths:
        await interaction.response.send_message("❌ Invalid growth type")
        return

    uid = str(interaction.user.id)
    user_settings.setdefault(uid, {})
    user_settings[uid][component] = {
        "growth": growth,
        "start": [start_year, start_quarter],
        "end": [end_year, end_quarter]
    }
    save_user_settings()
    await interaction.response.send_message(f"✅ Set {component} to {growth} from Q{start_quarter} {start_year} to Q{end_quarter} {end_year}.")

# === /viewgrowth ===
@tree.command(name="viewgrowth", description="View your growth settings")
async def viewgrowth(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    settings = user_settings.get(uid, {})
    lines = ["📊 Your Growth Settings:"]
    for comp in supported_components:
        cfg = settings.get(comp, default_growth_settings[comp])
        sy, sq = cfg['start']
        ey, eq = cfg['end']
        lines.append(f"• {comp}: {cfg['growth']} from Q{sq} {sy} → Q{eq} {ey}")
    await interaction.response.send_message("\n".join(lines))

# === /chartdivisions ===
@tree.command(name="chartdivisions", description="Show valuation of components for a bullishness level")
@app_commands.describe(bullishness="Choose from: bear, normal, bull, hyperbull")
async def chartdivisions(interaction: discord.Interaction, bullishness: str = "normal"):
    await interaction.response.defer()

    if bullishness not in supported_bull_levels:
        await interaction.followup.send("❌ Invalid bullishness level.")
        return

    timeline = generate_timeline()
    labels = [f"{y} Q{q}" for y, q in timeline]
    components = supported_components
    data = [project_component(interaction.user.id, comp, bullishness) for comp in components]

    plt.figure(figsize=(12, 6))
    bottom = [0] * len(timeline)
    for values, label in zip(data, components):
        plt.bar(labels, values, bottom=bottom, label=label)
        bottom = [b + v for b, v in zip(bottom, values)]

    plt.title(f"Tesla Component Valuation — {bullishness.capitalize()} Case")
    plt.xlabel("Quarter")
    plt.ylabel("Value ($B)")
    plt.xticks(rotation=45, ha='right', fontsize=8)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await interaction.followup.send(file=discord.File(buf, filename="chartdivisions.png"))

# === /chartbulllevels ===
@tree.command(name="chartbulllevels", description="Show a component's valuation across all bull levels")
@app_commands.describe(division="Component (e.g., cars, energy, robotaxi, fsd, optimus, dojo)")
async def chartbulllevels(interaction: discord.Interaction, division: str = "total"):
    await interaction.response.defer()

    if division != "total" and division not in supported_components:
        await interaction.followup.send("❌ Invalid component.")
        return

    timeline = generate_timeline()
    labels = [f"{y} Q{q}" for y, q in timeline]

    plt.figure(figsize=(12, 6))

    if division == "total":
        for bull in supported_bull_levels:
            total = [0] * len(timeline)
            for comp in supported_components:
                comp_val = project_component(interaction.user.id, comp, bull)
                total = [t + c for t, c in zip(total, comp_val)]
            plt.plot(labels, total, label=bull)
    else:
        for bull in supported_bull_levels:
            values = project_component(interaction.user.id, division, bull)
            plt.plot(labels, values, label=bull)

    title = "Total Valuation" if division == "total" else f"{division.capitalize()} Valuation"
    plt.title(f"{title} across Bullishness Levels")
    plt.xlabel("Quarter")
    plt.ylabel("Value ($B)")
    plt.xticks(rotation=45, ha='right', fontsize=8)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await interaction.followup.send(file=discord.File(buf, filename="chartbulllevels.png"))

# === Startup ===
@client.event
async def on_ready():
    await client.change_presence(activity=discord.Game(name="Tesla Valuation"))
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

    try:
        synced = await tree.sync()
        print(f"🌍 Synced {len(synced)} global slash command(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"⚠️ Failed to sync commands: {e}")

client.run(TOKEN)
