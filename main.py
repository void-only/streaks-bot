import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Mini web server for Render free tier ---
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Streaks Bot is alive!')

def run_server():
    httpd = HTTPServer(('0.0.0.0', 8080), PingHandler)
    httpd.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# -------- Discord Bot Code --------

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

DATA_FILE = 'levels.json'
COOLDOWN_SECONDS = 60

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

user_data = load_data()
user_cooldowns = {}  # {(guild_id, user_id): datetime} dict

def get_xp_for_level(level):
    return level * 100

def get_icon_for_level(level):
    if level < 10:
        return '🔥'
    elif level < 50:
        return '💎'
    elif level < 100:
        return '🏅'
    elif level < 150:
        return '💯'
    else:
        return '∞'

async def update_nickname(member, level):
    icon = get_icon_for_level(level)
    display_level = level if level < 150 else '∞'
    base_name = member.name
    max_nick_length = 32
    new_nick = f"{base_name} {icon} {display_level}"
    if len(new_nick) > max_nick_length:
        base_name = base_name[:max_nick_length - len(icon) - len(str(display_level)) - 2]
        new_nick = f"{base_name} {icon} {display_level}"
    try:
        if member.guild.me.top_role > member.top_role:
            await member.edit(nick=new_nick)
    except Exception as e:
        print(f"Failed to update nickname for {member.name}: {e}")

def get_blacklist(guild_id):
    try:
        return user_data[str(guild_id)]['blacklist']
    except Exception:
        return []

def set_blacklist(guild_id, channels):
    user_data.setdefault(str(guild_id), {})
    user_data[str(guild_id)]['blacklist'] = channels
    save_data(user_data)

def ensure_user_entry(guild_id, user_id):
    user_data.setdefault(str(guild_id), {})
    if 'users' not in user_data[str(guild_id)]:
        user_data[str(guild_id)]['users'] = {}
    if str(user_id) not in user_data[str(guild_id)]['users']:
        user_data[str(guild_id)]['users'][str(user_id)] = {"xp": 0, "level": 1}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    guild_id = message.guild.id
    user_id = message.author.id
    channel_id = message.channel.id
    blacklist = get_blacklist(guild_id)
    if channel_id in blacklist:
        return
    ensure_user_entry(guild_id, user_id)
    now = datetime.datetime.now().timestamp()
    cooldown_id = (guild_id, user_id)
    last_time = user_cooldowns.get(cooldown_id, 0)
    if now - last_time < COOLDOWN_SECONDS:
        return
    user_cooldowns[cooldown_id] = now
    pdata = user_data[str(guild_id)]['users'][str(user_id)]
    pdata['xp'] += 10
    current_level = pdata['level']
    current_xp = pdata['xp']
    xp_needed = get_xp_for_level(current_level)
    leveled_up = False
    while current_xp >= xp_needed and current_level < 151:
        pdata['level'] += 1
        pdata['xp'] = 0
        current_level = pdata['level']
        current_xp = pdata['xp']
        xp_needed = get_xp_for_level(current_level)
        leveled_up = True
    save_data(user_data)
    if leveled_up:
        await update_nickname(message.author, current_level)
        icon = get_icon_for_level(current_level)
        embed = discord.Embed(
            title="🚀 LEVEL UP!",
            description=f"{message.author.mention} reached level {icon} **{current_level if current_level < 150 else '∞'}**!",
            color=discord.Color.gold()
        )
        embed.add_field(name="Current XP", value=f"{current_xp}/{xp_needed if current_level < 150 else 'MAX'}")
        embed.set_thumbnail(url=message.author.display_avatar.url)
        if current_level == 10:
            embed.add_field(name="Milestone!", value="💎 You’ve hit level 10! Keep it up!", inline=False)
        if current_level == 50:
            embed.add_field(name="Milestone!", value="🏅 Level 50! You’re unstoppable!", inline=False)
        if current_level == 100:
            embed.add_field(name="Milestone!", value="💯 Legendary—LEVEL 100!", inline=False)
        if current_level == 150:
            embed.add_field(name="Infinity!", value="∞ MAX LEVEL! You are a legend!", inline=False)
        await message.channel.send(embed=embed)

