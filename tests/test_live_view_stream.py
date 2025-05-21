#!/usr/bin/env python3
"""
Canon Camera Live View Streaming Script - Direct Connection Version

This script connects to a Canon camera using the EDSDK with a direct connection approach 
(similar to connection_test.py), starts live view, streams frames, and allows you to 
exit cleanly by pressing Ctrl+C in the terminal.

Usage:
    PYTHONPATH=$PYTHONPATH:. python tests/test_live_view_stream.py

Press Ctrl+C to stop streaming and exit.
"""

import os
import time
import subprocess
import platform
import threading
import queue
import signal
import sys

# Import EDSDK constants and custom classes
from src.camera_constants import (
    EDS_ERR_OK, kEdsPropID_Evf_Mode, kEdsPropID_Evf_OutputDevice,
    kEdsEvfOutputDevice_PC, CameraStatus
)
from src.canon_camera_connection import (
    CanonCameraConnection, CMD_CONNECT, CMD_DISCONNECT,
    CMD_START_LIVE_VIEW, CMD_STOP_LIVE_VIEW, CMD_CAPTURE_FRAME,
    MSG_CONNECTION_STATUS, MSG_CAMERA_INFO, MSG_LIVE_FRAME, MSG_ERROR, MSG_LOG
)
from src.canon_camera_controller import CanonCameraController

# Global variables for clean exit
connection = None
controller = None
command_queue = None
data_queue = None
running = True
live_view_active = False


def check_system_usb_devices():
    """Check if any Canon cameras are visible at the OS level using system_profiler."""
    if platform.system() != "Darwin":
        print("USB device check via system_profiler is macOS specific. Skipping.")
        return True # Assume OK on other platforms for this check

    try:
        result = subprocess.run(
            ['system_profiler', 'SPUSBDataType'],
            capture_output=True,
            text=True,
            check=False
        )
        output = result.stdout
        print("\nUSB Device Check (macOS):")
        if 'Canon' in output:
            print("✓ Canon device found in system USB devices.")
            # Extract Canon device details for more information
            lines = output.split('\n')
            for i, line in enumerate(lines):
                if 'Canon' in line:
                    # Print a few lines around the Canon device for context
                    start = max(0, i-2)
                    end = min(len(lines), i+5)
                    for j in range(start, end):
                        if j < len(lines): print(f"  {lines[j]}")
                    break
            return True
        else:
            print("✗ No Canon devices found in system USB devices.")
            print("Please make sure your camera is:")
            print("  1. Powered on")
            print("  2. Connected via USB")
            print("  3. Set to PTP/PC connection mode")
            print("  4. Not in sleep mode")
            return False
    except Exception as e:
        print(f"Error checking USB devices: {e}")
        return False


def setup_camera_connection():
    """Setup the Canon camera connection and controller."""
    global connection, controller, command_queue, data_queue
    
    print(f"\nRunning on {platform.system()} {platform.release()}")
    print(f"Python version: {platform.python_version()}")

    # Only proceed if we can see a Canon camera at the OS level
    if not check_system_usb_devices():
        print("Warning: No Canon camera detected at OS level.")
        print("Attempting to connect anyway...")

    print("\nSetting up CanonCameraConnection...")
    connection = CanonCameraConnection()
    command_queue = queue.Queue()
    data_queue = queue.Queue()
    connection.start_worker(command_queue, data_queue)

    print("Sending connect command to camera...")
    command_queue.put({"action": CMD_CONNECT})

    # Wait for connection confirmation
    connected = False
    try:
        for _ in range(20): # Timeout after ~10 seconds
            message = data_queue.get(timeout=0.5)
            print(f"Received: {message}")
            if message["type"] == MSG_CONNECTION_STATUS and message["payload"]["status"] == "connected":
                connected = True
                print("✓ Camera connected successfully.")
                break
            if message["type"] == MSG_CAMERA_INFO: # Often comes after connection
                connected = True # Assume connection if we get info
                print(f"✓ Camera info received: {message['payload']}")
                try:
                    msg_extra = data_queue.get(timeout=0.1)
                    if msg_extra["type"] == MSG_CONNECTION_STATUS and msg_extra["payload"]["status"] == "connected":
                         print("✓ Camera connected successfully (confirmed).")
                except queue.Empty:
                    pass # It's fine if no extra message
                break
            if message["type"] == MSG_ERROR:
                print(f"Error during connection: {message['payload']}")
                return False
    except queue.Empty:
        print("Failed to connect to camera: Timeout waiting for connection confirmation.")
        connection.stop_worker()
        return False
    
    if not connected:
        print("Failed to connect to camera.")
        connection.stop_worker()
        return False

    # Ensure connection is fully established
    time.sleep(0.5) # Give worker thread a moment
    if not connection.edsdk or not connection.camera or not connection.session_open:
        print("Connection to camera is not fully established.")
        command_queue.put({"action": CMD_DISCONNECT})
        connection.stop_worker()
        return False

    print("Setting up CanonCameraController...")
    controller = CanonCameraController(connection)
    if not controller:
        print("Failed to initialize CanonCameraController.")
        command_queue.put({"action": CMD_DISCONNECT})
        connection.stop_worker()
        return False

    print("✓ Camera connection setup complete.")
    return True


