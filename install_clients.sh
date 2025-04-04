#!/bin/bash

# Multi-client installation script
# This script will create 7 client services with different IDs

echo "Installing 7 ad display clients"
echo "=============================="
echo

# Make sure we're running as root
if [ "$EUID" -ne 0 ]
  then echo "Please run as root (sudo)"
  exit 1
fi

# Get the current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Ask for server IP
read -p "Enter the server IP address: " server_ip

# Make client script executable
chmod +x "$SCRIPT_DIR/client.py"

# Create and install 7 client services
for i in {1..7}
do
    echo "Setting up client $i..."
    
    # Create a new service file for this client
    client_service="ad-client-$i.service"
    
    cat > "/etc/systemd/system/$client_service" << EOF
[Unit]
Description=Ad Display Client $i
After=network.target ad-server.service
Requires=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/client.py --server $server_ip --id client$i
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    # Enable and start the service
    systemctl daemon-reload
    systemctl enable "$client_service"
    systemctl start "$client_service"
    
    echo "Client $i installed and started."
    echo
done

echo "All 7 clients installed and started."
echo
echo "To check the status of a specific client:"
echo "  systemctl status ad-client-<number>.service"
echo
echo "To see logs from a specific client:"
echo "  journalctl -u ad-client-<number>.service -f"
echo
echo "Installation complete." 