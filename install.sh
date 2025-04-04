#!/bin/bash

# Synchronized Ad Display System Installer

echo "Synchronized Ad Display System Installer"
echo "========================================"
echo

# Make sure we're running as root
if [ "$EUID" -ne 0 ]
  then echo "Please run as root (sudo)"
  exit 1
fi

# Get the current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Detect if this is a server or client installation
echo "Is this a server or client installation?"
echo "1. Server"
echo "2. Client"
read -p "Enter choice [1/2]: " installtype

if [ "$installtype" == "1" ]; then
    echo "Installing server..."
    
    # Copy the service file
    cp "$SCRIPT_DIR/ad-server.service" /etc/systemd/system/
    
    # Make scripts executable
    chmod +x "$SCRIPT_DIR/server.py"
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start the service
    systemctl enable ad-server.service
    systemctl start ad-server.service
    
    echo "Server installation complete!"
    echo
    echo "The server should now be running. Check with:"
    echo "  systemctl status ad-server.service"
    echo
    echo "You can manage ads using the server CLI."
    
elif [ "$installtype" == "2" ]; then
    echo "Installing client..."
    
    # Ask for server IP
    read -p "Enter the server IP address: " server_ip
    
    # Update the service file with the correct server IP
    sed "s/SERVER_IP/$server_ip/g" "$SCRIPT_DIR/ad-client.service" > /etc/systemd/system/ad-client.service
    
    # Make scripts executable
    chmod +x "$SCRIPT_DIR/client.py"
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start the service
    systemctl enable ad-client.service
    systemctl start ad-client.service
    
    echo "Client installation complete!"
    echo
    echo "The client should now be running and connecting to $server_ip."
    echo "Check with:"
    echo "  systemctl status ad-client.service"
    
else
    echo "Invalid choice. Exiting."
    exit 1
fi

echo
echo "To see logs from the service:"
echo "  journalctl -u ad-server.service -f"
echo "  or"
echo "  journalctl -u ad-client.service -f"
echo
echo "Installation finished." 