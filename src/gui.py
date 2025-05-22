"""
GUI Application Module for Poly Canon Cam

This module provides a graphical user interface for controlling and viewing
Canon camera live preview. It uses tkinter for the GUI. Camera operations
are handled by CanonCameraConnection in a separate worker thread to maintain
UI responsiveness.
"""

import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
import queue
import time
import collections
import threading

# Assuming CanonCameraConnection and its constants are in the same directory or accessible
from .canon_camera_connection import (
    CanonCameraConnection,
    CMD_CONNECT, CMD_DISCONNECT, CMD_START_LIVE_VIEW, CMD_STOP_LIVE_VIEW,
    CMD_GET_CAMERA_INFO, CMD_GET_STATUS, CMD_SHUTDOWN,
    MSG_STATUS_UPDATE, MSG_ERROR, MSG_CAMERA_INFO, MSG_LIVE_FRAME,
    MSG_CONNECTION_STATUS, MSG_LOG
)
from src.camera_constants import CameraError
from . import SyphonWebcamOutput # Keep for now
from . import gui_style


class FrameRateMonitor:
    """Monitor and calculate frame rate statistics."""
    def __init__(self, window_size=30):
        self.frame_times = collections.deque(maxlen=window_size)
        self.total_frames = 0
        self.start_time = time.time()
        
    def new_frame(self):
        """Record a new frame."""
        self.frame_times.append(time.time())
        self.total_frames += 1
        
    @property
    def current_fps(self):
        """Calculate current frames per second."""
        if len(self.frame_times) < 2:
            return 0.0
        # Ensure denominator is not zero
        delta_time = self.frame_times[-1] - self.frame_times[0]
        return (len(self.frame_times) -1) / delta_time if delta_time > 0 else 0.0
    
    @property
    def average_fps(self):
        """Calculate average FPS since start."""
        elapsed = time.time() - self.start_time
        return self.total_frames / elapsed if elapsed > 0 else 0.0


class LogDisplay:
    """Display for camera and system logs."""
    def __init__(self, parent):
        self.frame = ttk.LabelFrame(parent, text="System Log", style='Card.TLabelframe')
        self.text = tk.Text(
            self.frame, height=6, width=40, bg=gui_style.COLORS['bg_light'],
            fg=gui_style.COLORS['text_primary'], font=('SF Pro Text', 12), wrap=tk.WORD,
            padx=8, pady=8, relief='flat', borderwidth=0
        )
        scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.text.yview, style="Vertical.TScrollbar")
        self.text.pack(side='left', fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side='right', fill='y', padx=(0, 8), pady=8)
        self.text.configure(yscrollcommand=scrollbar.set)
        
    def log(self, message, timestamp=True):
        """Add a message to the log."""
        prefix = f"[{time.strftime('%H:%M:%S', time.localtime())}] " if timestamp else ""
        self.text.insert("end", f"{prefix}{message}\n")
        self.text.see("end")
        
    def clear(self):
        self.text.delete(1.0, "end")


