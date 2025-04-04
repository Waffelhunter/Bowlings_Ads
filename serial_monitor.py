#!/usr/bin/env python3
import serial
import time
import sys
import os
import binascii

# ANSI colors for better visibility
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


def monitor_serial_port(port_name, baud_rate=9600, timeout=0.1):
    """
    Monitor a serial port and display all incoming data in both hex and ASCII.

    Args:
        port_name: Serial port device name (e.g., /dev/ttyUSB0)
        baud_rate: Baud rate to use for the connection
        timeout: Read timeout in seconds
    """
    print(f"{CYAN}Serial Port Monitor{RESET}")
    print(f"Monitoring port: {GREEN}{port_name}{RESET}")
    print(f"Baud rate: {baud_rate}, Timeout: {timeout}s")
    print(f"Press {YELLOW}Ctrl+C{RESET} to exit")
    print("-" * 60)

    try:
        # Try opening the serial port
        ser = serial.Serial(port_name, baudrate=baud_rate, timeout=timeout)
        print(f"Successfully opened port {GREEN}{port_name}{RESET}")

        # Clear any initial data
        ser.flushInput()

        # Counter for received data chunks
        counter = 0

        try:
            while True:
                # Read data if available
                if ser.in_waiting > 0:
                    # Read all available data
                    data = ser.read(ser.in_waiting)

                    if data:
                        counter += 1
                        timestamp = time.strftime("%H:%M:%S", time.localtime())

                        # Convert data to different representations
                        hex_data = binascii.hexlify(data).decode()

                        # Try to show ASCII representation where possible
                        ascii_repr = ""
                        for byte in data:
                            if 32 <= byte <= 126:  # Printable ASCII
                                ascii_repr += chr(byte)
                            else:
                                ascii_repr += "."

                        # Display the received data
                        print(
                            f"\n{YELLOW}[{timestamp}] Received data #{counter}:{RESET}"
                        )
                        print(f"{CYAN}HEX:{RESET} {hex_data}")
                        print(f"{CYAN}ASCII:{RESET} {ascii_repr}")
                        print(
                            f"{CYAN}Bytes:{RESET} {' '.join([f'{b:02x}' for b in data])}"
                        )
                        print(f"{CYAN}Length:{RESET} {len(data)} bytes")
                        print("-" * 60)

                # Small delay to prevent 100% CPU usage
                time.sleep(0.05)

        except KeyboardInterrupt:
            print(f"\n{YELLOW}Monitoring stopped by user{RESET}")

        finally:
            # Always close the serial port
            ser.close()
            print(f"Closed port {port_name}")

    except serial.SerialException as e:
        print(f"{YELLOW}Error opening serial port {port_name}: {e}{RESET}")


def find_serial_ports():
    """Find potential serial ports on the system."""
    potential_ports = []

    # Common paths for serial ports on Linux
    if sys.platform.startswith("linux"):
        # Look for ttyUSB devices (USB to serial adapters like PL2303)
        for i in range(10):
            port = f"/dev/ttyUSB{i}"
            if os.path.exists(port):
                potential_ports.append(port)

        # Look for ttyS devices (hardware serial ports)
        for i in range(10):
            port = f"/dev/ttyS{i}"
            if os.path.exists(port):
                potential_ports.append(port)

    # macOS and Windows would need different patterns, but we're focusing on Linux

    return potential_ports


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serial Port Monitor")
    parser.add_argument("--port", help="Serial port to monitor (e.g., /dev/ttyUSB0)")
    parser.add_argument(
        "--baud", type=int, default=9600, help="Baud rate (default: 9600)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.1,
        help="Read timeout in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--scan", action="store_true", help="Scan and list available serial ports"
    )

    args = parser.parse_args()

    if args.scan:
        ports = find_serial_ports()
        if ports:
            print(f"{CYAN}Found serial ports:{RESET}")
            for port in ports:
                print(f"  {GREEN}{port}{RESET}")
        else:
            print(f"{YELLOW}No serial ports found.{RESET}")
        sys.exit(0)

    if not args.port:
        # If no port specified, try to find one
        ports = find_serial_ports()
        if not ports:
            print(
                f"{YELLOW}No serial ports found. Please specify a port with --port.{RESET}"
            )
            sys.exit(1)

        # Use the first found port
        port_to_monitor = ports[0]
        print(f"{YELLOW}No port specified, using {port_to_monitor}{RESET}")
    else:
        port_to_monitor = args.port

    monitor_serial_port(port_to_monitor, args.baud, args.timeout)
