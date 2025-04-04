# Server PC Configuration Guide

This guide explains how to set up the Server PC to both run the ad server and display ads.

## Overview

The server PC will:

1. Run the ad server to manage and distribute ads
2. Run a client instance to display ads locally
3. Start both services on boot

## Setup

### Step 1: Install the Server

1. From the project directory, run the server install script:

   ```bash
   sudo ./install.sh
   ```

2. When prompted, choose option `1` for Server installation.

3. Verify the server is running:
   ```bash
   sudo systemctl status ad-server.service
   ```

### Step 2: Install a Local Client

1. Create a local client service:

   ```bash
   sudo nano /etc/systemd/system/ad-client-local.service
   ```

2. Paste the following content:

   ```
   [Unit]
   Description=Ad Display Client (Local)
   After=network.target ad-server.service
   Requires=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/home/fabian/Documents/Bowling_stuff/CAS2
   ExecStart=/usr/bin/python3 /home/fabian/Documents/Bowling_stuff/CAS2/client.py --server localhost --id server-display
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Save and close the file.

4. Enable and start the local client:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable ad-client-local.service
   sudo systemctl start ad-client-local.service
   ```

5. Verify the client is running:
   ```bash
   sudo systemctl status ad-client-local.service
   ```

## Managing Ads

### Adding New Ads

1. The easiest way to add ads is to place image files in the `ads` directory.

2. You can open the ads directory directly from the server CLI:

   ```
   > dir
   ```

3. Copy your image files into this directory. The server will automatically detect and add them.

### Using Server CLI

Start the server manually (if not already running) to access the CLI:

```bash
sudo systemctl stop ad-server.service  # Stop the service if running
cd /home/fabian/Documents/Bowling_stuff/CAS2
./server.py  # Run manually to access CLI
```

CLI commands:

- `play/pause` - Toggle play/pause
- `list` - Show all ads
- `add [content]` - Add a new ad
- `remove [id]` - Remove an ad
- `dir` - Open ads directory
- `scan` - Scan for new files
- `duration [seconds]` - Set ad duration
- `help` - Show all commands

## Local Client Controls

The local client has the following commands available when run manually:

- `p` - Toggle Play/Pause locally (enters idle mode when paused)
- `s` - Force sync with server (exits idle mode if needed)
- `i` - Show idle/connection status
- `q` - Quit client
- `?` - Show help

### About Idle Mode

When the client is paused locally, it enters an "idle mode" where it disconnects from the server to reduce network traffic. When you resume playback, it automatically reconnects to sync with the server.

## Troubleshooting

### If the Server Won't Start

Check the logs:

```bash
journalctl -u ad-server.service -n 50
```

Common issues:

- Path issues: Make sure the paths in the service file match your actual installation directory
- Permission issues: Make sure the user running the service has permission to the directory

### If the Client Won't Display

Check the logs:

```bash
journalctl -u ad-client-local.service -n 50
```

Common issues:

- Connection issues: Make sure the server is running and accessible
- Path issues: Make sure the paths in the service file match your actual installation directory
- Idle mode issues: If the client is stuck in idle mode, try restarting it

## Updating the Ad List

The server automatically watches the ads directory for new files, but you can also:

1. Manually scan for changes:

   ```
   > scan
   ```

2. View the current ad list:
   ```
   > list
   ```

## Using Local Control for the Display

To control the local display client directly:

1. Stop the service:

   ```bash
   sudo systemctl stop ad-client-local.service
   ```

2. Run the client manually:

   ```bash
   cd /home/fabian/Documents/Bowling_stuff/CAS2
   ./client.py --server localhost --id server-display
   ```

3. Use the client controls:
   - `p` - Toggle local play/pause
   - `s` - Force sync with server
   - `i` - Show idle/connection status
   - `?` - Show help
