#!/usr/bin/env python3
import socket
import threading
import time
import json
import signal
import sys
import os
import base64
from datetime import datetime
from pathlib import Path
import shutil
from PIL import Image, ImageDraw


class AdServer:
    def __init__(self, host="0.0.0.0", port=5000):
        self.host = host
        self.port = port
        self.clients = []  # List of client sockets
        self.client_info = {}  # Dictionary to store client info by socket
        self.ads = []
        self.current_ad_index = 0
        self.ad_duration = 10  # seconds per ad
        self.start_time = time.time()
        self.is_playing = True
        self.pause_time = 0
        self.lock = threading.Lock()

        # Setup main ads directory (will be watched for changes)
        self.ads_dir = os.path.join(os.getcwd(), "ads")
        os.makedirs(self.ads_dir, exist_ok=True)

        # Setup ad file watcher
        self.last_check_time = time.time()
        self.file_check_interval = 5  # seconds

        # Load ads from file
        self.load_ads()

        # Setup server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Register signal handlers
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        # Start directory watcher thread
        threading.Thread(target=self.watch_ads_directory, daemon=True).start()

    def load_ads(self):
        """Load the ad list from the file or create a default one"""
        try:
            with open(os.path.join(self.ads_dir, "ad_list.json"), "r") as f:
                self.ads = json.load(f)
            print(f"SERVER: Loaded {len(self.ads)} ads")
        except FileNotFoundError:
            # Scan the ads directory for images and create a default list
            self.scan_ads_directory()

            if not self.ads:
                # Create a default ad list if no images found
                self.ads = [
                    {"id": 1, "content": "Sample Ad 1", "path": "ad1.jpg"},
                    {"id": 2, "content": "Sample Ad 2", "path": "ad2.jpg"},
                    {"id": 3, "content": "Sample Ad 3", "path": "ad3.jpg"},
                ]

            self.save_ads()
            print(f"SERVER: Created ad list with {len(self.ads)} ads")

    def scan_ads_directory(self):
        """Scan the ads directory for image files and update the ad list"""
        image_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]

        # List all files in the ads directory
        files = [
            f
            for f in os.listdir(self.ads_dir)
            if os.path.isfile(os.path.join(self.ads_dir, f))
            and any(f.lower().endswith(ext) for ext in image_extensions)
            and f != "ad_list.json"  # Exclude the ad_list.json file itself
        ]

        with self.lock:
            # Get current paths in our ad list
            current_paths = {ad["path"]: ad["id"] for ad in self.ads}

            # Recreate the ad list from scratch based on files in the directory
            new_ads = []
            next_id = 1

            # Keep track of existing ads to preserve their IDs and content
            for file in files:
                if file in current_paths:
                    # Keep existing ad entries but ensure they're updated
                    existing_ad = next(ad for ad in self.ads if ad["path"] == file)
                    new_ads.append(existing_ad)
                else:
                    # Create a new entry for this file
                    # Extract base name without extension to use as content
                    base_name = os.path.splitext(file)[0]
                    content = base_name.replace("_", " ").title()

                    # Find an available ID
                    while any(ad["id"] == next_id for ad in new_ads):
                        next_id += 1

                    new_ads.append({"id": next_id, "content": content, "path": file})
                    next_id += 1
                    print(f"SERVER: Added new ad from file: {file}")

            # Check if there were any changes
            if len(new_ads) != len(self.ads) or set(
                ad["path"] for ad in new_ads
            ) != set(ad["path"] for ad in self.ads):
                # Update the ads list
                self.ads = new_ads
                print(f"SERVER: Updated ad list, now contains {len(self.ads)} ads")

                # Sort ads by ID for consistency
                self.ads.sort(key=lambda ad: ad["id"])

                # Save the updated list
                self.save_ads()
                return True  # Indicate changes were made

            return False  # No changes were made

    def watch_ads_directory(self):
        """Watch the ads directory for changes and update the ad list accordingly"""
        while True:
            time.sleep(self.file_check_interval)

            current_time = time.time()
            if current_time - self.last_check_time >= self.file_check_interval:
                # Check for changes by scanning the directory
                print("SERVER: Checking for changes in ads directory...")
                changes_made = self.scan_ads_directory()

                # If changes were detected (scan_ads_directory returns True if changes were made)
                if changes_made:
                    print(
                        "SERVER: Changes detected in ads directory, notifying clients..."
                    )

                    # Notify all clients about the updated ad list
                    for client in self.clients:
                        try:
                            self.send_ad_list(client)
                        except:
                            pass

                self.last_check_time = current_time

    def save_ads(self):
        """Save the ad list to the file"""
        with open(os.path.join(self.ads_dir, "ad_list.json"), "w") as f:
            json.dump(self.ads, f, indent=2)

    def start(self):
        """Start the server"""
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            print(f"SERVER: Started on {self.host}:{self.port}")
            print(f"SERVER: Monitoring ads directory: {self.ads_dir}")

            # Start a background thread to perform periodic maintenance (cleanup stale clients)
            threading.Thread(target=self.maintenance_thread, daemon=True).start()

            # Accept clients
            self.accept_clients()
        except Exception as e:
            print(f"SERVER ERROR: {e}")
            self.shutdown()

    def accept_clients(self):
        """Accept incoming client connections"""
        while True:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"SERVER: Client connected from {address}")

                # Create a thread to handle this client
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address),
                    daemon=True,
                )
                client_thread.start()
            except Exception as e:
                print(f"SERVER ERROR: Error accepting client: {e}")
                break

    def handle_client(self, client_socket, address):
        """Handle communication with a connected client"""
        client_id = "unknown"
        try:
            # Register client
            with self.lock:
                # Set socket timeout to help detect disconnected clients
                client_socket.settimeout(15)  # 15 seconds timeout

                self.clients.append(client_socket)
                # Initialize client info with address
                self.client_info[client_socket] = {
                    "address": address,
                    "client_id": None,
                    "last_active": time.time(),
                }

            # Send initial sync data
            self.send_sync_data(client_socket)

            # Send ad list
            self.send_ad_list(client_socket)

            # Handle client messages
            buffer = ""
            while True:
                try:
                    data = client_socket.recv(1024)
                    if not data:
                        # Client disconnected properly
                        break

                    # Update last active time
                    if client_socket in self.client_info:
                        self.client_info[client_socket]["last_active"] = time.time()

                    # Append data to buffer
                    buffer += data.decode("utf-8")

                    # Process all complete messages in buffer
                    while "\n" in buffer:
                        message, buffer = buffer.split("\n", 1)
                        if message:  # Skip empty messages
                            self.process_client_message(message, client_socket)
                            client_id = self.client_info.get(client_socket, {}).get(
                                "client_id", "unknown"
                            )

                except socket.timeout:
                    # Check if client is still connected
                    try:
                        # Try sending an empty message to check connection
                        client_socket.send(b"")
                    except:
                        # Socket error, client probably disconnected
                        break
                    continue
                except ConnectionResetError:
                    # Client disconnected abruptly
                    break
                except ConnectionAbortedError:
                    # Connection aborted
                    break

        except Exception as e:
            client_id = self.client_info.get(client_socket, {}).get(
                "client_id", "unknown"
            )
            print(f"SERVER ERROR: Error handling client {client_id} ({address}): {e}")
        finally:
            # Unregister client
            self.cleanup_client(client_socket, address, client_id)

    def cleanup_client(self, client_socket, address, client_id):
        """Clean up client resources when disconnected"""
        with self.lock:
            if client_socket in self.clients:
                self.clients.remove(client_socket)

            # Get client info before removing
            if client_socket in self.client_info:
                client_id = self.client_info[client_socket].get("client_id", "unknown")
                del self.client_info[client_socket]

        try:
            client_socket.close()
        except:
            pass

        print(f"SERVER: Client {client_id} ({address}) disconnected")

    def process_client_message(self, message, client_socket):
        """Process messages from clients"""
        # Update client info for logging
        client_info = self.client_info.get(
            client_socket, {"address": "unknown", "client_id": "unknown"}
        )
        client_id = client_info.get("client_id", "unknown")
        address = client_info.get("address", "unknown")

        # Update last active time
        if client_socket in self.client_info:
            self.client_info[client_socket]["last_active"] = time.time()

        try:
            cmd = json.loads(message)
            command = cmd.get("command")

            # Extract client_id from message if available
            msg_client_id = cmd.get("client_id")
            if msg_client_id and client_socket in self.client_info:
                self.client_info[client_socket]["client_id"] = msg_client_id
                client_id = msg_client_id  # Update for current log messages

            # Process commands
            if command == "get_sync":
                print(
                    f"SERVER: Received 'get_sync' request from client {client_id} ({address})"
                )
                self.send_sync_data(client_socket)
            elif command == "get_ads":
                print(
                    f"SERVER: Received 'get_ads' request from client {client_id} ({address})"
                )
                self.send_ad_list(client_socket)
            elif command == "get_file":
                filename = cmd.get("filename")
                if filename:
                    print(
                        f"SERVER: Received 'get_file' request for '{filename}' from client {client_id} ({address})"
                    )
                    self.send_ad_file(client_socket, filename)
            else:
                print(
                    f"SERVER WARNING: Unknown command '{command}' received from client {client_id} ({address})"
                )
        except json.JSONDecodeError:
            print(
                f"SERVER ERROR: Invalid message format from client {client_id} ({address}): {message}"
            )
        except Exception as e:
            print(
                f"SERVER ERROR: Error processing client message: {e} - Message: {message} from {client_id} ({address})"
            )

    def send_ad_file(self, client_socket, filename):
        """Send an ad file to a client"""
        file_path = os.path.join(self.ads_dir, filename)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            try:
                # Read the file content
                with open(file_path, "rb") as f:
                    file_content = f.read()

                # Encode file content to base64
                content_base64 = base64.b64encode(file_content).decode("utf-8")

                # Send the file data
                file_data = {
                    "command": "file_transfer",
                    "filename": filename,
                    "content": content_base64,
                }

                client_socket.send((json.dumps(file_data) + "\n").encode("utf-8"))

                # Get client info for logging
                client_info = self.client_info.get(
                    client_socket, {"address": "unknown", "client_id": "unknown"}
                )
                client_id = client_info.get("client_id", "unknown")

                print(f"SERVER: Sent file '{filename}' to client {client_id}")

            except Exception as e:
                print(f"SERVER ERROR: Error sending file {filename}: {e}")
        else:
            print(f"SERVER ERROR: File not found: {filename}")

    def send_sync_data(self, client_socket):
        """Send synchronization data to a client"""
        with self.lock:
            # Calculate elapsed time for ad display
            elapsed_time = 0
            if self.is_playing and self.ads:
                elapsed_time = (time.time() - self.start_time) % (
                    self.ad_duration * len(self.ads)
                )
            elif not self.is_playing and self.ads:
                elapsed_time = self.pause_time % (self.ad_duration * len(self.ads))

            # Calculate current ad index and remaining time
            current_ad_index = int(elapsed_time / self.ad_duration) if self.ads else 0
            remaining_time = (
                self.ad_duration - (elapsed_time % self.ad_duration) if self.ads else 0
            )

            sync_data = {
                "command": "sync",
                "timestamp": time.time(),
                "server_time": time.time(),
                "is_playing": self.is_playing,
                "current_ad_index": current_ad_index,
                "remaining_time": remaining_time,
                "ad_duration": self.ad_duration,
                "elapsed_time": elapsed_time,
                "start_time": self.start_time if self.is_playing else None,
                "pause_time": self.pause_time if not self.is_playing else None,
            }

            try:
                client_socket.send((json.dumps(sync_data) + "\n").encode("utf-8"))

                # Get client info for logging
                client_info = self.client_info.get(
                    client_socket, {"address": "unknown", "client_id": "unknown"}
                )
                client_id = client_info.get("client_id", "unknown")

                print(
                    f"SERVER: Sent sync data to client {client_id} (current_ad: {current_ad_index}, remaining: {remaining_time:.1f}s)"
                )

            except Exception as e:
                print(f"SERVER ERROR: Error sending sync data: {e}")

    def send_ad_list(self, client_socket):
        """Send the ad list to a client"""
        with self.lock:
            ad_list_data = {"command": "ad_list", "ads": self.ads}

            try:
                client_socket.send((json.dumps(ad_list_data) + "\n").encode("utf-8"))

                # Get client info for logging
                client_info = self.client_info.get(
                    client_socket, {"address": "unknown", "client_id": "unknown"}
                )
                client_id = client_info.get("client_id", "unknown")

                print(
                    f"SERVER: Sent ad list with {len(self.ads)} ads to client {client_id}"
                )

            except Exception as e:
                print(f"SERVER ERROR: Error sending ad list: {e}")

    def notify_clients_state_change(self):
        """Notify all connected clients of a state change (play/pause)"""
        with self.lock:
            clients_copy = self.clients.copy()

        for client_socket in clients_copy:
            try:
                self.send_sync_data(client_socket)
            except Exception as e:
                # Client may have disconnected
                try:
                    address = self.client_info.get(client_socket, {}).get(
                        "address", "unknown"
                    )
                    client_id = self.client_info.get(client_socket, {}).get(
                        "client_id", "unknown"
                    )
                    print(f"SERVER: Failed to notify client {client_id}: {e}")
                    # Remove disconnected client
                    self.cleanup_client(client_socket, address, client_id)
                except:
                    pass

    def toggle_play_pause(self):
        """Toggle between play and pause states"""
        with self.lock:
            if self.is_playing and self.ads:
                # Pausing
                self.pause_time = (time.time() - self.start_time) % (
                    self.ad_duration * len(self.ads)
                )
                self.is_playing = False
                print(
                    f"SERVER: Ad display paused at {datetime.now().strftime('%H:%M:%S')}"
                )
            else:
                # Resuming
                if self.ads:
                    self.start_time = time.time() - self.pause_time
                else:
                    self.start_time = time.time()
                self.is_playing = True
                print(
                    f"SERVER: Ad display resumed at {datetime.now().strftime('%H:%M:%S')}"
                )

        # Notify clients of the state change
        self.notify_clients_state_change()

    def add_ad(self, ad_data):
        """Add a new ad to the list"""
        with self.lock:
            new_id = max([ad["id"] for ad in self.ads], default=0) + 1
            ad_data["id"] = new_id

            # If a path is specified, create a placeholder file if needed
            if "path" in ad_data and not os.path.exists(
                os.path.join(self.ads_dir, ad_data["path"])
            ):
                # Instead of creating a text file, create a simple image using PIL
                try:
                    # Create a placeholder path with .jpg extension
                    if (
                        not ad_data["path"]
                        .lower()
                        .endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp"))
                    ):
                        ad_data["path"] = f"ad_{new_id}.jpg"

                    placeholder_path = os.path.join(self.ads_dir, ad_data["path"])

                    # Create a simple colored image with text
                    img = Image.new("RGB", (640, 480), color=(240, 240, 240))
                    d = ImageDraw.Draw(img)
                    d.text(
                        (320, 240),
                        ad_data.get("content", f"Ad {new_id}"),
                        fill=(0, 0, 0),
                    )
                    img.save(placeholder_path)

                    print(f"SERVER: Created placeholder image: {placeholder_path}")
                except ImportError:
                    # Fallback if PIL is not available
                    placeholder_path = os.path.join(self.ads_dir, ad_data["path"])
                    with open(placeholder_path, "w") as f:
                        f.write(f"Ad {new_id}: {ad_data.get('content', 'No content')}")
                    print(f"SERVER: Created placeholder file: {placeholder_path}")

            self.ads.append(ad_data)
            self.save_ads()

        # Notify clients of the updated ad list
        for client in self.clients:
            try:
                self.send_ad_list(client)
            except:
                pass

    def remove_ad(self, ad_id):
        """Remove an ad from the list"""
        with self.lock:
            # Find the ad to be removed
            ad_to_remove = None
            for ad in self.ads:
                if ad["id"] == ad_id:
                    ad_to_remove = ad
                    break

            if ad_to_remove:
                # Remove the ad file if it exists and only used by this ad
                path = ad_to_remove.get("path")
                if path:
                    file_path = os.path.join(self.ads_dir, path)

                    # Check if other ads use this same file
                    other_ads_with_same_file = [
                        a
                        for a in self.ads
                        if a["id"] != ad_id and a.get("path") == path
                    ]

                    if not other_ads_with_same_file and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"SERVER: Removed ad file: {path}")
                        except:
                            print(f"SERVER ERROR: Failed to remove ad file: {path}")

            # Update the ads list
            self.ads = [ad for ad in self.ads if ad["id"] != ad_id]
            self.save_ads()

        # Notify clients of the updated ad list
        for client in self.clients:
            try:
                self.send_ad_list(client)
            except:
                pass

    def open_ads_directory(self):
        """Open the ads directory in the file manager"""
        try:
            import subprocess

            # Different commands for different operating systems
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", self.ads_dir])
            elif sys.platform == "darwin":  # macOS
                subprocess.Popen(["open", self.ads_dir])
            elif sys.platform == "win32":  # Windows
                subprocess.Popen(["explorer", self.ads_dir])

            print(f"SERVER: Opened ads directory: {self.ads_dir}")
        except Exception as e:
            print(f"SERVER ERROR: Failed to open ads directory: {e}")

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        print("SERVER: Shutdown signal received")
        self.shutdown()

    def shutdown(self):
        """Clean shutdown of the server"""
        print("SERVER: Shutting down...")

        # Save state if needed
        self.save_ads()

        # Close all client connections
        with self.lock:
            for client in self.clients:
                try:
                    client.close()
                except:
                    pass
            self.clients = []

        # Close server socket
        try:
            self.server_socket.close()
        except:
            pass

        sys.exit(0)

    def maintenance_thread(self):
        """Periodically check for stale client connections"""
        while True:
            time.sleep(30)  # Run every 30 seconds
            self.check_stale_clients()

    def check_stale_clients(self):
        """Check for and remove stale client connections"""
        current_time = time.time()
        stale_clients = []

        with self.lock:
            # Find stale clients (inactive for more than 60 seconds)
            for client_socket, info in list(self.client_info.items()):
                last_active = info.get("last_active", 0)
                if current_time - last_active > 60:  # 60 seconds threshold
                    stale_clients.append((client_socket, info))

        # Clean up each stale client
        for client_socket, info in stale_clients:
            try:
                # Try to see if the socket is still connected
                try:
                    client_socket.send(b"")
                except:
                    # Socket is no longer valid, clean it up
                    address = info.get("address", "unknown")
                    client_id = info.get("client_id", "unknown")
                    print(
                        f"SERVER: Removing stale client {client_id} ({address}) - no response"
                    )
                    self.cleanup_client(client_socket, address, client_id)
            except:
                pass


