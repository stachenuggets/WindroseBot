# WindroseBot

A Discord bot for monitoring and managing a Windrose Nitrado gameserver. Hosted for free on Oracle Cloud.

## Features

- `/status` — Live server status with player slots, IP, and online/offline state
- `/start` `/stop` `/restart` — Remote server control (admin only)
- `/ip` — Quick copy-paste server address
- `/uptime` — How long the server has been running
- `/backup create` — Create a server backup (admin only)
- `/backup list` — View available backups (admin only)
- `/backup restore` — Restore from a backup (admin only)
- `/logs` — Pull recent server logs (admin only)
- `/players` — Check player count
- `/save` — Save the server (creates a backup)
- **Auto-monitoring** — Updates a status embed every 5 minutes and alerts on status changes
- **Restart warnings** — Posts a 5-minute warning before the daily scheduled restart

## Requirements

- Python 3.8+
- A [Discord bot application](https://discord.com/developers/applications)
- A [Nitrado](https://server.nitrado.net) gameserver with an API token
- An Oracle Cloud free tier VM (or any Linux server)

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to **Bot** and copy the token
4. Enable **Presence Intent** and **Server Members Intent** under Privileged Gateway Intents
5. Go to **OAuth2 > URL Generator**
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Manage Messages`
6. Open the generated URL to invite the bot to your server

### 2. Get Your Nitrado API Token

1. Log in to [Nitrado](https://server.nitrado.net)
2. Go to your account settings and generate an API token
3. Note your service ID from your server's URL (e.g., `https://webinterface.nitrado.net/19044524/...` — the ID is `19044524`)

### 3. Get Your Discord Channel ID

1. Enable Developer Mode in Discord (Settings > Advanced > Developer Mode)
2. Right-click the channel where you want status updates
3. Click **Copy Channel ID**

### 4. Deploy to Oracle Cloud

Create a free VM on [Oracle Cloud](https://cloud.oracle.com):
- Shape: `VM.Standard.E2.1.Micro` (Always Free)
- OS: Ubuntu 22.04+
- Assign a public IP to the VNIC

SSH into the VM and run:

```bash
git clone https://github.com/YOUR_USER/WindroseBot.git
cd WindroseBot
chmod +x setup.sh
./setup.sh
```

Edit the environment file with your tokens:

```bash
sudo nano /opt/windrosebot/.env
```

```
DISCORD_TOKEN=your_discord_bot_token
NITRADO_TOKEN=your_nitrado_api_token
NITRADO_SERVICE_ID=your_service_id
STATUS_CHANNEL_ID=your_channel_id
ALERT_ROLE_ID=optional_role_id_for_pings
```

Start the bot:

```bash
sudo systemctl start windrosebot
```

### 5. Verify

Check the bot is running:

```bash
sudo journalctl -u windrosebot -f
```

You should see `WindroseBot online as ...` in the logs and the bot should appear online in your Discord server.

## Managing the Bot

```bash
# Check status
sudo systemctl status windrosebot

# Restart
sudo systemctl restart windrosebot

# Stop
sudo systemctl stop windrosebot

# View logs
sudo journalctl -u windrosebot -f

# Update the bot
cd ~/WindroseBot
git pull
sudo cp bot.py /opt/windrosebot/bot.py
sudo systemctl restart windrosebot
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `NITRADO_TOKEN` | Yes | Nitrado API token |
| `NITRADO_SERVICE_ID` | Yes | Nitrado service ID |
| `STATUS_CHANNEL_ID` | Yes | Discord channel ID for status updates |
| `ALERT_ROLE_ID` | No | Discord role ID to ping on status changes |

The daily restart warning time is set in `bot.py` (`RESTART_HOUR_UTC` and `RESTART_MINUTE_UTC`). Default is 16:09 UTC (9:09 AM UTC-7).