@bot.tree.command(name="rank", description="Check your current level and XP.")
async def rank(interaction: discord.Interaction, user: discord.Member = None):
    user = user or interaction.user
    guild_id = interaction.guild.id
    user_id = user.id
    ensure_user_entry(guild_id, user_id)
    data = user_data[str(guild_id)]['users'][str(user_id)]
    level = data['level']
    xp = data['xp']
    xp_needed = get_xp_for_level(level)
    icon = get_icon_for_level(level)
    embed = discord.Embed(title=f"{user.display_name}'s Rank", color=discord.Color.orange())
    embed.add_field(name="Level", value=f"{icon} {level if level < 150 else '∞'}", inline=True)
    embed.add_field(name="XP", value=f"{xp}/{xp_needed if level < 150 else 'MAX'}", inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

def admin_check(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

@bot.tree.command(name="addlevel", description="Increase a member's level by X.")
@app_commands.describe(member="Member to add levels to", amount="Amount to add")
async def addlevel(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not admin_check(interaction):
        await interaction.response.send_message("You lack admin permissions.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    user_id = member.id
    ensure_user_entry(guild_id, user_id)
    user_data[str(guild_id)]['users'][str(user_id)]['level'] += amount
    save_data(user_data)
    await update_nickname(member, user_data[str(guild_id)]['users'][str(user_id)]['level'])
    await interaction.response.send_message(f"Added {amount} level(s) to {member.mention}!")

@bot.tree.command(name="removelevel", description="Decrease a member's level by X.")
@app_commands.describe(member="Member to remove levels from", amount="Amount to remove")
async def removelevel(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not admin_check(interaction):
        await interaction.response.send_message("You lack admin permissions.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    user_id = member.id
    ensure_user_entry(guild_id, user_id)
    prev = user_data[str(guild_id)]['users'][str(user_id)]['level']
    user_data[str(guild_id)]['users'][str(user_id)]['level'] = max(prev - amount, 1)
    save_data(user_data)
    await update_nickname(member, user_data[str(guild_id)]['users'][str(user_id)]['level'])
    await interaction.response.send_message(f"Removed {amount} level(s) from {member.mention}!")

@bot.tree.command(name="resetlevel", description="Reset a member's level to 1.")
@app_commands.describe(member="Member to reset level for")
async def resetlevel(interaction: discord.Interaction, member: discord.Member):
    if not admin_check(interaction):
        await interaction.response.send_message("You lack admin permissions.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    user_id = member.id
    ensure_user_entry(guild_id, user_id)
    user_data[str(guild_id)]['users'][str(user_id)]['level'] = 1
    user_data[str(guild_id)]['users'][str(user_id)]['xp'] = 0
    save_data(user_data)
    await update_nickname(member, 1)
    await interaction.response.send_message(f"Reset {member.mention}'s level to 1!")

@bot.tree.command(name="blacklist", description="Manage XP blacklist channels.")
@app_commands.describe(subcommand="add/remove/list", channel="Channel to add/remove")
async def blacklist(interaction: discord.Interaction, subcommand: str, channel: discord.TextChannel = None):
    if not admin_check(interaction):
        await interaction.response.send_message("You lack admin permissions.", ephemeral=True)
        return
    guild_id = interaction.guild.id
    channels = get_blacklist(guild_id)
    if subcommand == "list":
        if channels:
            channel_mentions = [f"<#{cid}>" for cid in channels]
            await interaction.response.send_message(f"Blacklisted channels: {', '.join(channel_mentions)}", ephemeral=True)
        else:
            await interaction.response.send_message("No channels blacklisted.", ephemeral=True)
    elif subcommand == "add" and channel:
        if channel.id not in channels:
            channels.append(channel.id)
            set_blacklist(guild_id, channels)
            await interaction.response.send_message(f"Added {channel.mention} to blacklist.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{channel.mention} is already blacklisted.", ephemeral=True)
    elif subcommand == "remove" and channel:
        if channel.id in channels:
            channels.remove(channel.id)
            set_blacklist(guild_id, channels)
            await interaction.response.send_message(f"Removed {channel.mention} from blacklist.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{channel.mention} is not in blacklist.", ephemeral=True)
    else:
        await interaction.response.send_message("Invalid subcommand or missing channel.", ephemeral=True)

bot.run(os.getenv('DISCORD_TOKEN'))
