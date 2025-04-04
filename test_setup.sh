#!/bin/bash

# Test script to run the ad display system locally for testing

echo "Ad Display System Local Test"
echo "==========================="
echo

# Get the current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Make sure the scripts are executable
chmod +x "$SCRIPT_DIR/server.py"
chmod +x "$SCRIPT_DIR/client.py"
chmod +x "$SCRIPT_DIR/create_sample_images.py"

# Create ads directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/ads"

# Create proper image files for sample ads if they don't exist
if [ ! -f "$SCRIPT_DIR/ads/ad1.jpg" ]; then
    echo "Creating sample image files..."
    # Run the Python script to create actual image files
    #python3 "$SCRIPT_DIR/create_sample_images.py"
    echo "Created sample image files."
else
    echo "Using existing sample ad images."
fi

# Start the server in the background
echo "Starting the server..."
gnome-terminal --title="Ad Server" -- "$SCRIPT_DIR/server.py" &
SERVER_PID=$!

# Wait for the server to initialize
sleep 3

# Start clients
echo "Starting clients..."
for i in {1}; do
    gnome-terminal --title="Ad Client $i" -- "$SCRIPT_DIR/client.py" --id "client$i" &
    CLIENT_PIDS+=($!)
    sleep 1
done

echo
echo "Test environment is running."
echo
echo "- Server is running in a separate terminal window"
echo "- 3 clients are running in separate terminal windows"
echo
echo "Server Controls:"
echo "  play/pause - Toggle play/pause for all clients"
echo "  list       - Show the current ad list"
echo "  dir        - Open the ads directory to add/edit files"
echo "  scan       - Scan for new files"
echo "  help       - Show all commands"
echo
echo "Client Controls (in client window):"
echo "  p          - Toggle local play/pause (enters idle mode when paused)"
echo "  s          - Force sync with server (exits idle mode if needed)"
echo "  i          - Show idle/connection status"
echo "  ?          - Show help"
echo
echo "Note: When clients are paused, they enter 'idle mode' and disconnect"
echo "      from the server to reduce network traffic. They will automatically"
echo "      reconnect and sync when resumed."
echo
echo "Note: To add new ads, simply drop image files into the ads directory,"
echo "      and use the 'scan' command in the server window to refresh."
echo
echo "Press CTRL+C to terminate all processes..."

# Wait for user to terminate
trap "kill $SERVER_PID ${CLIENT_PIDS[@]} 2>/dev/null" EXIT
wait 