#!/bin/bash
# Run this on your Oracle Cloud VM to set up WindroseBot

set -e

echo "=== WindroseBot Setup ==="

# Install Python and pip (works on Oracle Linux and Ubuntu)
if command -v dnf &> /dev/null; then
    sudo dnf install -y python3 python3-pip git
else
    sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
fi

# Create app directory
sudo mkdir -p /opt/windrosebot
sudo cp bot.py requirements.txt /opt/windrosebot/
cd /opt/windrosebot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
if [ ! -f .env ]; then
    echo "Creating .env — you'll need to fill in your tokens."
    cat > .env <<'ENVEOF'
DISCORD_TOKEN=
NITRADO_TOKEN=
NITRADO_SERVICE_ID=
STATUS_CHANNEL_ID=
ALERT_ROLE_ID=
ENVEOF
    echo "Edit /opt/windrosebot/.env and add your tokens."
fi

# Install systemd service
sudo tee /etc/systemd/system/windrosebot.service > /dev/null <<'SVCEOF'
[Unit]
Description=WindroseBot Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/windrosebot
ExecStart=/opt/windrosebot/venv/bin/python bot.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/windrosebot/.env

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable windrosebot

echo ""
echo "=== Setup complete! ==="
echo "1. Edit /opt/windrosebot/.env with your tokens"
echo "2. Start the bot: sudo systemctl start windrosebot"
echo "3. Check logs: sudo journalctl -u windrosebot -f"
