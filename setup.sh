#!/bin/bash

# --- CONFIG ---
SERVICE_NAME="lichaser-bridge"
PYTHON_SCRIPT="control_led_strip.py"
CUR_DIR=$(pwd)
VENV_DIR="$CUR_DIR/venv"
USER_NAME=$(whoami)

echo "--- Starting Setup for $SERVICE_NAME ---"

# 1. Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# 2. Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements.txt
else
    echo "Error: requirements.txt not found!"
    exit 1
fi

# 3. Create the Systemd Service File
echo "Generating systemd service file..."
sudo bash -c "cat <<EOT > /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Lichaser Bluetooth LED Bridge
After=network.target bluetooth.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$CUR_DIR
ExecStart=$VENV_DIR/bin/python3 $CUR_DIR/$PYTHON_SCRIPT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOT"

# 4. Enable and Start the service
echo "Reloading systemd and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo "--- Setup Complete ---"
echo "Check status with: sudo systemctl status $SERVICE_NAME"
echo "View logs with: journalctl -u $SERVICE_NAME -f"