# (continued from your current file)

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
    await interaction.response.send_message(f"✅ Set {component} to {growth} growth from Q{start_quarter} {start_year} to Q{end_quarter} {end_year}.")

# === /viewgrowth ===
@tree.command(name="viewgrowth", description="View your component growth settings")
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
@tree.command(name="chartdivisions", description="Chart valuation per division")
@app_commands.describe(bullishness="bear, normal, bull, hyperbull")
async def chartdivisions(interaction: discord.Interaction, bullishness: str = "normal"):
    if bullishness not in supported_bull_levels:
        await interaction.response.send_message("❌ Invalid bullishness level.")
        return

    uid = interaction.user.id
    x = [f"{y}Q{q}" for y, q in generate_timeline()]
    y_data = {comp: project_component(uid, comp, bullishness) for comp in supported_components}
    total = [sum(vals) for vals in zip(*y_data.values())]

    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = [0] * len(x)
    for comp in supported_components:
        ax.bar(x, y_data[comp], bottom=bottom, label=comp)
        bottom = [b + v for b, v in zip(bottom, y_data[comp])]
    ax.plot(x, total, color="black", linewidth=2, label="Total")

    ax.set_title(f"Tesla Valuation by Division ({bullishness})")
    ax.set_ylabel("Projected Value ($B)")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    await interaction.response.send_message(file=discord.File(buf, filename="chart.png"))
    plt.close()

# === /chartbulllevels ===
@tree.command(name="chartbulllevels", description="Chart all bull levels for one division")
@app_commands.describe(division="cars, energy, fsd, robotaxi, optimus, dojo, total")
async def chartbulllevels(interaction: discord.Interaction, division: str = "total"):
    if division != "total" and division not in supported_components:
        await interaction.response.send_message("❌ Invalid division.")
        return

    uid = interaction.user.id
    x = [f"{y}Q{q}" for y, q in generate_timeline()]
    fig, ax = plt.subplots(figsize=(12, 6))

    for bull in supported_bull_levels:
        if division == "total":
            all_vals = [project_component(uid, comp, bull) for comp in supported_components]
            y = [sum(vals) for vals in zip(*all_vals)]
        else:
            y = project_component(uid, division, bull)
        ax.plot(x, y, label=bull)

    ax.set_title(f"{division.capitalize()} Valuation Across Bullishness Levels")
    ax.set_ylabel("Projected Value ($B)")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    await interaction.response.send_message(file=discord.File(buf, filename="bulllevels.png"))
    plt.close()

# === Startup ===
@client.event
async def on_ready():
    await client.change_presence(activity=discord.Game(name="Tesla Valuation"))
    print(f"✅ Logged in as {client.user}")
    await tree.sync()

client.run(TOKEN)
