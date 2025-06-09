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
    return [(y, q) for y in range(start_year, end_year+1) for q in range(1, 5)]

def quarters_between(start, end):
    return (end[0] - start[0]) * 4 + (end[1] - start[1]) + 1

# === Component Projection ===
def project_component(user_id, component, bullishness):
    settings = user_settings.get(str(user_id), {}).get(component, default_growth_settings[component])

    growth_type = settings['growth']
    start = settings['start']
    end = settings['end']
    total_quarters = 44
    result = []

    for i, (y, q) in enumerate(generate_timeline()):
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

# === Declare Tree Explicitly for Compatibility ===
tree = app_commands.CommandTree(client)
client.tree = tree
