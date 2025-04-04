# Changelog

## Version 1.1.0 - Client Idle State and Message Format Fix

### Client Improvements

- Added idle state functionality
  - Clients now enter idle mode when locally paused
  - Disconnects from server to minimize network traffic when paused
  - Automatically reconnects and syncs when resumed
  - Only communicates with the server when needed (startup and after local pause)
- Added the `i` command to check idle/connection status
- Improved client UI feedback with idle state indicators
- Added a delay between initial sync requests to prevent message interleaving

### Server Improvements

- Fixed message parsing to properly handle client messages
  - Added message buffer handling to correctly process incoming client messages
  - Properly splits messages on newline characters
  - Fixed "Invalid message format" errors when receiving multiple commands
- Added error handling for empty messages
- Added additional error reporting for client message processing
- Fixed potential division by zero when ad list is empty

### Documentation

- Updated README with idle state information
- Added communication protocol documentation
- Updated SERVER_PC_GUIDE with idle mode information
- Improved troubleshooting information for idle mode issues
- Updated test script with idle mode information

## Version 1.0.0 - Initial Release

- Server-client architecture for synchronized ad display
- Automatic reconnection if connection is lost
- Central ad management with file distribution
- Individual client pause/resume capability
- Hot-folder monitoring for adding ads by copying files
- Systemd services for automatic startup on boot
- Graceful handling of network disconnections
- Server PC can act as display client
