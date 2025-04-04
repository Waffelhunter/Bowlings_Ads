#!/usr/bin/env python3
import socket
import threading
import time
import json
import signal
import sys
import os
import random
import shutil
from datetime import datetime
from PIL import Image, ImageTk
import tkinter as tk
import traceback  # For better error reporting
import queue

# Global variables
# Queue for GUI operations to be performed in the main thread
gui_queue = queue.Queue()
# Flag to indicate if GUI thread is running
gui_thread_running = False
# Tkinter root
root = None
# Image window references (to track all windows)
windows = []
# Main image window
image_window = None
image_label = None


def setup_gui_thread():
    """Set up the GUI thread that will handle all Tkinter operations"""
    global gui_thread_running, root

    def run_gui():
        global gui_thread_running, root
        try:
            # Create the main root window (invisible)
            root = tk.Tk()
            root.withdraw()

            # Set a flag that the GUI thread is running
            gui_thread_running = True
            print("GUI thread started, Tkinter main loop running")

            # Main loop to process GUI operations from the queue
            while True:
                try:
                    # Check if there are any operations in the queue
                    # (timeout to allow checking the root.quit flag)
                    operation = gui_queue.get(timeout=0.1)
                    if operation is None:
                        # None is our signal to stop
                        break
                    # Execute the operation in the GUI thread
                    operation()
                    gui_queue.task_done()
                except queue.Empty:
                    # No operations, just update the UI
                    root.update()
                except Exception as e:
                    print(f"Error in GUI thread: {e}")
                    traceback.print_exc()

                # Check if we should exit
                if not gui_thread_running:
                    break

            print("GUI thread shutting down")
            root.destroy()
        except Exception as e:
            print(f"GUI thread error: {e}")
            traceback.print_exc()
        finally:
            gui_thread_running = False

    # Create and start the GUI thread
    threading.Thread(target=run_gui, daemon=True).start()

    # Wait for the GUI thread to start
    retries = 0
    while not gui_thread_running and retries < 10:
        time.sleep(0.1)
        retries += 1


# Initialize the GUI thread at module import
setup_gui_thread()


def execute_in_gui_thread(func):
    """Execute a function in the GUI thread"""
    global gui_queue, gui_thread_running

    if not gui_thread_running:
        print("GUI thread is not running, trying to restart it")
        setup_gui_thread()

    # Put the function in the queue for the GUI thread to execute
    gui_queue.put(func)