class CameraApp:
    """Main GUI application class for Canon camera control."""
    def __init__(self, root):
        self.root = root
        self.root.title("Canon Camera Viewer - Princeps Polycap Productions")
        self.root.configure(bg=gui_style.COLORS['bg_dark'])
        self.root.option_add('*TCombobox*Listbox.background', gui_style.COLORS['bg_light'])
        self.root.option_add('*TCombobox*Listbox.foreground', gui_style.COLORS['text_primary'])
        self.root.option_add('*TCombobox*Listbox.selectBackground', gui_style.COLORS['primary'])
        
        # Setup main container
        self.main_container = gui_style.create_gradient_frame(self.root)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Header section
        self.header_frame = ttk.Frame(self.main_container, style='TFrame')
        self.header_frame.pack(fill="x", padx=5, pady=(5, 15))
        
        self.title_label = ttk.Label(self.header_frame, text="Canon Camera Control", style='Title.TLabel')
        self.title_label.pack(side=tk.LEFT, padx=10)
        
        # Connection status display in header
        self.connection_frame = ttk.Frame(self.header_frame, style='TFrame')
        self.connection_frame.pack(side=tk.RIGHT, padx=10)
        
        self.status_icon_label = ttk.Label(self.connection_frame, text="●", style='StatusIcon.TLabel')
        self.status_icon_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.connection_var = tk.StringVar(value="Disconnected")
        self.connection_label = ttk.Label(self.connection_frame, textvariable=self.connection_var, style='Status.TLabel')
        self.connection_label.pack(side=tk.LEFT)
        
        # Main content - split into two panes: Live View (left) and Controls (right)
        self.content_frame = ttk.Frame(self.main_container, style='TFrame')
        self.content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create PanedWindow for resizable split
        self.paned_window = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill="both", expand=True)
        
        # Left pane - Live View
        self.live_view_frame = gui_style.create_gradient_frame(self.paned_window, 
                                                              bg_color=gui_style.COLORS['bg_medium'])
        
        # Right pane - Controls
        self.controls_frame = ttk.Frame(self.paned_window, style='TFrame')
        
        self.paned_window.add(self.live_view_frame, weight=3)  # Give live view more space
        self.paned_window.add(self.controls_frame, weight=1)
        
        # Live View Canvas
        self.canvas_container = ttk.Frame(self.live_view_frame, style='TFrame')
        self.canvas_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.canvas_header = ttk.Label(self.canvas_container, text="Camera Live View", style='TLabel')
        self.canvas_header.pack(fill="x", padx=5, pady=(0, 5))
        
        self.canvas = tk.Canvas(
            self.canvas_container, 
            bg=gui_style.COLORS['bg_dark'],
            highlightthickness=1,
            highlightbackground=gui_style.COLORS['border']
        )
        self.canvas.pack(fill="both", expand=True)
        
        # Stats bar below canvas
        self.stats_frame = ttk.Frame(self.canvas_container, style='TFrame')
        self.stats_frame.pack(fill="x", padx=5, pady=5)
        
        self.stats_var = tk.StringVar()
        self.stats_label = ttk.Label(self.stats_frame, textvariable=self.stats_var, style='Stats.TLabel')
        self.stats_label.pack(side=tk.LEFT, fill="x", expand=True)
        
        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(self.stats_frame, textvariable=self.error_var, style='Error.TLabel')
        self.error_label.pack(side=tk.RIGHT)
        
        # Controls Panel (right side)
        # 1. Camera Info Card
        self.info_card = ttk.LabelFrame(self.controls_frame, text="Camera Information", style='Card.TLabelframe')
        self.info_card.pack(fill="x", padx=10, pady=10)
        
        self.camera_info_var = tk.StringVar(value="No Camera Connected")
        self.camera_info_label = ttk.Label(self.info_card, textvariable=self.camera_info_var, style='Info.TLabel')
        self.camera_info_label.pack(fill="x", padx=8, pady=8)
        
        # 2. Connection Controls
        self.connection_card = ttk.LabelFrame(self.controls_frame, text="Connection", style='Card.TLabelframe')
        self.connection_card.pack(fill="x", padx=10, pady=10)
        
        self.connection_buttons_frame = ttk.Frame(self.connection_card, style='Card.TFrame')
        self.connection_buttons_frame.pack(fill="x", padx=8, pady=8)
        
        self.connect_button = ttk.Button(
            self.connection_buttons_frame, 
            text="Connect Camera", 
            command=self.cmd_connect_camera, 
            style='Accent.TButton'
        )
        self.connect_button.pack(fill="x", pady=(0, 5))
        
        self.disconnect_button = ttk.Button(
            self.connection_buttons_frame, 
            text="Disconnect", 
            command=self.cmd_disconnect_camera, 
            style='Danger.TButton',
            state=tk.DISABLED
        )
        self.disconnect_button.pack(fill="x")
        
        # 3. Live View Controls
        self.live_view_card = ttk.LabelFrame(self.controls_frame, text="Live View Control", style='Card.TLabelframe')
        self.live_view_card.pack(fill="x", padx=10, pady=10)
        
        self.live_view_buttons_frame = ttk.Frame(self.live_view_card, style='Card.TFrame')
        self.live_view_buttons_frame.pack(fill="x", padx=8, pady=8)
        
        self.start_lv_button = ttk.Button(
            self.live_view_buttons_frame, 
            text="Start Live View", 
            command=self.cmd_start_live_view, 
            style='TButton',
            state=tk.DISABLED
        )
        self.start_lv_button.pack(fill="x", pady=(0, 5))
        
        self.stop_lv_button = ttk.Button(
            self.live_view_buttons_frame, 
            text="Stop Live View", 
            command=self.cmd_stop_live_view, 
            style='Danger.TButton',
            state=tk.DISABLED
        )
        self.stop_lv_button.pack(fill="x")
        
        # Placeholder for future controls
        self.future_controls_frame = ttk.Frame(self.controls_frame, style='TFrame')
        self.future_controls_frame.pack(fill="both", expand=True)
        
        # Bottom section
        self.bottom_frame = ttk.Frame(self.main_container, style='TFrame')
        self.bottom_frame.pack(fill="x", padx=5, pady=(15, 5))
        
        # Logs
        self.log_display = LogDisplay(self.bottom_frame)
        self.log_display.frame.pack(fill="x", pady=5)
        
        # Footer with version info
        self.footer_frame = ttk.Frame(self.main_container, style='TFrame')
        self.footer_frame.pack(fill="x", padx=5, pady=5)
        
        self.version_label = ttk.Label(
            self.footer_frame, 
            text="EDSDK Version 13.19.0 | v1.0.0", 
            style='Status.TLabel'
        )
        self.version_label.pack(side=tk.RIGHT, padx=10)
        
        # Initialize camera connection and communication queues
        self.camera_connection = None
        self.camera_command_queue = queue.Queue()
        self.camera_data_queue = queue.Queue()
        
        self.syphon_output = None
        self.is_running_live_view = False
        self.current_image_ref = None
        self.frame_monitor = FrameRateMonitor()
        self.reconnect_timer_id = None
        self._data_queue_after_id = None
        self.is_connecting = False # Flag to track connection attempt - INITIALIZE EARLIER
        
        # Window positioning and size
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.update_idletasks()
        width, height = 1280, 800
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.minsize(900, 600)
        
        # Start application
        self.log_display.log("Application initialized. Click 'Connect Camera' to begin.")
        self.update_gui_for_status()
        self._start_data_queue_processing()
        # self.is_connecting = False # Moved earlier


    def _start_data_queue_processing(self):
        if self._data_queue_after_id:
            self.root.after_cancel(self._data_queue_after_id)
        self._process_camera_data_queue()

    def _process_camera_data_queue(self):
        try:
            while not self.camera_data_queue.empty():
                msg = self.camera_data_queue.get_nowait()
                msg_type = msg.get("type")
                payload = msg.get("payload", {})

                if msg_type == MSG_LOG:
                    self.log_display.log(payload.get("message", "Log: Empty message"), timestamp=False)
                elif msg_type == MSG_ERROR:
                    self._handle_error_message(payload)
                elif msg_type == MSG_CONNECTION_STATUS:
                    self._handle_connection_status_message(payload)
                elif msg_type == MSG_CAMERA_INFO:
                    self._handle_camera_info_message(payload)
                elif msg_type == MSG_STATUS_UPDATE:
                    self._handle_status_update_message(payload)
                elif msg_type == MSG_LIVE_FRAME:
                    self._handle_live_frame_message(payload)
                else:
                    self.log_display.log(f"GUI received unknown message type: {msg_type}")
                self.camera_data_queue.task_done()
        except queue.Empty:
            pass
        except Exception as e:
            self.log_display.log(f"Error processing data queue: {e}")
        
        self._data_queue_after_id = self.root.after(50, self._process_camera_data_queue)

    def _handle_error_message(self, payload):
        err_msg = payload.get("message", "Unknown error")
        source = payload.get("source", "CameraWorker")
        self.error_var.set(f"⚠️ Error: {err_msg[:100]}")
        self.log_display.log(f"ERROR ({source}): {err_msg}")
        if "No cameras detected" in err_msg or "Failed to get camera list" in err_msg:
            if self.is_connecting: # Only schedule reconnect if it was part of an active attempt
                self._schedule_reconnect_attempt()
            else: # If not actively connecting (e.g. spontaneous error), just update UI
                self.update_gui_for_status("disconnected_error")


    def _handle_connection_status_message(self, payload):
        status = payload.get("status")
        message = payload.get("message", "")
        self.log_display.log(f"Connection Status: {status} - {message}")

        current_connection_state = "disconnected"

        if status == "sdk_loaded":
            self.connection_var.set("SDK Loaded")
            current_connection_state = "sdk_loaded"
        elif status == "sdk_initialized":
            self.connection_var.set("Initializing...")
            current_connection_state = "sdk_initialized"
        elif status == "connecting": # This status might be set by GUI, not worker
            self.connection_var.set("Connecting...")
            current_connection_state = "connecting"
            self.is_connecting = True
        elif status == "connected":
            self.connection_var.set("Connected")
            if self.reconnect_timer_id: # Clear reconnect timer on successful connection
                self.root.after_cancel(self.reconnect_timer_id)
                self.reconnect_timer_id = None
            self.is_connecting = False
            current_connection_state = "connected"
            # Automatically request camera info and status after connection
            self.camera_command_queue.put({"action": CMD_GET_CAMERA_INFO})
            self.camera_command_queue.put({"action": CMD_GET_STATUS})
        elif status == "disconnected" or status == "disconnected_error":
            self.connection_var.set("Disconnected" if status == "disconnected" else "Connection Error")
            self.is_running_live_view = False
            self.is_connecting = False # No longer actively trying if fully disconnected
            current_connection_state = status # "disconnected" or "disconnected_error"
        elif status == "shutdown_complete":
            self.connection_var.set("Shutdown")
            self.is_running_live_view = False
            self.is_connecting = False
            current_connection_state = "shutdown"
        else:
            self.connection_var.set(message or status)
            # Infer state if possible, otherwise default to disconnected
            if "fail" in status.lower() or "error" in status.lower():
                current_connection_state = "disconnected_error"
            else:
                current_connection_state = "disconnected" # Default for unknown

        self.update_gui_for_status(current_connection_state)
        self.status_icon_label.configure(foreground=gui_style.STATUS_COLORS.get(status, gui_style.STATUS_COLORS['disconnected']))


    def _handle_camera_info_message(self, payload):
        name = payload.get("product_name", "N/A")
        serial = payload.get("serial_number", "N/A")
        fw = payload.get("firmware_version", "N/A")
        self.camera_info_var.set(f"Model: {name}\nSerial: {serial}\nFirmware: {fw}")

    def _handle_status_update_message(self, payload):
        battery = payload.get("battery_level", -1)
        temp_code = payload.get("temperature_status", 0)
        mode = payload.get("mode", -1)
        live_view_status = payload.get("live_view_status")

        if live_view_status == "active":
            self.is_running_live_view = True
        elif live_view_status == "inactive":
            self.is_running_live_view = False
        
        self.update_gui_for_status("connected" if self.camera_connection else "disconnected")

        temp_str = self.get_temp_status_str(temp_code)
        battery_str = f"{battery}%" if battery != -1 else "N/A"
        mode_str = f"Mode: {mode}"

        fps_curr = self.frame_monitor.current_fps
        fps_avg = self.frame_monitor.average_fps
        
        stats_text = f"Stream: {fps_curr:.1f} FPS (Avg: {fps_avg:.1f}) | Temp: {temp_str} | Battery: {battery_str} | {mode_str}"
        self.stats_var.set(stats_text)

        if temp_code & 0x0002:
            self.error_var.set("⚠️ Warning: Camera temperature elevated")
        elif not self.error_var.get().startswith("⚠️ Error"):
             self.error_var.set("")

    def _handle_live_frame_message(self, payload):
        frame_bytes = payload.get("data")
        if frame_bytes:
            try:
                nparr = np.frombuffer(frame_bytes, np.uint8)
                frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame_bgr is not None:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    
                    # Syphon Output (if enabled)
                    if self.syphon_output and self.syphon_output.is_running:
                        try:
                            self.syphon_output.send_frame(frame_rgb)
                        except Exception as e:
                            self.log_display.log(f"Syphon send error: {e}")
                            
                    pil_image = Image.fromarray(frame_rgb)
                    self.show_frame_on_canvas(pil_image)
                    self.frame_monitor.new_frame()
                else:
                    self.log_display.log("Failed to decode live frame.")
            except Exception as e:
                self.log_display.log(f"Error processing live frame: {e}")

    def show_frame_on_canvas(self, image_pil):
        try:
            # Clear previous image
            self.canvas.delete("all")
            
            canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            if canvas_w <= 1 or canvas_h <= 1:
                return

            img_w, img_h = image_pil.size
            if img_w == 0 or img_h == 0: 
                return

            canvas_ratio = canvas_w / canvas_h
            image_ratio = img_w / img_h
            
            if image_ratio > canvas_ratio:
                new_width = canvas_w
                new_height = int(new_width / image_ratio)
            else:
                new_height = canvas_h
                new_width = int(new_height * image_ratio)
            
            resized_image = image_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.current_image_ref = ImageTk.PhotoImage(image=resized_image)
            
            # Center the image
            x = (canvas_w - new_width) // 2
            y = (canvas_h - new_height) // 2
            self.canvas.create_image(x, y, image=self.current_image_ref, anchor=tk.NW)
        except Exception as e:
            self.log_display.log(f"Display error: {e}")

    def update_gui_for_status(self, status_key=None):
        connected = self.camera_connection and self.camera_connection.worker_thread and self.camera_connection.worker_thread.is_alive()

        if status_key == "disconnected" or status_key == "shutdown" or status_key == "disconnected_error":
            connected = False
            self.is_running_live_view = False

        # Update button states
        can_connect = not connected and not self.is_connecting
        self.connect_button.config(state=tk.NORMAL if can_connect else tk.DISABLED)
        
        can_disconnect = connected # Can always try to disconnect if worker thinks it's connected
        self.disconnect_button.config(state=tk.NORMAL if can_disconnect else tk.DISABLED)

        can_start_lv = connected and not self.is_running_live_view
        self.start_lv_button.config(state=tk.NORMAL if can_start_lv else tk.DISABLED)

        can_stop_lv = connected and self.is_running_live_view
        self.stop_lv_button.config(state=tk.NORMAL if can_stop_lv else tk.DISABLED)

        # Update display texts
        if not connected:
            self.camera_info_var.set("No Camera Connected")
            self.stats_var.set("")
            self.canvas.delete("all")
            
            # Display a message on the canvas
            canvas_w, canvas_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            if canvas_w > 1 and canvas_h > 1:
                self.canvas.create_text(
                    canvas_w/2, canvas_h/2,
                    text="No Camera Connected\nClick 'Connect Camera' to begin",
                    fill=gui_style.COLORS['text_secondary'],
                    font=('SF Pro Text', 16),
                    justify=tk.CENTER
                )

    def cmd_connect_camera(self):
        if self.is_connecting and not self.reconnect_timer_id: # Already trying, not a scheduled retry
            self.log_display.log("Connection attempt already in progress.")
            return

        if self.reconnect_timer_id: # If a reconnect was scheduled, cancel it for this manual attempt
            self.root.after_cancel(self.reconnect_timer_id)
            self.reconnect_timer_id = None
            self.log_display.log("Cancelled scheduled reconnect attempt due to manual connect.")

        self.log_display.log("Connecting to camera...")
        self.error_var.set("")
        self.is_connecting = True # Set flag
        self.update_gui_for_status("connecting") # Update button states immediately

        if not self.camera_connection or not (self.camera_connection.worker_thread and self.camera_connection.worker_thread.is_alive()):
            self.log_display.log("No active camera worker, creating new one.")
            self.camera_connection = CanonCameraConnection()
            self.camera_connection.start_worker(self.camera_command_queue, self.camera_data_queue)
            # Give worker a moment to start before sending command
            self.root.after(200, lambda: self.camera_command_queue.put({"action": CMD_CONNECT}))
        else:
            self.log_display.log("Existing camera worker found, sending connect command.")
            self.camera_command_queue.put({"action": CMD_CONNECT})
        # self.update_gui_for_status() # Already called with "connecting"

    def cmd_disconnect_camera(self):
        self.log_display.log("Disconnecting camera...")
        if self.reconnect_timer_id: # Cancel any pending reconnect if user disconnects
            self.root.after_cancel(self.reconnect_timer_id)
            self.reconnect_timer_id = None
            self.log_display.log("Cancelled scheduled reconnect attempt due to manual disconnect.")
        
        self.is_connecting = False # No longer trying to connect

        if self.camera_connection:
            self.camera_command_queue.put({"action": CMD_DISCONNECT})
        # GUI will update to "disconnected" via _handle_connection_status_message
        # self.update_gui_for_status("disconnected") # Avoid race condition, let worker confirm

    def cmd_start_live_view(self):
        self.log_display.log("Starting live view...")
        if self.camera_connection:
            self.camera_command_queue.put({"action": CMD_START_LIVE_VIEW})

    def cmd_stop_live_view(self):
        self.log_display.log("Stopping live view...")
        if self.camera_connection:
            self.camera_command_queue.put({"action": CMD_STOP_LIVE_VIEW})

    def _schedule_reconnect_attempt(self):
        if self.reconnect_timer_id:
            self.root.after_cancel(self.reconnect_timer_id)
        self.log_display.log("Scheduling reconnect in 5 seconds...")
        self.reconnect_timer_id = self.root.after(5000, self.cmd_connect_camera)

    def get_temp_status_str(self, status_code):
        if status_code == 0: return "Normal"
        if status_code & 0x0002: return "⚠️ High"
        if status_code & 0x0004: return "🔥 Critical"
        return f"Unknown ({status_code:#x})"

    def cleanup_resources(self):
        self.log_display.log("Cleaning up resources...")
        if self._data_queue_after_id:
            self.root.after_cancel(self._data_queue_after_id)
            self._data_queue_after_id = None
        if self.reconnect_timer_id:
            self.root.after_cancel(self.reconnect_timer_id)
            self.reconnect_timer_id = None
            
        if self.camera_connection:
            self.log_display.log("Stopping camera worker...")
            self.camera_connection.stop_worker()
            self.camera_connection = None
        
        if self.syphon_output:
            try:
                self.syphon_output.stop()
                self.log_display.log("Syphon output stopped.")
            except Exception as e:
                self.log_display.log(f"Error stopping Syphon: {e}")
            self.syphon_output = None
        
        self.is_running_live_view = False
        self.update_gui_for_status("shutdown")
        self.log_display.log("Cleanup complete.")

    def on_closing(self):
        self.log_display.log("Shutting down application...")
        self.cleanup_resources()
        self.root.destroy()

def create_app():
    root = tk.Tk()
    gui_style.setup_styles(root)
    app = CameraApp(root)
    return app

# if __name__ == '__main__':
#     root = tk.Tk()
#     gui_style.setup_styles(root)
#     app = CameraApp(root)
#     root.mainloop()
