"""
WindroseBot — Nitrado server monitor for Discord.
Runs via GitHub Actions on a schedule. Checks server status and posts to Discord.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Config from environment ---
NITRADO_TOKEN = os.environ["NITRADO_TOKEN"]
NITRADO_SERVICE_ID = os.environ["NITRADO_SERVICE_ID"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
DISCORD_ALERT_ROLE_ID = os.environ.get("DISCORD_ALERT_ROLE_ID", "")

NITRADO_API = "https://api.nitrado.net"
STATE_FILE = Path(__file__).parent / "last_state.json"


def get_server_status() -> dict:
    """Fetch gameserver details from Nitrado API."""
    url = f"{NITRADO_API}/services/{NITRADO_SERVICE_ID}/gameservers"
    headers = {"Authorization": f"Bearer {NITRADO_TOKEN}"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    gs = data["data"]["gameserver"]
    return {
        "status": gs.get("status", "unknown"),
        "game": gs.get("game", "unknown"),
        "hostname": gs.get("settings", {}).get("config", {}).get("hostname", gs.get("game_human", "Windrose Server")),
        "ip": gs.get("ip", "unknown"),
        "port": gs.get("port", 0),
        "players_online": gs.get("query", {}).get("player_current", 0),
        "players_max": gs.get("query", {}).get("player_max", 0),
        "query_status": gs.get("query", {}).get("server_name", ""),
    }


def load_last_state() -> dict | None:
    """Load the previous server state from disk."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


def save_state(state: dict):
    """Persist current state for next run."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def status_color(status: str) -> int:
    """Discord embed color based on server status."""
    colors = {
        "started": 0x2ECC71,   # green
        "stopped": 0xE74C3C,   # red
        "restarting": 0xF39C12, # orange
        "stopping": 0xF39C12,
        "suspended": 0x95A5A6,  # gray
    }
    return colors.get(status, 0x95A5A6)


def status_emoji(status: str) -> str:
    emojis = {
        "started": "🟢",
        "stopped": "🔴",
        "restarting": "🟡",
        "stopping": "🟡",
        "suspended": "⚫",
    }
    return emojis.get(status, "⚪")


def build_status_embed(server: dict) -> dict:
    """Build a Discord embed with current server info."""
    status = server["status"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    embed = {
        "title": f"{status_emoji(status)} Windrose Server Status",
        "color": status_color(status),
        "fields": [
            {"name": "Status", "value": status.capitalize(), "inline": True},
            {"name": "Players", "value": f"{server['players_online']}/{server['players_max']}", "inline": True},
            {"name": "Address", "value": f"`{server['ip']}:{server['port']}`", "inline": True},
        ],
        "footer": {"text": f"Last checked: {now}"},
    }

    if server.get("hostname"):
        embed["description"] = server["hostname"]

    return embed


def post_status(server: dict):
    """Post or update the status embed in Discord."""
    embed = build_status_embed(server)
    payload = {
        "username": "WindroseBot",
        "embeds": [embed],
    }
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def post_alert(old_status: str, new_status: str):
    """Post an alert when server status changes."""
    mention = f"<@&{DISCORD_ALERT_ROLE_ID}> " if DISCORD_ALERT_ROLE_ID else ""
    message = f"{mention}Server status changed: **{old_status.capitalize()}** → **{new_status.capitalize()}** {status_emoji(new_status)}"

    payload = {
        "username": "WindroseBot",
        "content": message,
    }
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def main():
    print("Checking Nitrado server status...")

    try:
        server = get_server_status()
    except requests.HTTPError as e:
        print(f"Nitrado API error: {e}")
        sys.exit(1)

    print(f"Server is {server['status']} | Players: {server['players_online']}/{server['players_max']}")

    # Check for status change
    last_state = load_last_state()
    if last_state and last_state.get("status") != server["status"]:
        print(f"Status changed: {last_state['status']} → {server['status']}")
        post_alert(last_state["status"], server["status"])

    # Post current status embed
    post_status(server)

    # Save state for next run
    save_state(server)
    print("Done.")


if __name__ == "__main__":
    main()