if __name__ == "__main__":
    server = AdServer()

    # Command line interface thread
    def cli():
        print("Ad Server CLI")
        print("Commands:")
        print("  play/pause - Toggle between playing and pausing ad display")
        print("  list       - Show the current ad list")
        print("  add [content] - Add a new ad with the specified content")
        print("  remove [id]   - Remove an ad by ID")
        print("  dir        - Open the ads directory in file manager")
        print("  scan       - Scan the ads directory for new files")
        print("  duration [seconds] - Set the duration for each ad")
        print("  clients    - Show connected clients")
        print("  help       - Show this help")
        print("  exit       - Shutdown the server")

        while True:
            cmd = input("> ").strip().lower()

            if cmd == "play" or cmd == "pause":
                server.toggle_play_pause()
            elif cmd == "list":
                print(f"Current ads ({len(server.ads)}):")
                for ad in server.ads:
                    print(
                        f"  ID: {ad['id']}, Content: {ad['content']}, File: {ad['path']}"
                    )
            elif cmd.startswith("add "):
                content = cmd[4:].strip()
                if content:
                    timestamp = int(time.time())
                    filename = f"ad_{timestamp}.txt"
                    server.add_ad({"content": content, "path": filename})
                    print(f"Added new ad: {content} (File: {filename})")
            elif cmd.startswith("remove "):
                try:
                    ad_id = int(cmd[7:].strip())
                    server.remove_ad(ad_id)
                    print(f"Removed ad ID: {ad_id}")
                except ValueError:
                    print("Invalid ad ID")
            elif cmd == "dir":
                server.open_ads_directory()
            elif cmd == "scan":
                print("Scanning ads directory for changes...")
                server.scan_ads_directory()
                server.save_ads()
                print(f"Updated ad list, now contains {len(server.ads)} ads")
            elif cmd.startswith("duration "):
                try:
                    duration = int(cmd[9:].strip())
                    if duration > 0:
                        server.ad_duration = duration
                        print(f"Ad duration set to {duration} seconds")
                    else:
                        print("Duration must be greater than 0")
                except ValueError:
                    print("Invalid duration value")
            elif cmd == "clients":
                print(f"Connected clients ({len(server.clients)}):")
                for client_socket, info in server.client_info.items():
                    client_id = info.get("client_id", "unknown")
                    address = info.get("address", "unknown")
                    last_active = info.get("last_active", 0)
                    time_since = time.time() - last_active
                    print(
                        f"  Client: {client_id}, Address: {address}, Last active: {time_since:.1f}s ago"
                    )
            elif cmd == "help":
                print("Commands:")
                print("  play/pause - Toggle between playing and pausing ad display")
                print("  list       - Show the current ad list")
                print("  add [content] - Add a new ad with the specified content")
                print("  remove [id]   - Remove an ad by ID")
                print("  dir        - Open the ads directory in file manager")
                print("  scan       - Scan the ads directory for new files")
                print("  duration [seconds] - Set the duration for each ad")
                print("  clients    - Show connected clients")
                print("  help       - Show this help")
                print("  exit       - Shutdown the server")
            elif cmd == "exit":
                server.shutdown()
                break
            else:
                print("Unknown command. Type 'help' for available commands.")

    # Start CLI thread
    threading.Thread(target=cli, daemon=True).start()

    # Start server
    try:
        server.start()
    except KeyboardInterrupt:
        server.shutdown()