def start_live_view():
    """Start the live view stream."""
    global live_view_active
    
    if not controller:
        print("Controller not initialized. Cannot start live view.")
        return False

    print("\nStarting Live View...")
    start_success = controller.start_live_view()
    if not start_success:
        print("Failed to start live view.")
        return False
    
    if not controller.live_view_active or not connection.live_view_active:
        print("Live view state not correctly updated. Check camera status.")
        return False
    
    live_view_active = True
    print("✓ Live View started successfully.")
    
    # Allow time for live view to stabilize
    time.sleep(1.0)
    return True


def stream_live_view():
    """Stream live view frames from the camera."""
    global running
    
    if not live_view_active:
        print("Live view is not active. Cannot stream frames.")
        return
    
    print("\nStreaming live view frames... Press Ctrl+C to stop.")
    frames_received = 0
    
    # Print frame info every second for stats
    last_stats_time = time.time()
    frames_since_stats = 0
    
    try:
        while running:
            try:
                # Wait for messages from the camera connection
                message = data_queue.get(timeout=1.0)
                
                if message["type"] == MSG_LIVE_FRAME:
                    frames_received += 1
                    frames_since_stats += 1
                    frame_payload = message["payload"]
                    
                    # Check if it's time to print stats (every 1 sec)
                    current_time = time.time()
                    if current_time - last_stats_time >= 1.0:
                        fps = frames_since_stats / (current_time - last_stats_time)
                        print(f"Streaming: {frames_received} frames total, {frames_since_stats} new frames " +
                              f"({fps:.1f} FPS), current frame size: {frame_payload.get('length', 0)} bytes", end='\r')
                        last_stats_time = current_time
                        frames_since_stats = 0
                    
                    # Here you could process the frame data if needed
                    # frame_data = frame_payload.get("data")
                    
                elif message["type"] == MSG_ERROR:
                    print(f"\nError during streaming: {message['payload']}")
                
                # Optional: Process all waiting messages to avoid queue backup
                while not data_queue.empty() and running:
                    try:
                        msg = data_queue.get_nowait()
                        if msg["type"] == MSG_LIVE_FRAME:
                            frames_received += 1
                            frames_since_stats += 1
                        elif msg["type"] == MSG_ERROR:
                            print(f"\nError during streaming: {msg['payload']}")
                    except queue.Empty:
                        break
                    
            except queue.Empty:
                # It's normal to time out occasionally if frames aren't coming constantly
                print("Waiting for frames...", end='\r')
        
        print(f"\n✓ Live view streaming stopped. Received {frames_received} frames total.")
    
    except KeyboardInterrupt:
        print("\nStreaming interrupted by user.")
        running = False


def stop_live_view():
    """Stop the live view stream."""
    global live_view_active
    
    if not controller or not live_view_active:
        return
    
    print("\nStopping Live View...")
    stop_success = controller.stop_live_view()
    if stop_success:
        print("✓ Live view stopped successfully.")
    else:
        print("Warning: Controller did not confirm live view stop, attempting direct command.")
        # Fallback if controller method is problematic
        if connection and connection.live_view_active:
            command_queue.put({"action": CMD_STOP_LIVE_VIEW})
            time.sleep(0.5) # Allow command to process
    
    live_view_active = False


def cleanup():
    """Clean up resources and disconnect from the camera."""
    global connection, controller, command_queue, data_queue, running
    
    running = False # Ensure any loops are stopped
    
    print("\nCleaning up...")
    
    # 1. Stop live view if it's active
    if live_view_active:
        stop_live_view()
    
    # 2. Disconnect from camera
    if connection:
        print("Disconnecting from camera...")
        command_queue.put({"action": CMD_DISCONNECT})
        try:
            # Wait for disconnect confirmation or proceed with worker stop
            for _ in range(5): # Short timeout
                message = data_queue.get(timeout=0.5)
                if message["type"] == MSG_CONNECTION_STATUS and message["payload"]["status"] == "disconnected":
                    print("✓ Camera disconnected successfully.")
                    break
                if message["type"] == MSG_LOG and "Disconnected" in message["payload"].get("message", ""):
                    print("✓ Camera disconnection logged.")
                    break
        except queue.Empty:
            pass # It's OK if no explicit confirmation
        
        # 3. Stop the worker thread
        print("Stopping CanonCameraConnection worker...")
        connection.stop_worker()
        
        # 4. Join the worker thread
        if connection.worker_thread and connection.worker_thread.is_alive():
            print("Waiting for worker thread to join...")
            connection.worker_thread.join(timeout=5)
            if connection.worker_thread.is_alive():
                print("Warning: Worker thread did not join in time.")
        else:
            print("✓ Worker thread stopped.")
    
    print("✓ Cleanup complete.")


def signal_handler(sig, frame):
    """Handle Ctrl+C signal to clean up resources."""
    print("\nCtrl+C detected. Stopping...")
    global running
    running = False


def main():
    """Main function to run the live view streaming application."""
    global running
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # 1. Connect to the camera
        if not setup_camera_connection():
            print("Failed to setup camera connection. Exiting.")
            return 1
        
        # 2. Start live view
        if not start_live_view():
            print("Failed to start live view. Exiting.")
            cleanup()
            return 1
        
        # 3. Stream live view frames
        stream_live_view()
        
    except Exception as e:
        print(f"\nError during execution: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 4. Clean up resources regardless of how we exit
        cleanup()
    
    print("Live view streaming completed successfully.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
