# Synchronized Ad Display System

This system allows for synchronized display of advertisements across multiple client machines. The server manages the ad list and synchronization, while clients display ads in perfect sync, with the ability to pause locally and enter an idle state to reduce network traffic.

## Features

- Server-client architecture for synchronized ad display
- Automatic reconnection if connection is lost
- Central ad management with file distribution
- Individual client pause/resume capability while maintaining synchronization
- Idle mode for clients when paused to minimize network communication
- Hot-folder monitoring for adding new ads by simply copying files to the ads directory
- Systemd services for automatic startup on boot
- Graceful handling of network disconnections
- Server can also be used as a display client

## Requirements

- Python 3.6+
- Linux with systemd for service installation

## Installation

### Server Setup

1. Clone this repository to `/home/fabian/Documents/Bowling_stuff/CAS2` or update the paths in the service files if using a different location.

2. Install the server systemd service:

   ```bash
   sudo cp ad-server.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable ad-server.service
   sudo systemctl start ad-server.service
   ```

3. Verify the server is running:

   ```bash
   sudo systemctl status ad-server.service
   ```

4. **Ads Management**:
   - Place ad images in the `ads` directory in the workspace
   - The server will automatically detect new images and add them to the ad list
   - You can also use the server's CLI to manage ads

### Client Setup

1. Clone this repository to each client machine.

2. Update the `ad-client.service` file to use the correct server IP address:

   ```bash
   # Edit the file and replace SERVER_IP with your server's IP address
   sudo nano ad-client.service
   ```

3. Install the client systemd service:

   ```bash
   sudo cp ad-client.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable ad-client.service
   sudo systemctl start ad-client.service
   ```

4. To install all 7 clients at once, you can use the included script:

   ```bash
   sudo ./install_clients.sh
   ```

5. Verify the client is running:
   ```bash
   sudo systemctl status ad-client.service
   ```

## Usage

### Server Commands

The server has a command-line interface with the following commands:

- `play/pause` - Toggle between playing and pausing ad display
- `list` - Show the current ad list
- `add [content]` - Add a new ad with the specified content
- `remove [id]` - Remove an ad by ID
- `dir` - Open the ads directory in file manager
- `scan` - Manually scan the ads directory for new files
- `duration [seconds]` - Set the duration for each ad
- `help` - Show available commands
- `exit` - Shutdown the server

### Client Controls

Each client has its own local control interface:

- `p` - Toggle Play/Pause locally (when resumed, client will sync with server)
- `s` - Force sync with server (update ad list and timing)
- `i` - Show idle/connection status
- `q` - Quit client
- `?` - Show help

### Client Idle State

When a client is locally paused, it enters an "idle state" where it:

1. Disconnects from the server to reduce network traffic
2. Maintains its local state (ad list, timing, etc.)
3. Only reconnects when needed (when resuming playback or manually forcing a sync)

This significantly reduces network traffic and server load when clients are paused.

### Managing Ads

1. The simplest way to add ads is to copy image files directly to the `ads` directory. The server will automatically detect new files and add them to the ad list.

2. You can also use the server's CLI to add text-based ads or manage the ad list.

3. The ads are stored in `ads/ad_list.json`, but this file is managed automatically by the server.

## Troubleshooting

- If clients cannot connect to the server, check firewall settings to ensure port 5000 is open.
- Check logs with `journalctl -u ad-server.service` or `journalctl -u ad-client.service`.
- If the service fails to start, you may need to adjust permissions or paths in the service files.
- If ad images don't appear on clients, check that the files are being properly transferred.
- If a client is stuck in idle mode, try manually forcing a sync with the `s` command.

## Architecture

- **Server**:

  - Manages the ad list and controls the display sequence
  - Monitors the ads directory for changes
  - Handles client connections and synchronization
  - Distributes ad files to clients

- **Clients**:
  - Connect to the server and download the ad list and files
  - Display ads in sync with the server's timer
  - Can pause/resume playback locally
  - Enter idle mode when paused to minimize network traffic
  - Automatically sync with server when resuming or connecting

## Synchronization Process

1. On startup, clients connect to the server.
2. Once connected, clients request the current ad list and timing information.
3. Clients also request any ad files they don't have locally.
4. The server responds with the current ad index, remaining time, and play state.
5. Clients adjust their local timers to match the server's position.
6. If a client pauses locally, it will enter idle mode and disconnect from the server.
7. When a client resumes after a local pause, it exits idle mode, reconnects and syncs with the server.

## Communication Protocol

The server and clients communicate using JSON messages, each terminated with a newline character:

```
{"command": "command_name", "param1": "value1", ...}\n
```

Available commands:

- `get_sync` - Request synchronization data
- `get_ads` - Request the ad list
- `get_file` - Request a specific ad file
- `sync` - Synchronization data response
- `ad_list` - Ad list response
- `file_transfer` - File transfer response

## Customization

- To change the ad duration, use the `duration` command on the server.
- For advanced display options, customize the `display_ad` method in `client.py`.
- To change the server port, modify both server and client files and update the service files accordingly.
- Adjust the directory watching interval by modifying the `file_check_interval` parameter in `server.py`.
- Adjust reconnection settings by modifying the `reconnect_interval` parameter in `client.py`.

## License

This software is provided as-is with no warranty. Use at your own risk.
