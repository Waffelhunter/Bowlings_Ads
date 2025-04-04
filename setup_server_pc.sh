#!/bin/bash

# Setup script for Server PC (both server and display client)

echo "Server PC Setup (Server + Display Client)"
echo "========================================"
echo

# Make sure we're running as root
if [ "$EUID" -ne 0 ]
  then echo "Please run as root (sudo)"
  exit 1
fi

# Get the current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "This script will set up this PC to run both the ad server and a display client."
echo

# Step 1: Install the server
echo "Step 1: Installing the ad server..."
# Copy the service file
cp "$SCRIPT_DIR/ad-server.service" /etc/systemd/system/

# Make scripts executable
chmod +x "$SCRIPT_DIR/server.py"
chmod +x "$SCRIPT_DIR/client.py"

# Create ads directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/ads"

# Reload systemd
systemctl daemon-reload

# Enable the server service
systemctl enable ad-server.service

# Step 2: Create a local client service
echo
echo "Step 2: Creating the local display client service..."

# Create the service file
cat > "/etc/systemd/system/ad-client-local.service" << EOF
[Unit]
Description=Ad Display Client (Local)
After=network.target ad-server.service
Requires=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/client.py --server localhost --id server-display
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable the client service
systemctl enable ad-client-local.service

echo
echo "Server PC setup complete!"
echo
echo "Services will start on next boot, or you can start them now with:"
echo "  sudo systemctl start ad-server.service"
echo "  sudo systemctl start ad-client-local.service"
echo
echo "To manage ads, either:"
echo "  1. Copy image files directly to: $SCRIPT_DIR/ads/"
echo "  2. Run the server with CLI access: $SCRIPT_DIR/server.py"
echo
echo "For more information, see SERVER_PC_GUIDE.md" 