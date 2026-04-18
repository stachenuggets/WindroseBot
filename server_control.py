"""
WindroseBot — Nitrado server start/stop/restart control.
Triggered via GitHub Actions workflow_dispatch.
"""

import os
import sys

import requests

NITRADO_TOKEN = os.environ["NITRADO_TOKEN"]
NITRADO_SERVICE_ID = os.environ["NITRADO_SERVICE_ID"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

NITRADO_API = "https://api.nitrado.net"


def server_action(action: str):
    """Send a start/stop/restart command to the Nitrado server."""
    url = f"{NITRADO_API}/services/{NITRADO_SERVICE_ID}/gameservers/{action}"
    headers = {"Authorization": f"Bearer {NITRADO_TOKEN}"}
    resp = requests.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def notify_discord(action: str, success: bool, message: str = ""):
    """Post action result to Discord."""
    status_text = "Success" if success else "Failed"
    color = 0x2ECC71 if success else 0xE74C3C

    embed = {
        "title": f"Server {action.capitalize()} — {status_text}",
        "color": color,
        "description": message or f"Server {action} command sent.",
    }

    payload = {"username": "WindroseBot", "embeds": [embed]}
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)


def main():
    if len(sys.argv) < 2:
        print("Usage: python server_control.py <start|stop|restart>")
        sys.exit(1)

    action = sys.argv[1].lower()
    if action not in ("start", "stop", "restart"):
        print(f"Invalid action: {action}. Use start, stop, or restart.")
        sys.exit(1)

    print(f"Sending {action} command to Nitrado...")

    try:
        result = server_action(action)
        msg = result.get("message", f"Server {action} initiated.")
        print(f"Success: {msg}")
        notify_discord(action, True, msg)
    except requests.HTTPError as e:
        error_msg = f"API error: {e.response.status_code} — {e.response.text}"
        print(error_msg)
        notify_discord(action, False, error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
