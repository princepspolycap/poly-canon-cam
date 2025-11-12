import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import queue
import time
import os
from datetime import datetime
from .canon_camera_connection import CanonCameraConnection
from .gui_style import apply_modern_style
from .camera_constants import (
    MSG_LOG, MSG_ERROR, MSG_CONNECTION_STATUS,
    MSG_CAMERA_INFO, MSG_STATUS_UPDATE, MSG_LIVE_FRAME, MSG_WARNING
)


class FrameRateMonitor:
    """Monitor frame rate for live view display"""
    def __init__(self):
        self.frame_times = []
        self.max_samples = 30
        
    def add_frame(self):
        """Record a new frame timestamp"""
        current_time = time.time()
        self.frame_times.append(current_time)
        
        # Keep only recent samples
        if len(self.frame_times) > self.max_samples:
            self.frame_times = self.frame_times[-self.max_samples:]
    
    def get_fps(self):
        """Calculate current FPS"""
        if len(self.frame_times) < 2:
            return 0.0
        
        time_span = self.frame_times[-1] - self.frame_times[0]
        if time_span > 0:
            return (len(self.frame_times) - 1) / time_span
        return 0.0
    
    def reset(self):
        """Reset frame time tracking"""
        self.frame_times = []


class LogDisplay:
    """Log display widget with timestamp and scrolling"""
    def __init__(self, parent):
        self.frame = ttk.LabelFrame(parent, text="System Log", style='Card.TLabelframe')
        
        # Create text widget with scrollbar
        self.text_frame = ttk.Frame(self.frame)
        self.text_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.scrollbar = ttk.Scrollbar(self.text_frame)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text_widget = tk.Text(
            self.text_frame,
            height=6,
            wrap=tk.WORD,
            yscrollcommand=self.scrollbar.set,
            bg='#1e1e1e',
            fg='#e0e0e0',
            font=('Monaco', 10),
            padx=10,
            pady=5
        )
        self.text_widget.pack(side=tk.LEFT, fill="both", expand=True)
        self.scrollbar.config(command=self.text_widget.yview)
        
        # Configure text tags for different message types
        self.text_widget.tag_config("timestamp", foreground="#808080")
        self.text_widget.tag_config("info", foreground="#e0e0e0")
        self.text_widget.tag_config("error", foreground="#ff6b6b")
        self.text_widget.tag_config("warning", foreground="#feca57")
        self.text_widget.tag_config("success", foreground="#48dbfb")
        
        # Make text widget read-only
        self.text_widget.config(state=tk.DISABLED)
    
    def log(self, message, level="info", timestamp=True):
        """Add a log message with optional timestamp"""
        self.text_widget.config(state=tk.NORMAL)
        
        if timestamp:
            time_str = datetime.now().strftime("[%H:%M:%S] ")
            self.text_widget.insert(tk.END, time_str, "timestamp")
        
        self.text_widget.insert(tk.END, message + "\n", level)
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.see(tk.END)  # Auto-scroll to bottom


class CameraControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Canon Camera Live View Controller")
        
        # Apply modern styling
        apply_modern_style(self.root)
        
        # Main container
        self.main_container = ttk.Frame(self.root, style='TFrame')
        self.main_container.pack(fill="both", expand=True)
        
        # Header
        self.header_frame = ttk.Frame(self.main_container, style='Header.TFrame')
        self.header_frame.pack(fill="x", padx=5, pady=5)
        
        self.title_label = ttk.Label(
            self.header_frame,
            text="📷 Canon Camera Control",
            style='Title.TLabel'
        )
        self.title_label.pack(side=tk.LEFT, padx=15)
        
        self.status_label = ttk.Label(
            self.header_frame,
            text="⚪ Not Connected",
            style='Status.TLabel'
        )
        self.status_label.pack(side=tk.RIGHT, padx=15)
        
        # Content area with two columns
        self.content_frame = ttk.Frame(self.main_container, style='TFrame')
        self.content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Left column - Camera Display
        self.display_frame = ttk.LabelFrame(
            self.content_frame,
            text="Live View Display",
            style='Card.TLabelframe'
        )
        self.display_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 5))
        
        # Camera view canvas
        self.canvas = tk.Canvas(
            self.display_frame,
            bg='#000000',
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        
        # FPS display
        self.fps_label = ttk.Label(
            self.display_frame,
            text="FPS: 0.0",
            style='Info.TLabel'
        )
        self.fps_label.pack(pady=(0, 10))
        
        # Right column - Controls
        self.controls_frame = ttk.Frame(self.content_frame, style='TFrame')
        self.controls_frame.pack(side=tk.RIGHT, fill="y", padx=(5, 0))
        
        # 1. Camera Info Card
        self.info_card = ttk.LabelFrame(self.controls_frame, text="Camera Information", style='Card.TLabelframe')
        self.info_card.pack(fill="x", padx=10, pady=(0, 10))
        
        self.info_labels_frame = ttk.Frame(self.info_card, style='Card.TFrame')
        self.info_labels_frame.pack(fill="x", padx=8, pady=8)
        
        self.camera_model_label = ttk.Label(self.info_labels_frame, text="Model: Not connected", style='Info.TLabel')
        self.camera_model_label.pack(anchor=tk.W, pady=2)
        
        self.camera_serial_label = ttk.Label(self.info_labels_frame, text="Serial: N/A", style='Info.TLabel')
        self.camera_serial_label.pack(anchor=tk.W, pady=2)
        
        self.camera_firmware_label = ttk.Label(self.info_labels_frame, text="Firmware: N/A", style='Info.TLabel')
        self.camera_firmware_label.pack(anchor=tk.W, pady=2)
        
        # 2. Camera Connection with combined Live View
        self.connection_card = ttk.LabelFrame(self.controls_frame, text="Camera Control", style='Card.TLabelframe')
        self.connection_card.pack(fill="x", padx=10, pady=10)
        
        self.connection_buttons_frame = ttk.Frame(self.connection_card, style='Card.TFrame')
        self.connection_buttons_frame.pack(fill="x", padx=8, pady=8)
        
        self.connect_button = ttk.Button(
            self.connection_buttons_frame, 
            text="Connect & Start Live View", 
            command=self.cmd_connect_and_start_live_view, 
            style='Accent.TButton'
        )
        self.connect_button.pack(fill="x", pady=(0, 5))
        
        self.stop_lv_button = ttk.Button(
            self.connection_buttons_frame, 
            text="Stop Live View", 
            command=self.cmd_stop_live_view, 
            style='Secondary.TButton',
            state=tk.DISABLED
        )
        self.stop_lv_button.pack(fill="x", pady=(0, 5))
        
        self.disconnect_button = ttk.Button(
            self.connection_buttons_frame, 
            text="Disconnect Camera", 
            command=self.cmd_disconnect_camera, 
            style='Danger.TButton',
            state=tk.DISABLED
        )
        self.disconnect_button.pack(fill="x")
        
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
        self.auto_start_live_view = False  # Flag to auto-start live view after connection
        
        # Window positioning and size
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.update_idletasks()
        width, height = 1280, 800
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.minsize(900, 600)
        
        # Start application
        self.log_display.log("Application initialized. Click 'Connect & Start Live View' to begin.")
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
                elif msg_type == MSG_WARNING:
                    self._handle_warning_message(payload)

        except queue.Empty:
            pass
        except Exception as e:
            self.log_display.log(f"Error processing camera data: {e}", level="error")

        self._data_queue_after_id = self.root.after(50, self._process_camera_data_queue)

    def _handle_error_message(self, payload):
        message = payload.get("message", "Unknown error")
        self.log_display.log(f"ERROR: {message}", level="error")
        
        # Reset connecting flag on error
        if self.is_connecting:
            self.is_connecting = False
            self.connect_button.config(state=tk.NORMAL, text="Connect & Start Live View")

    def _handle_connection_status_message(self, payload):
        status = payload.get("status", "unknown")
        message = payload.get("message", "")
        
        self.log_display.log(f"Connection Status: {status} - {message}")
        
        if status == "connected":
            self.is_connecting = False  # Clear connecting flag
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.status_label.config(text="🟢 Connected")
            
            # Auto-start live view if flag is set
            if self.auto_start_live_view:
                self.auto_start_live_view = False
                self.root.after(500, self.cmd_start_live_view)  # Small delay to ensure connection is stable
        
        elif status == "disconnected":
            self.is_connecting = False  # Clear connecting flag
            self._reset_to_disconnected_state()
        
        elif status in ["sdk_loaded", "sdk_initialized"]:
            # Intermediate states during connection
            pass

    def _handle_camera_info_message(self, payload):
        model = payload.get("model", "Unknown")
        serial = payload.get("serial", "Unknown")
        firmware = payload.get("firmware", "Unknown")
        
        self.camera_model_label.config(text=f"Model: {model}")
        self.camera_serial_label.config(text=f"Serial: {serial}")
        self.camera_firmware_label.config(text=f"Firmware: {firmware}")

    def _handle_status_update_message(self, payload):
        if "live_view_status" in payload:
            lv_status = payload["live_view_status"]
            if lv_status == "active":
                self.is_running_live_view = True
                self.stop_lv_button.config(state=tk.NORMAL)
                self.status_label.config(text="🟢 Connected - Live View Active")
                self.log_display.log("Live view is now active")
            else:
                self.is_running_live_view = False
                self.stop_lv_button.config(state=tk.DISABLED)
                if self.camera_connection:
                    self.status_label.config(text="🟢 Connected")

    def _handle_live_frame_message(self, payload):
        frame_data = payload.get("frame_data")
        if frame_data:
            try:
                # Decode base64 if needed, or use raw bytes
                if isinstance(frame_data, str):
                    import base64
                    frame_bytes = base64.b64decode(frame_data)
                else:
                    frame_bytes = frame_data
                    
                # Convert to numpy array and decode
                nparr = np.frombuffer(frame_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    self._display_frame(frame)
                    self.frame_monitor.add_frame()
                    fps = self.frame_monitor.get_fps()
                    self.fps_label.config(text=f"FPS: {fps:.1f}")
            except Exception as e:
                self.log_display.log(f"Error displaying frame: {e}", level="error")

    def _handle_warning_message(self, payload):
        message = payload.get("message", "Warning")
        self.log_display.log(f"⚠️ {message}", level="warning")

    def _display_frame(self, frame):
        """Display a frame on the canvas"""
        try:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Get canvas size
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width > 1 and canvas_height > 1:
                # Calculate scaling to fit canvas while maintaining aspect ratio
                h, w = frame_rgb.shape[:2]
                scale = min(canvas_width/w, canvas_height/h)
                new_width = int(w * scale)
                new_height = int(h * scale)
                
                # Resize frame
                frame_resized = cv2.resize(frame_rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
                
                # Convert to PIL Image
                image = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(image)
                
                # Update canvas
                self.canvas.delete("all")
                x = (canvas_width - new_width) // 2
                y = (canvas_height - new_height) // 2
                self.canvas.create_image(x, y, anchor=tk.NW, image=photo)
                
                # Keep reference to prevent garbage collection
                self.current_image_ref = photo
                
        except Exception as e:
            self.log_display.log(f"Display error: {e}", level="error")

    def cmd_connect_and_start_live_view(self):
        """Connect to camera and automatically start live view"""
        if self.is_connecting:
            self.log_display.log("Connection already in progress...")
            return
            
        self.log_display.log("Connecting to camera...")
        self.is_connecting = True
        self.connect_button.config(state=tk.DISABLED, text="Connecting...")
        
        # Create new camera connection worker ONLY if one doesn't exist
        # This allows fast reconnection without SDK reinitialization
        if not self.camera_connection:
            self.log_display.log("No active camera worker, creating new one.")
            self.camera_connection = CanonCameraConnection()
            self.camera_connection.start_worker(
                command_queue=self.camera_command_queue,
                data_queue=self.camera_data_queue
            )
        else:
            self.log_display.log("Reusing existing camera worker for reconnection.")
        
        # Send connect command
        self.camera_command_queue.put({
            "action": "connect",
            "data": {}
        })
        
        # Set flag to auto-start live view after connection
        self.auto_start_live_view = True

    def cmd_disconnect_camera(self):
        """Disconnect from camera (keep SDK/worker alive for fast reconnection)"""
        if self.camera_connection:
            self.log_display.log("Disconnecting from camera...")
            
            # Stop live view first if active with proper wait time
            if self.is_running_live_view:
                self.cmd_stop_live_view()
                time.sleep(1.0)  # Increased wait time for live view to fully stop
            
            # ONLY send disconnect command - DO NOT shutdown worker/SDK
            # This keeps the worker thread and SDK initialized for fast reconnection
            self.camera_command_queue.put({
                "action": "disconnect",
                "data": {}
            })
            
            # Wait for disconnect to complete (shorter delay since no SDK termination)
            self.root.after(1000, self._finalize_disconnect)
        else:
            self._reset_to_disconnected_state()
    
    def _finalize_disconnect(self):
        """Finalize disconnect - keep worker/SDK alive for reconnection"""
        # DON'T set self.camera_connection to None - keep worker alive!
        self._reset_to_disconnected_state()
        self.log_display.log("Camera disconnected successfully. SDK ready for reconnection.")

    def cmd_start_live_view(self):
        """Start live view"""
        if self.camera_connection:
            self.log_display.log("Starting live view...")
            self.camera_command_queue.put({
                "action": "start_live_view",
                "data": {}
            })
        else:
            self.log_display.log("Not connected to camera", level="warning")

    def cmd_stop_live_view(self):
        """Stop live view"""
        if self.camera_connection:
            self.log_display.log("Stopping live view...")
            self.camera_command_queue.put({
                "action": "stop_live_view",
                "data": {}
            })
            self.is_running_live_view = False
            self.stop_lv_button.config(state=tk.DISABLED)
            self.canvas.delete("all")
            self.fps_label.config(text="FPS: 0.0")
            self.frame_monitor.reset()
        else:
            self.log_display.log("Not connected to camera", level="warning")

    def _reset_to_disconnected_state(self):
        """Reset GUI to disconnected state"""
        self.connect_button.config(state=tk.NORMAL, text="Connect & Start Live View")
        self.disconnect_button.config(state=tk.DISABLED)
        self.stop_lv_button.config(state=tk.DISABLED)
        self.status_label.config(text="⚪ Not Connected")
        self.camera_model_label.config(text="Model: Not connected")
        self.camera_serial_label.config(text="Serial: N/A")
        self.camera_firmware_label.config(text="Firmware: N/A")
        self.canvas.delete("all")
        self.fps_label.config(text="FPS: 0.0")
        self.is_running_live_view = False
        self.frame_monitor.reset()

    def update_gui_for_status(self):
        """Update GUI elements based on connection status"""
        # This method is called on initialization
        # Most updates now happen via message handlers
        pass

    def on_closing(self):
        """Handle window closing"""
        if self.camera_connection:
            self.log_display.log("Closing application...")
            
            # First disconnect camera if connected
            if self.is_running_live_view:
                self.cmd_stop_live_view()
                time.sleep(0.5)
            
            # Send disconnect command
            self.camera_command_queue.put({"action": "disconnect", "data": {}})
            time.sleep(0.5)
            
            # NOW shutdown the SDK worker completely
            self.log_display.log("Shutting down camera SDK...")
            self.camera_command_queue.put({"action": "shutdown", "data": {}})
            time.sleep(1.0)  # Wait for clean shutdown
            
            self.camera_connection = None
        
        # Cancel any pending after callbacks
        if self._data_queue_after_id:
            self.root.after_cancel(self._data_queue_after_id)
        if self.reconnect_timer_id:
            self.root.after_cancel(self.reconnect_timer_id)
            
        self.root.destroy()


def create_app():
    """Create and return the camera control application."""
    root = tk.Tk()
    app = CameraControlPanel(root)
    return app


def main():
    """Main entry point when running gui.py directly."""
    app = create_app()
    app.root.mainloop()


if __name__ == "__main__":
    main()