class AdClient:
    def __init__(
        self, server_host="localhost", server_port=5000, client_id=None, idle_timeout=0
    ):
        self.server_host = server_host
        self.server_port = server_port
        self.client_id = client_id or f"client_{random.randint(1000, 9999)}"
        self.socket = None
        self.connected = False
        self.reconnect_interval = 5  # seconds

        # Ad data
        self.ads = []
        self.current_ad_index = 0
        self.ad_duration = 10  # seconds

        # Local timing system
        self.is_playing = False
        self.locally_paused = False  # Track if paused locally
        self.start_time = 0  # Local time when current ad sequence started
        self.pause_time = 0  # Elapsed time when paused
        self.last_time_check = 0  # For checking time drift
        self.time_drift_check_interval = 300  # Check time drift every 5 minutes
        self.needs_full_sync = False  # Flag to indicate we need a full sync (used when resuming from pause)

        # Time offset to sync with server (server_time - local_time)
        self.server_time_offset = 0

        # Idle state - only communicate with server when needed
        self.idle_mode = False
        self.idle_timeout = (
            idle_timeout  # Seconds before automatically exiting idle mode (0 = never)
        )
        self.idle_timer = None  # Timer for tracking idle timeout

        # Create local ads directory if it doesn't exist
        self.local_ads_dir = os.path.join(os.getcwd(), "ads_local")
        os.makedirs(self.local_ads_dir, exist_ok=True)

        # Setup signal handlers
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        # Create lock for thread safety
        self.lock = threading.Lock()

        # Create user input thread for local control
        self.input_thread = threading.Thread(target=self.handle_user_input, daemon=True)

    def connect(self):
        """Connect to the ad server"""
        while not self.connected and not self.idle_mode:
            try:
                print(
                    f"CLIENT [{self.client_id}]: Connecting to server at {self.server_host}:{self.server_port}..."
                )

                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.connect((self.server_host, self.server_port))
                self.connected = True

                print(f"CLIENT [{self.client_id}]: Connected to server successfully!")

                # Start message handler thread
                threading.Thread(target=self.message_handler, daemon=True).start()

                # Request initial sync
                self.request_sync()
                time.sleep(0.5)  # Small delay between requests

                # Request ad list
                self.request_ad_list()

                # Start time drift check
                threading.Thread(target=self.periodic_maintenance, daemon=True).start()

            except (socket.error, ConnectionRefusedError) as e:
                print(f"CLIENT [{self.client_id}]: Connection failed: {e}")
                print(
                    f"CLIENT [{self.client_id}]: Retrying in {self.reconnect_interval} seconds..."
                )
                time.sleep(self.reconnect_interval)
                self.connected = False

    def periodic_maintenance(self):
        """Periodically check for time drift and perform maintenance tasks"""
        while True:
            time.sleep(60)  # Check every minute
            if self.connected and not self.idle_mode and self.is_playing:
                # Only do periodic checks if we're playing and connected
                self.check_time_drift()

    def check_time_drift(self):
        """Check if our local timing has drifted too far from server time"""
        current_time = time.time()
        if (
            current_time - self.last_time_check > self.time_drift_check_interval
            and self.ads
        ):
            # Only check time drift occasionally
            self.last_time_check = current_time
            print(f"CLIENT [{self.client_id}]: Checking time drift with server...")

            # Mark that we need a full sync to correct any drift
            self.needs_full_sync = True
            self.request_sync()

    def message_handler(self):
        """Handle incoming messages from the server"""
        buffer = ""

        try:
            while self.connected and not self.idle_mode:
                data = self.socket.recv(4096)
                if not data:
                    raise ConnectionError("Server disconnected")

                buffer += data.decode("utf-8")

                # Process complete messages (assuming JSON messages delimited by newlines)
                while "\n" in buffer:
                    message, buffer = buffer.split("\n", 1)
                    self.process_message(message)

        except Exception as e:
            print(f"CLIENT [{self.client_id}]: Connection to server lost: {e}")
            self.connected = False

            # Attempt to reconnect only if not in idle mode
            if not self.idle_mode:
                threading.Thread(target=self.reconnect, daemon=True).start()
            else:
                print(
                    f"CLIENT [{self.client_id}]: In idle mode - will reconnect when needed"
                )

    def reconnect(self):
        """Attempt to reconnect to the server after a disconnection"""
        if self.idle_mode:
            print(
                f"CLIENT [{self.client_id}]: Not reconnecting - client is in idle mode"
            )
            return

        print(f"CLIENT [{self.client_id}]: Attempting to reconnect...")

        # Close socket if it exists
        self.disconnect_socket()

        time.sleep(self.reconnect_interval)
        self.connect()

    def disconnect_socket(self):
        """Disconnect the socket cleanly"""
        if self.socket:
            try:
                # Send a proper EOF by shutting down the socket before closing
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except:
                    # Socket might already be disconnected
                    pass

                # Close the socket
                self.socket.close()
                print(f"CLIENT [{self.client_id}]: Socket disconnected")
            except Exception as e:
                print(f"CLIENT [{self.client_id}]: Error closing socket: {e}")
            finally:
                self.socket = None
                self.connected = False

    def process_message(self, message_str):
        """Process a message from the server"""
        try:
            message = json.loads(message_str)
            command = message.get("command")

            if command == "sync":
                self.handle_sync(message)
            elif command == "ad_list":
                self.handle_ad_list(message)
            elif command == "file_transfer":
                self.handle_file_transfer(message)
            else:
                print(f"CLIENT [{self.client_id}]: Unknown command received: {command}")

        except json.JSONDecodeError:
            print(f"CLIENT [{self.client_id}]: Invalid message format: {message_str}")
        except Exception as e:
            print(f"CLIENT [{self.client_id}]: Error processing message: {e}")

    def handle_sync(self, sync_data):
        """Handle sync data from the server"""
        with self.lock:
            # Store if we're resuming from pause
            resuming_from_pause = self.locally_paused and not self.is_playing
            came_from_idle = self.idle_mode
            fresh_connection = (
                not hasattr(self, "initial_sync_done") or not self.initial_sync_done
            )

            # Always perform a full sync after reconnection
            if (
                resuming_from_pause
                or came_from_idle
                or fresh_connection
                or self.needs_full_sync
            ):
                print(
                    f"CLIENT [{self.client_id}]: Performing full timing synchronization"
                )
                self.force_sync_complete(sync_data)
                self.needs_full_sync = False

                # If resuming, update play state
                if resuming_from_pause:
                    self.locally_paused = False
                    self.is_playing = True
                    print(f"CLIENT [{self.client_id}]: Resuming from pause")

            # Calculate server-client time offset
            server_time = sync_data.get("server_time", time.time())
            self.server_time_offset = server_time - time.time()

            # Only update our play state if we're not locally paused
            server_is_playing = sync_data.get("is_playing", False)

            if not self.locally_paused:
                old_is_playing = self.is_playing
                self.is_playing = server_is_playing

            # Get ad duration from server
            self.ad_duration = sync_data.get("ad_duration", 10)

            # Print current status
            ad_info = ""
            if self.ads and 0 <= self.current_ad_index < len(self.ads):
                ad_info = f" | Current Ad: {self.ads[self.current_ad_index].get('content', 'Unknown')}"

            play_status = "Playing" if self.is_playing else "Paused"
            local_status = " (Locally paused)" if self.locally_paused else ""
            idle_status = " (Idle mode)" if self.idle_mode else ""

            # Calculate local timing info for display
            if self.is_playing and self.ads:
                elapsed_time = (time.time() - self.start_time) % (
                    self.ad_duration * len(self.ads)
                )
                current_ad_index = int(elapsed_time / self.ad_duration)
                remaining_time = self.ad_duration - (elapsed_time % self.ad_duration)

                timing_info = f" | Remaining: {remaining_time:.1f}s (local timing)"
            else:
                # If paused, show info from server
                remaining_time = sync_data.get("remaining_time", 0)
                timing_info = f" | Remaining: {remaining_time:.1f}s (server timing)"

            print(
                f"CLIENT [{self.client_id}]: Sync received: {play_status}{local_status}{idle_status}{ad_info}{timing_info}"
            )

            # If we're playing and don't have a display thread, start one
            if self.is_playing and not hasattr(self, "display_thread"):
                self.display_thread = threading.Thread(
                    target=self.display_loop, daemon=True
                )
                self.display_thread.start()

            # If we're coming from idle mode or it's initial sync and we're playing, force display the current ad
            if (came_from_idle or fresh_connection) and self.is_playing and self.ads:
                self.force_display_current_ad()

            self.initial_sync_done = True

            # If we're locally paused, enter idle mode after receiving sync data
            if self.locally_paused and not self.idle_mode:
                self.enter_idle_mode(already_locked=True)

    def force_sync_complete(self, sync_data):
        """Force complete sync with server data, including current ad and timing"""
        # Update current ad index first
        if self.ads:
            self.current_ad_index = sync_data.get("current_ad_index", 0)

        # Calculate exactly when the server calculated the sync data
        server_timestamp = sync_data.get("timestamp", time.time())
        server_elapsed_time = sync_data.get("elapsed_time", 0)

        if self.ads:
            # Reset timing completely using absolute time values
            # Account for network delay by estimating round trip time (server_time vs our time)
            network_delay = time.time() - sync_data.get("server_time", time.time())

            # Calculate our start time based on server elapsed time, adjusted for delay
            total_cycle_time = self.ad_duration * len(self.ads)

            # First calculate when server started playback
            server_start_time = server_timestamp - server_elapsed_time

            # Then adjust that to our local time reference
            self.start_time = server_start_time - network_delay

            print(
                f"CLIENT [{self.client_id}]: Force synchronized with server (network delay: {network_delay:.3f}s)"
            )

            # Log the exact sync details
            current_ad_index = sync_data.get("current_ad_index", 0)
            if 0 <= current_ad_index < len(self.ads):
                print(
                    f"CLIENT [{self.client_id}]: Now showing ad {current_ad_index+1}/{len(self.ads)}: {self.ads[current_ad_index].get('content', 'Unknown')}"
                )

    def force_display_current_ad(self):
        """Force immediate display of the current ad"""
        if self.ads and 0 <= self.current_ad_index < len(self.ads):
            ad = self.ads[self.current_ad_index]
            # Display the ad immediately
            threading.Thread(target=self.display_ad, args=(ad,), daemon=True).start()
            print(
                f"CLIENT [{self.client_id}]: Forced display of current ad: {ad.get('content', 'Unknown')}"
            )

    def sync_local_timing(self, sync_data):
        """Synchronize local timing with server data"""
        # Get server state
        server_elapsed_time = sync_data.get("elapsed_time", 0)
        server_start_time = sync_data.get("start_time")
        server_pause_time = sync_data.get("pause_time")

        if sync_data.get("is_playing", False):
            # Server is playing, calculate our local start time
            if self.ads:
                total_cycle_time = self.ad_duration * len(self.ads)
                self.start_time = time.time() - server_elapsed_time
                print(
                    f"CLIENT [{self.client_id}]: Synchronized local timing with server"
                )
        else:
            # Server is paused, store pause time
            self.pause_time = server_elapsed_time
            print(
                f"CLIENT [{self.client_id}]: Stored server pause time: {self.pause_time:.1f}s"
            )

        # Update current ad index
        if self.ads:
            self.current_ad_index = sync_data.get("current_ad_index", 0)

    def display_loop(self):
        """Main loop for displaying ads locally based on local timing"""
        last_ad_index = -1

        while True:
            time.sleep(0.1)  # Small sleep to prevent CPU hogging

            with self.lock:
                if not self.is_playing or not self.ads:
                    continue

                # Calculate the current ad index based on locally tracked elapsed time
                elapsed_time = (time.time() - self.start_time) % (
                    self.ad_duration * len(self.ads)
                )
                current_ad_index = int(elapsed_time / self.ad_duration)

                # If we've moved to a new ad, display it
                if current_ad_index != last_ad_index:
                    if 0 <= current_ad_index < len(self.ads):
                        ad = self.ads[current_ad_index]
                        self.current_ad_index = current_ad_index  # Update tracked index
                        self.display_ad(ad)
                        last_ad_index = current_ad_index

    def exit_idle_mode(self, already_locked=False):
        """Exit idle mode - reconnect to server for syncing"""
        if self.idle_mode:
            # Cancel any active idle timeout timer
            if self.idle_timer:
                self.idle_timer.cancel()
                self.idle_timer = None

            if already_locked:
                # The calling method already holds the lock
                print(f"CLIENT [{self.client_id}]: Exiting idle mode")
                self.idle_mode = False

                # Mark that we need to force sync when reconnected
                self.needs_full_sync = True

                # Reconnect to server
                if not self.connected:
                    threading.Thread(target=self.connect, daemon=True).start()
                    print(
                        f"CLIENT [{self.client_id}]: Reconnecting to server for sync..."
                    )
            else:
                # Need to acquire the lock
                with self.lock:
                    print(f"CLIENT [{self.client_id}]: Exiting idle mode")
                    self.idle_mode = False

                    # Mark that we need to force sync when reconnected
                    self.needs_full_sync = True

                    # Reconnect to server
                    if not self.connected:
                        threading.Thread(target=self.connect, daemon=True).start()
                        print(
                            f"CLIENT [{self.client_id}]: Reconnecting to server for sync..."
                        )

            # No longer close the window when exiting idle mode, we want to keep it open

    def handle_ad_list(self, ad_list_data):
        """Handle ad list data from the server"""
        with self.lock:
            self.ads = ad_list_data.get("ads", [])
            print(
                f"CLIENT [{self.client_id}]: Received ad list with {len(self.ads)} ads"
            )

            # Request any ad files we don't have locally
            for ad in self.ads:
                ad_path = ad.get("path", "")
                if ad_path and not os.path.exists(
                    os.path.join(self.local_ads_dir, ad_path)
                ):
                    self.request_ad_file(ad_path)

    def handle_file_transfer(self, file_data):
        """Handle file transfer from server"""
        filename = file_data.get("filename", "")
        content_base64 = file_data.get("content", "")

        if filename and content_base64:
            import base64

            try:
                # Decode the base64 content
                file_content = base64.b64decode(content_base64)

                # Save the file to local ads directory
                local_path = os.path.join(self.local_ads_dir, filename)
                with open(local_path, "wb") as f:
                    f.write(file_content)

                print(
                    f"CLIENT [{self.client_id}]: Received and saved ad file: {filename}"
                )
            except Exception as e:
                print(
                    f"CLIENT [{self.client_id}]: Error saving ad file {filename}: {e}"
                )

    def request_sync(self):
        """Request sync data from the server"""
        if self.connected and not self.idle_mode:
            try:
                request = {"command": "get_sync", "client_id": self.client_id}
                self.socket.send((json.dumps(request) + "\n").encode("utf-8"))
                print(f"CLIENT [{self.client_id}]: Requested sync data from server")
            except Exception as e:
                print(f"CLIENT [{self.client_id}]: Error requesting sync: {e}")
                self.connected = False

                # Only reconnect if not in idle mode
                if not self.idle_mode:
                    threading.Thread(target=self.reconnect, daemon=True).start()

    def request_ad_list(self):
        """Request ad list from the server"""
        if self.connected and not self.idle_mode:
            try:
                request = {"command": "get_ads", "client_id": self.client_id}
                self.socket.send((json.dumps(request) + "\n").encode("utf-8"))
                print(f"CLIENT [{self.client_id}]: Requested ad list from server")
            except Exception as e:
                print(f"CLIENT [{self.client_id}]: Error requesting ad list: {e}")
                self.connected = False

                # Only reconnect if not in idle mode
                if not self.idle_mode:
                    threading.Thread(target=self.reconnect, daemon=True).start()

    def request_ad_file(self, filename):
        """Request ad file from the server"""
        if self.connected and not self.idle_mode:
            try:
                request = {
                    "command": "get_file",
                    "filename": filename,
                    "client_id": self.client_id,
                }
                self.socket.send((json.dumps(request) + "\n").encode("utf-8"))
                print(f"CLIENT [{self.client_id}]: Requested ad file: {filename}")
            except Exception as e:
                print(f"CLIENT [{self.client_id}]: Error requesting ad file: {e}")
                self.connected = False

                # Only reconnect if not in idle mode
                if not self.idle_mode:
                    threading.Thread(target=self.reconnect, daemon=True).start()

    def display_ad(self, ad):
        """Display an ad (in this case, just print it and show image if available)"""
        # In a real implementation, this would show the ad on a display
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\nCLIENT [{self.client_id}] [{timestamp}]: DISPLAYING AD")
        print(f"  Content: {ad.get('content', 'Unknown')}")

        ad_path = ad.get("path", "")
        local_path = os.path.join(self.local_ads_dir, ad_path) if ad_path else ""

        if local_path and os.path.exists(local_path):
            print(f"  Image: {local_path}")
            # Display the image in a graphical window if it's an image file
            if local_path.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
                self.show_image_window(local_path, ad.get("content", "Ad"))
            else:
                print(f"  Not a supported image format")
        else:
            print(f"  Path: {ad_path} (file not available locally)")

        print("-" * 50)

    def show_image_window(self, image_path, title):
        """Show the image in a tkinter window"""
        global image_window, image_label, windows

        # Load the image first (outside GUI thread)
        try:
            print(f"CLIENT [{self.client_id}]: Loading image: {image_path}")
            img = Image.open(image_path)
            print(
                f"CLIENT [{self.client_id}]: Image loaded: {img.format}, {img.size}, {img.mode}"
            )

            # Resize if the image is too large
            max_width, max_height = 800, 600
            width, height = img.size
            if width > max_width or height > max_height:
                ratio = min(max_width / width, max_height / height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                print(f"CLIENT [{self.client_id}]: Resized image to {new_size}")

            # Now create/update the window in the GUI thread
            def create_or_update_window():
                global image_window, image_label, windows

                # Create a new window if one doesn't exist
                if image_window is None or len(windows) == 0:
                    print(
                        f"CLIENT [{self.client_id}]: Creating new window for ad display"
                    )
                    # Create a new toplevel window
                    image_window = tk.Toplevel(root)
                    windows.append(image_window)  # Keep track of all windows

                    image_window.title(f"Ad Display - {self.client_id} - {title}")
                    image_window.protocol("WM_DELETE_WINDOW", self.close_image_window)
                    image_window.minsize(320, 240)

                    # Create label for image
                    image_label = tk.Label(image_window)
                    image_label.pack(fill=tk.BOTH, expand=True)

                    # Bind event handlers to the window and image label
                    self.bind_window_events(image_window, image_label)
                else:
                    # Reuse existing window
                    print(f"CLIENT [{self.client_id}]: Updating existing window")
                    image_window.title(f"Ad Display - {self.client_id} - {title}")

                    # Ensure event handlers are bound
                    self.bind_window_events(image_window, image_label)

                # Convert image for display
                tk_img = ImageTk.PhotoImage(img)

                # Update the image
                image_label.configure(image=tk_img)
                image_label.image = tk_img  # Keep a reference

                # Make sure window is visible and raised to the top
                image_window.update()
                image_window.deiconify()
                image_window.lift()

                print(f"CLIENT [{self.client_id}]: Window updated and visible")

            # Execute window creation/update in GUI thread
            execute_in_gui_thread(create_or_update_window)

        except Exception as e:
            print(f"CLIENT [{self.client_id}]: Error displaying image: {e}")
            traceback.print_exc()

    def bind_window_events(self, window, label):
        """Bind key and mouse events to window and label to enter idle mode on interaction"""
        try:
            # Bind key presses to both window and label
            window.bind("<Key>", self.handle_window_event)
            label.bind("<Key>", self.handle_window_event)

            # Bind mouse clicks to both window and label
            window.bind("<Button-1>", self.handle_window_event)
            window.bind("<Button-2>", self.handle_window_event)
            window.bind("<Button-3>", self.handle_window_event)
            label.bind("<Button-1>", self.handle_window_event)
            label.bind("<Button-2>", self.handle_window_event)
            label.bind("<Button-3>", self.handle_window_event)

            # Uncomment to enable mouse movement detection
            # window.bind("<Motion>", self.handle_window_event)
            # label.bind("<Motion>", self.handle_window_event)

            print(
                f"CLIENT [{self.client_id}]: Event handlers bound to window - any key or click will trigger idle mode"
            )
        except Exception as e:
            print(f"CLIENT [{self.client_id}]: Error binding window events: {e}")
            traceback.print_exc()

    def handle_window_event(self, event):
        """Handle window interaction events by entering idle mode"""
        if not self.idle_mode and self.is_playing:
            event_type = (
                "key press"
                if event.type == tk.EventType.KeyPress
                else "mouse interaction"
            )
            print(
                f"\nCLIENT [{self.client_id}]: {event_type} detected in window - entering idle mode"
            )

            # Schedule the action in a thread to not block the event loop
            def pause_thread():
                self.toggle_play_pause()

            threading.Thread(target=pause_thread, daemon=True).start()

    def close_image_window(self):
        """Close the main image window if it exists"""
        # Schedule window closing in GUI thread
        execute_in_gui_thread(self.close_all_windows_internal)
        print(f"CLIENT [{self.client_id}]: Window close requested")

    def close_all_windows_internal(self):
        """Close all managed windows (to be called in GUI thread)"""
        global image_window, image_label, windows

        try:
            print(f"CLIENT [{self.client_id}]: Closing all windows...")
            # Close all tracked windows
            for win in list(windows):
                try:
                    win.destroy()
                    windows.remove(win)
                    print(f"CLIENT [{self.client_id}]: Destroyed window")
                except Exception as e:
                    print(f"CLIENT [{self.client_id}]: Error destroying window: {e}")

            # Reset references
            image_window = None
            image_label = None
            windows = []
            print(
                f"CLIENT [{self.client_id}]: All windows closed and references cleared"
            )
        except Exception as e:
            print(f"CLIENT [{self.client_id}]: Error in close_all_windows: {e}")
            traceback.print_exc()

    def close_image_window_force(self):
        """Forcibly close all windows - test function"""
        print(f"CLIENT [{self.client_id}]: Force closing all windows")
        execute_in_gui_thread(self.close_all_windows_internal)

        # Also send a close command to root for good measure
        def force_refresh():
            global root
            if root:
                root.update()

        execute_in_gui_thread(force_refresh)

    def enter_idle_mode(self, already_locked=False):
        """Enter idle mode - disconnect from server to minimize communication"""
        if not self.idle_mode:
            if already_locked:
                # The calling method already holds the lock
                print(f"CLIENT [{self.client_id}]: Entering idle mode")
                self.idle_mode = True

                # Force disconnect from server
                self.disconnect_socket()

                print(
                    f"CLIENT [{self.client_id}]: Idle mode active - disconnected from server"
                )

                # Set up idle timeout if configured
                self.setup_idle_timeout()
            else:
                # Need to acquire the lock
                with self.lock:
                    print(f"CLIENT [{self.client_id}]: Entering idle mode")
                    self.idle_mode = True

                    # Force disconnect from server
                    self.disconnect_socket()

                    print(
                        f"CLIENT [{self.client_id}]: Idle mode active - disconnected from server"
                    )

                    # Set up idle timeout if configured
                    self.setup_idle_timeout()

            # Close the image window in a thread-safe way
            self.close_image_window_force()
            print(f"CLIENT [{self.client_id}]: Closed image window")

    def setup_idle_timeout(self):
        """Set up a timer to automatically exit idle mode after the configured timeout"""
        # Cancel any existing timer
        if self.idle_timer:
            self.idle_timer.cancel()
            self.idle_timer = None

        # Only set up a timer if timeout is greater than 0
        if self.idle_timeout > 0:
            print(
                f"CLIENT [{self.client_id}]: Idle timeout set to {self.idle_timeout} seconds"
            )
            # Create a new timer
            self.idle_timer = threading.Timer(
                self.idle_timeout, self.idle_timeout_callback
            )
            self.idle_timer.daemon = True
            self.idle_timer.start()

    def idle_timeout_callback(self):
        """Called when the idle timeout is reached"""
        print(
            f"CLIENT [{self.client_id}]: Idle timeout reached after {self.idle_timeout} seconds - auto-resuming"
        )
        # Exit idle mode and resume playback
        self.toggle_play_pause()

    def handle_user_input(self):
        """Handle user input for local control"""
        print(f"CLIENT [{self.client_id}]: Local Control Available:")
        print("  p - Toggle Play/Pause locally")
        print("  s - Force sync with server")
        print("  i - Show idle/connection status")
        print("  k - Test close window (debug)")
        print("  w - Show window info (debug)")
        print("  q - Quit client")
        print("  ? - Show this help")

        while True:
            cmd = input().strip().lower()

            if cmd == "p":
                self.toggle_play_pause()
            elif cmd == "s":
                print(f"CLIENT [{self.client_id}]: Forcing sync with server...")

                # Exit idle mode if needed for sync
                if self.idle_mode:
                    self.exit_idle_mode()

                    # Wait a bit for connection to establish
                    sync_tries = 0
                    while not self.connected and sync_tries < 10:
                        sync_tries += 1
                        time.sleep(0.5)

                if self.connected:
                    self.request_sync()
                    time.sleep(0.5)  # Small delay between requests
                    self.request_ad_list()
                else:
                    print(
                        f"CLIENT [{self.client_id}]: Not connected - try again in a few seconds"
                    )
            elif cmd == "k":
                # Test window closing functionality
                print(f"CLIENT [{self.client_id}]: Testing window close functionality")
                self.close_image_window_force()
            elif cmd == "w":
                # Print window info
                global image_window, windows
                print(f"CLIENT [{self.client_id}]: Window info:")
                print(f"  Main window exists: {image_window is not None}")
                print(f"  Number of tracked windows: {len(windows)}")
                for i, win in enumerate(windows):
                    try:
                        print(f"  Window {i}: {win} - exists: {win.winfo_exists()}")
                    except:
                        print(f"  Window {i}: {win} - error checking")
            elif cmd == "i":
                status = "Connected" if self.connected else "Disconnected"
                idle = "In idle mode" if self.idle_mode else "Active mode"
                play = (
                    "Playing"
                    if self.is_playing
                    else "Paused" + (" (locally)" if self.locally_paused else "")
                )
                print(f"CLIENT [{self.client_id}]: Status: {status} | {idle} | {play}")

                # Show current ad and timing based on local calculations
                ad_name, current_index, elapsed, remaining = (
                    self.calculate_current_status()
                )
                if ad_name != "No ads available" and ad_name != "Unknown":
                    print(
                        f"  Current Ad: {ad_name} | Index: {current_index} | Remaining: {remaining:.1f}s"
                    )
                    print(
                        f"  Local timing: elapsed={elapsed:.1f}s, start_time={self.start_time}, pause_time={self.pause_time}"
                    )
                else:
                    print(f"  {ad_name}")

            elif cmd == "q":
                self.shutdown()
                break
            elif cmd == "?":
                print(f"CLIENT [{self.client_id}]: Local Control Commands:")
                print("  p - Toggle Play/Pause locally")
                print("  s - Force sync with server")
                print("  i - Show idle/connection status")
                print("  k - Test close window (debug)")
                print("  w - Show window info (debug)")
                print("  q - Quit client")
                print("  ? - Show this help")
            else:
                print(
                    f"CLIENT [{self.client_id}]: Unknown command '{cmd}'. Type ? for help"
                )

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        print(f"CLIENT [{self.client_id}]: Shutdown signal received")
        self.close_image_window()  # Close the image window on shutdown
        self.shutdown()

    def shutdown(self):
        """Clean shutdown of the client"""
        global gui_thread_running, gui_queue

        print(f"CLIENT [{self.client_id}]: Shutting down...")

        # Close all windows
        self.close_image_window_force()

        # Shut down network
        self.idle_mode = False
        self.connected = False
        self.disconnect_socket()

        # Shut down GUI thread
        gui_thread_running = False
        gui_queue.put(None)  # Signal GUI thread to exit

        # Exit program
        sys.exit(0)

    def start(self):
        """Start the client"""
        print(f"CLIENT [{self.client_id}]: Starting...")
        self.connect()

        # Start user input thread for local control
        self.input_thread.start()

        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.shutdown()

    def toggle_play_pause(self):
        """Toggle between play and pause states locally"""
        with self.lock:
            if self.is_playing:
                # Pausing locally
                self.pause_time = (time.time() - self.start_time) % (
                    self.ad_duration * len(self.ads) if self.ads else self.ad_duration
                )
                self.is_playing = False
                self.locally_paused = True

                print(f"CLIENT [{self.client_id}]: Ad display LOCALLY PAUSED")

                # Enter idle mode when paused, already holding the lock
                self.enter_idle_mode(already_locked=True)
            else:
                # Resuming - need to sync with server first
                self.locally_paused = False

                print(f"CLIENT [{self.client_id}]: RESUMING from local pause")

                # Exit idle mode and reconnect for sync, already holding the lock
                self.exit_idle_mode(already_locked=True)

                # We'll reconnect and sync in exit_idle_mode

    def calculate_current_status(self):
        """Calculate current ad status based on local timing"""
        if not self.ads:
            return "No ads available", None, None, None

        if self.is_playing:
            # Calculate based on local timing
            elapsed_time = (time.time() - self.start_time) % (
                self.ad_duration * len(self.ads)
            )
            current_ad_index = int(elapsed_time / self.ad_duration)
            remaining_time = self.ad_duration - (elapsed_time % self.ad_duration)

            if 0 <= current_ad_index < len(self.ads):
                ad = self.ads[current_ad_index]
                return (
                    ad.get("content", "Unknown"),
                    current_ad_index,
                    elapsed_time,
                    remaining_time,
                )
        else:
            # Paused state - use stored pause time
            if self.ads:
                elapsed_time = self.pause_time
                current_ad_index = int(elapsed_time / self.ad_duration)
                remaining_time = self.ad_duration - (elapsed_time % self.ad_duration)

                if 0 <= current_ad_index < len(self.ads):
                    ad = self.ads[current_ad_index]
                    return (
                        ad.get("content", "Unknown"),
                        current_ad_index,
                        elapsed_time,
                        remaining_time,
                    )

        return "Unknown", 0, 0, 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ad Display Client")
    parser.add_argument("--server", default="localhost", help="Server hostname or IP")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    parser.add_argument("--id", help="Client ID (random if not specified)")
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=0,
        help="Seconds to stay in idle mode before auto-resuming (0 = never)",
    )

    args = parser.parse_args()

    client = AdClient(
        server_host=args.server,
        server_port=args.port,
        client_id=args.id,
        idle_timeout=args.idle_timeout,
    )
    client.start()
