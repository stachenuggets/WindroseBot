"""
WindroseBot — Discord bot for Nitrado gameserver monitoring and control.
"""

import os
from datetime import datetime, timezone, timedelta, time

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import requests

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
NITRADO_TOKEN = os.environ["NITRADO_TOKEN"]
NITRADO_SERVICE_ID = os.environ["NITRADO_SERVICE_ID"]
STATUS_CHANNEL_ID = int(os.environ["STATUS_CHANNEL_ID"])
ALERT_ROLE_ID = os.environ.get("ALERT_ROLE_ID", "")

NITRADO_API = "https://api.nitrado.net"

# Track state for change detection
last_known_status = None
status_message_id = None


# --- Nitrado API helpers ---

def nitrado_headers():
    return {"Authorization": f"Bearer {NITRADO_TOKEN}"}


def nitrado_get(path: str) -> dict:
    """GET request to Nitrado API."""
    resp = requests.get(f"{NITRADO_API}{path}", headers=nitrado_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def nitrado_post(path: str, data: dict = None) -> dict:
    """POST request to Nitrado API."""
    resp = requests.post(
        f"{NITRADO_API}{path}", headers=nitrado_headers(), json=data, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def get_server_info() -> dict:
    """Fetch gameserver details from Nitrado."""
    data = nitrado_get(f"/services/{NITRADO_SERVICE_ID}/gameservers")
    gs = data["data"]["gameserver"]
    return {
        "status": gs.get("status", "unknown"),
        "game": gs.get("game", "unknown"),
        "hostname": (
            gs.get("settings", {}).get("config", {}).get("hostname")
            or gs.get("game_human", "Windrose Server")
        ),
        "ip": gs.get("ip", "unknown"),
        "port": gs.get("port", 0),
        "players_online": gs.get("query", {}).get("player_current", "N/A"),
        "players_max": gs.get("query", {}).get("player_max") or gs.get("slots", 0),
        "last_status_change": gs.get("last_status_change"),
    }


def get_full_gameserver() -> dict:
    """Fetch full raw gameserver data."""
    data = nitrado_get(f"/services/{NITRADO_SERVICE_ID}/gameservers")
    return data["data"]["gameserver"]


def server_action(action: str) -> str:
    """Send start/stop/restart to Nitrado. Returns status message."""
    data = nitrado_post(f"/services/{NITRADO_SERVICE_ID}/gameservers/{action}")
    return data.get("message", f"Server {action} command sent.")


# --- Backup helpers ---

def get_backups() -> list:
    """Fetch list of available backups."""
    data = nitrado_get(f"/services/{NITRADO_SERVICE_ID}/gameservers/backups")
    return data.get("data", {}).get("backups", [])


def create_backup() -> str:
    """Create a new backup."""
    data = nitrado_post(f"/services/{NITRADO_SERVICE_ID}/gameservers/backups")
    return data.get("message", "Backup created.")


def restore_backup(backup_id: str) -> str:
    """Restore a backup by ID."""
    data = nitrado_post(
        f"/services/{NITRADO_SERVICE_ID}/gameservers/backups/{backup_id}/restore"
    )
    return data.get("message", "Backup restore initiated.")


# --- Log helpers ---

def get_log_files() -> list:
    """Get list of log files from the server."""
    gs = get_full_gameserver()
    log_files = gs.get("game_specific", {}).get("log_files", [])
    return log_files


def download_file(file_path: str) -> str:
    """Get a download URL for a file on the server, then fetch its content."""
    data = nitrado_get(
        f"/services/{NITRADO_SERVICE_ID}/gameservers/file_server/download"
        f"?file={file_path}"
    )
    token = data.get("data", {}).get("token", {})
    url = token.get("url")
    if not url:
        return "Could not get download URL."
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def list_directory(dir_path: str) -> list:
    """List files in a directory on the server."""
    data = nitrado_get(
        f"/services/{NITRADO_SERVICE_ID}/gameservers/file_server/list"
        f"?dir={dir_path}"
    )
    return data.get("data", {}).get("entries", [])


# --- Embed builders ---

STATUS_COLORS = {
    "started": 0x2ECC71,
    "stopped": 0xE74C3C,
    "restarting": 0xF39C12,
    "stopping": 0xF39C12,
    "suspended": 0x95A5A6,
}

STATUS_EMOJI = {
    "started": "\U0001f7e2",
    "stopped": "\U0001f534",
    "restarting": "\U0001f7e1",
    "stopping": "\U0001f7e1",
    "suspended": "\u26ab",
}


def build_status_embed(info: dict) -> discord.Embed:
    status = info["status"]
    emoji = STATUS_EMOJI.get(status, "\u26aa")
    color = STATUS_COLORS.get(status, 0x95A5A6)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    embed = discord.Embed(
        title=f"{emoji} Windrose Server Status",
        description=info["hostname"],
        color=color,
    )
    embed.add_field(name="Status", value=status.capitalize(), inline=True)
    players = info["players_online"]
    max_p = info["players_max"]
    if players == "N/A":
        player_text = f"—/{max_p} slots"
    else:
        player_text = f"{players}/{max_p}"
    embed.add_field(name="Players", value=player_text, inline=True)
    embed.add_field(
        name="Address",
        value=f"`{info['ip']}:{info['port']}`",
        inline=True,
    )
    embed.set_footer(text=f"Last updated: {now}")
    return embed


def format_uptime(seconds: int) -> str:
    """Format seconds into a human-readable uptime string."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


# --- Bot setup ---

intents = discord.Intents.default()
intents.presences = True
intents.members = True
activity = discord.Activity(type=discord.ActivityType.watching, name="Windrose Server")
bot = discord.Client(intents=intents, activity=activity, status=discord.Status.online)
tree = app_commands.CommandTree(bot)


@bot.event
async def on_ready():
    await tree.sync()
    print(f"WindroseBot online as {bot.user}")
    monitor_loop.start()
    restart_announce_loop.start()


# --- Slash commands ---

@tree.command(name="status", description="Check the Windrose server status")
async def cmd_status(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        info = get_server_info()
        embed = build_status_embed(info)
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Nitrado API error: {e.response.status_code}")


@tree.command(name="start", description="Start the Windrose server")
@app_commands.default_permissions(administrator=True)
async def cmd_start(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        msg = server_action("restart")
        embed = discord.Embed(title="Server Start", description=msg, color=0x2ECC71)
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Failed to start server: {e.response.status_code}")


@tree.command(name="stop", description="Stop the Windrose server")
@app_commands.default_permissions(administrator=True)
async def cmd_stop(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        msg = server_action("stop")
        embed = discord.Embed(title="Server Stop", description=msg, color=0xE74C3C)
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Failed to stop server: {e.response.status_code}")


@tree.command(name="restart", description="Restart the Windrose server")
@app_commands.default_permissions(administrator=True)
async def cmd_restart(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        msg = server_action("restart")
        embed = discord.Embed(
            title="Server Restart", description=msg, color=0xF39C12
        )
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Failed to restart server: {e.response.status_code}")


@tree.command(name="players", description="Show who's online on the Windrose server")
async def cmd_players(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        info = get_server_info()
        count = info["players_online"]
        max_p = info["players_max"]
        if count == "N/A":
            await interaction.followup.send(f"Player count not available — server has **{max_p}** slots")
        elif count == 0:
            await interaction.followup.send(f"No players online (0/{max_p})")
        else:
            await interaction.followup.send(f"**{count}/{max_p}** players online")
    except requests.HTTPError as e:
        await interaction.followup.send(f"Nitrado API error: {e.response.status_code}")


@tree.command(name="save", description="Save the server (creates a backup)")
@app_commands.default_permissions(administrator=True)
async def cmd_save(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        msg = create_backup()
        embed = discord.Embed(
            title="\U0001f4be Server Saved",
            description=msg,
            color=0x2ECC71,
        )
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Save failed: {e.response.status_code}")


@tree.command(name="ip", description="Get the server address")
async def cmd_ip(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        info = get_server_info()
        address = f"{info['ip']}:{info['port']}"
        await interaction.followup.send(f"```\n{address}\n```")
    except requests.HTTPError as e:
        await interaction.followup.send(f"Nitrado API error: {e.response.status_code}")


@tree.command(name="uptime", description="Show how long the server has been running")
async def cmd_uptime(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        info = get_server_info()
        last_change = info.get("last_status_change")
        if not last_change:
            await interaction.followup.send("Uptime data not available.")
            return

        change_time = datetime.fromtimestamp(last_change, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - change_time
        uptime_str = format_uptime(int(delta.total_seconds()))

        status = info["status"]
        if status == "started":
            emoji = "\U0001f7e2"
            msg = f"{emoji} Server has been **online** for **{uptime_str}**"
        else:
            emoji = STATUS_EMOJI.get(status, "\u26aa")
            msg = f"{emoji} Server has been **{status}** for **{uptime_str}**"

        embed = discord.Embed(
            title="Server Uptime",
            description=msg,
            color=STATUS_COLORS.get(status, 0x95A5A6),
        )
        embed.add_field(
            name="Since",
            value=change_time.strftime("%Y-%m-%d %H:%M UTC"),
            inline=True,
        )
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Nitrado API error: {e.response.status_code}")


# --- Backup commands ---

backup_group = app_commands.Group(name="backup", description="Server backup commands")


@backup_group.command(name="create", description="Create a new server backup")
@app_commands.default_permissions(administrator=True)
async def cmd_backup_create(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        msg = create_backup()
        embed = discord.Embed(
            title="Backup Created",
            description=msg,
            color=0x3498DB,
        )
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Backup failed: {e.response.status_code}")


@backup_group.command(name="list", description="List available server backups")
@app_commands.default_permissions(administrator=True)
async def cmd_backup_list(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        backups = get_backups()
        if not backups:
            await interaction.followup.send("No backups found.")
            return

        embed = discord.Embed(
            title="Server Backups",
            color=0x3498DB,
        )
        for i, backup in enumerate(backups[:10]):
            backup_id = backup.get("id", "unknown")
            created = backup.get("created_at", backup.get("timestamp", "unknown"))
            size = backup.get("size", "unknown")
            if isinstance(size, (int, float)):
                size = f"{size / 1024 / 1024:.1f} MB"
            embed.add_field(
                name=f"#{i + 1} — {backup_id}",
                value=f"Created: {created}\nSize: {size}",
                inline=False,
            )

        if len(backups) > 10:
            embed.set_footer(text=f"Showing 10 of {len(backups)} backups")

        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Failed to list backups: {e.response.status_code}")


@backup_group.command(name="restore", description="Restore a server backup by ID")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(backup_id="The backup ID to restore (use /backup list to find it)")
async def cmd_backup_restore(interaction: discord.Interaction, backup_id: str):
    await interaction.response.defer()
    try:
        msg = restore_backup(backup_id)
        embed = discord.Embed(
            title="Backup Restore",
            description=msg,
            color=0xF39C12,
        )
        await interaction.followup.send(embed=embed)
    except requests.HTTPError as e:
        await interaction.followup.send(f"Restore failed: {e.response.status_code}")


tree.add_command(backup_group)


# --- Logs command ---

@tree.command(name="logs", description="Pull recent server logs")
@app_commands.default_permissions(administrator=True)
async def cmd_logs(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        gs = get_full_gameserver()
        log_files = gs.get("game_specific", {}).get("log_files", [])
        base_path = gs.get("game_specific", {}).get("path", "")

        # If no log files defined, try to find them in the server directory
        if not log_files:
            try:
                entries = list_directory(base_path)
                log_files = [
                    e["name"] for e in entries
                    if e.get("type") == "file"
                    and any(e["name"].endswith(ext) for ext in (".log", ".txt"))
                ]
                log_files = [f"{base_path}{f}" for f in log_files[:5]]
            except Exception:
                pass

        if not log_files:
            # Try common log locations
            common_paths = [
                f"{base_path}logs/",
                f"{base_path}Logs/",
                f"{base_path}log/",
            ]
            for log_dir in common_paths:
                try:
                    entries = list_directory(log_dir)
                    log_files = [
                        f"{log_dir}{e['name']}" for e in entries
                        if e.get("type") == "file"
                    ]
                    if log_files:
                        log_files = log_files[-3:]  # Last 3 log files
                        break
                except Exception:
                    continue

        if not log_files:
            await interaction.followup.send("No log files found on the server.")
            return

        # Download the most recent log file
        log_path = log_files[-1] if isinstance(log_files[-1], str) else log_files[-1]
        try:
            content = download_file(log_path)
        except Exception as e:
            await interaction.followup.send(f"Could not download log: {e}")
            return

        # Truncate to last 1500 chars to fit in Discord
        if len(content) > 1500:
            content = "...\n" + content[-1500:]

        filename = log_path.split("/")[-1] if "/" in log_path else log_path
        embed = discord.Embed(
            title=f"Server Log — {filename}",
            description=f"```\n{content}\n```",
            color=0x95A5A6,
        )
        await interaction.followup.send(embed=embed)

    except requests.HTTPError as e:
        await interaction.followup.send(f"Failed to fetch logs: {e.response.status_code}")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


# --- Auto-monitoring loop ---

@tasks.loop(minutes=5)
async def monitor_loop():
    global last_known_status, status_message_id

    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        print(f"Could not find channel {STATUS_CHANNEL_ID}")
        return

    try:
        info = get_server_info()
    except Exception as e:
        print(f"Monitor error: {e}")
        return

    new_status = info["status"]

    # Alert on status change
    if last_known_status is not None and last_known_status != new_status:
        emoji = STATUS_EMOJI.get(new_status, "\u26aa")
        mention = f"<@&{ALERT_ROLE_ID}> " if ALERT_ROLE_ID else ""
        alert = (
            f"{mention}Server status changed: "
            f"**{last_known_status.capitalize()}** → **{new_status.capitalize()}** {emoji}"
        )
        await channel.send(alert)

    last_known_status = new_status

    # Update or post the status embed
    embed = build_status_embed(info)
    if status_message_id:
        try:
            msg = await channel.fetch_message(status_message_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    msg = await channel.send(embed=embed)
    status_message_id = msg.id


@monitor_loop.before_loop
async def before_monitor():
    await bot.wait_until_ready()


# --- Scheduled restart announcement ---
# Restart is at 16:09 UTC (9:09 AM UTC-7) daily
RESTART_HOUR_UTC = 16
RESTART_MINUTE_UTC = 9
restart_warning_sent_today = False


@tasks.loop(minutes=1)
async def restart_announce_loop():
    global restart_warning_sent_today

    now = datetime.now(timezone.utc)
    restart_time = now.replace(hour=RESTART_HOUR_UTC, minute=RESTART_MINUTE_UTC, second=0, microsecond=0)
    warning_time = restart_time - timedelta(minutes=5)

    # Reset the flag after the restart window passes
    if now.hour == RESTART_HOUR_UTC and now.minute > RESTART_MINUTE_UTC + 5:
        restart_warning_sent_today = False

    # Post 5-minute warning
    if not restart_warning_sent_today and now >= warning_time and now < restart_time:
        channel = bot.get_channel(STATUS_CHANNEL_ID)
        if channel:
            mention = f"<@&{ALERT_ROLE_ID}> " if ALERT_ROLE_ID else ""
            embed = discord.Embed(
                title="\U0001f7e1 Scheduled Restart in 5 Minutes",
                description=f"{mention}The Windrose server will restart at "
                            f"<t:{int(restart_time.timestamp())}:t>. "
                            f"Save your progress!",
                color=0xF39C12,
            )
            await channel.send(embed=embed)
            restart_warning_sent_today = True


@restart_announce_loop.before_loop
async def before_restart_announce():
    await bot.wait_until_ready()


bot.run(DISCORD_TOKEN)
