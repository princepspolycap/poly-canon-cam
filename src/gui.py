"""
GUI Application Module for Poly Canon Cam

This module provides a graphical user interface for controlling and viewing
Canon camera live preview. It uses tkinter for the GUI and handles camera
operations in a separate thread to maintain UI responsiveness.

Features:
- Live preview display with automatic resizing
- Start/Stop camera controls
- Status indicators
- Clean shutdown handling
- Thread-safe frame capture and display
"""

import ctypes
import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
from . import CanonCamera, LiveViewManager, SyphonWebcamOutput
from .camera import EDS_ERR_OK, CameraError, CanonCameraController
import threading
import queue
import time
import collections

class FrameRateMonitor:
    """Monitor and calculate frame rate statistics."""
    def __init__(self, window_size=30):
        self.frame_times = collections.deque(maxlen=window_size)
        self.total_frames = 0
        self.start_time = time.time()
        
    def update(self):
        """Record a new frame."""
        self.frame_times.append(time.time())
        self.total_frames += 1
        
    @property
    def current_fps(self):
        """Calculate current frames per second."""
        if len(self.frame_times) < 2:
            return 0.0
        return len(self.frame_times) / (self.frame_times[-1] - self.frame_times[0])
    
    @property
    def average_fps(self):
        """Calculate average FPS since start."""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.total_frames / elapsed
        return 0.0

class LogDisplay:
    """Display for camera and system logs."""
    def __init__(self, parent):
        self.frame = ttk.LabelFrame(parent, text="System Log")
        self.text = tk.Text(self.frame, height=6, width=50)
        self.text.pack(padx=5, pady=5, fill="both", expand=True)
        self.frame.pack(padx=5, pady=5, fill="x")
        
    def log(self, message):
        """Add a message to the log."""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.text.insert("end", f"[{timestamp}] {message}\n")
        self.text.see("end")  # Auto-scroll to bottom
        
    def clear(self):
        """Clear all log entries."""
        self.text.delete(1.0, "end")

class CameraApp:
    """Main GUI application class for Canon camera control."""
    def __init__(self, root):
        self.root = root
        self.root.title("Canon Camera Viewer - Princeps Polycap Productions")
        
        # Main container
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill="both", expand=True)
        
        # Create canvas for video display
        self.canvas = tk.Canvas(self.main_frame, width=1280, height=720, bg="black")
        self.canvas.pack(pady=5)
        
        # Status display
        self.status_frame = ttk.LabelFrame(self.main_frame, text="Camera Status")
        self.status_frame.pack(fill="x", padx=5, pady=5)
        
        # Stats display
        self.stats_var = tk.StringVar()
        self.stats_label = ttk.Label(self.status_frame, textvariable=self.stats_var)
        self.stats_label.pack(fill="x", padx=5, pady=2)
        
        # Error display
        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(self.status_frame, textvariable=self.error_var, 
                                   foreground="red")
        self.error_label.pack(fill="x", padx=5, pady=2)
        
        # Log display
        self.log_display = LogDisplay(self.main_frame)
        
        # Control buttons
        self.btn_frame = ttk.Frame(self.main_frame)
        self.btn_frame.pack(pady=5)
        
        self.start_btn = ttk.Button(self.btn_frame, text="Start Camera", 
                                  command=self.start_camera)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(self.btn_frame, text="Stop Camera", 
                                 command=self.stop_camera, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Initialize variables
        self.camera = None
        self.controller = None
        self.live_view = None
        self.syphon_output = None
        self.is_running = False
        self.frame_queue = queue.Queue(maxsize=1)
        self.show_frame_id = None
        self.target_fps = 30.0
        self.frame_monitor = FrameRateMonitor()
        
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start status update
        self.update_status()
        
        # Center the window on screen
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
        # Log initial status
        self.log_display.log("Application initialized. Click 'Start Camera' to begin.")

    def start_camera(self):
        """Initialize camera connection and start live preview."""
        try:
            self.log_display.log("Initializing camera connection...")
            
            self.camera = None  # Initialize camera variable to avoid scope issues
            try:
                self.camera = CanonCamera()
                self.camera.connect()
            except CameraError as e:
                # Handle specific camera errors with user-friendly messages
                error_msg = str(e)
                if "No cameras detected" in error_msg:
                    self.error_var.set("No camera detected. Please check:")
                    self.log_display.log("1. Camera is powered on")
                    self.log_display.log("2. Camera is in photo mode (not playback/video)")
                    self.log_display.log("3. USB connection is set to 'PTP' or 'PC Connect'")
                    self.log_display.log("4. USB cable is securely connected")
                    return
                else:
                    self.error_var.set(f"Camera Error: {error_msg}")
                    self.log_display.log(error_msg)
                    if e.recovery_hint:
                        self.log_display.log(e.recovery_hint)
                    return
            
            self.log_display.log("Connected to camera, waiting for device to stabilize...")
            self.controller = CanonCameraController(self.camera) # Initialize controller
            self.status_label.configure(text="Camera: Initializing...")
            self.root.update()
            
            # Allow camera to stabilize before starting live view
            self.root.after(1000)
            
            # Initialize LiveViewManager first
            self.log_display.log("Initializing live view manager...")
            self.live_view = LiveViewManager(self.controller, self.target_fps)
            
            self.log_display.log("Starting live view...")
            try:
                self.live_view.start()
                self.is_running = True
                if self.is_running: # Ensure live view started successfully
                    try:
                        # Get frame dimensions from canvas or a default, Syphon needs width/height
                        # It's better if the camera can provide actual stream dimensions.
                        # For now, let's use the canvas dimensions as a placeholder.
                        # This might need adjustment if stream dimensions differ.
                        width = self.canvas.winfo_width() 
                        height = self.canvas.winfo_height()
                        if width <= 1 or height <= 1: # Canvas might not be realized yet
                            width, height = 1280, 720 # Fallback default
                            self.log_display.log(f"Canvas not realized, using default {width}x{height} for Syphon.")

                        self.syphon_output = SyphonWebcamOutput() # Default server name "CanonCamSyphon"
                        self.syphon_output.start(width, height)
                        if self.syphon_output.is_running:
                            self.log_display.log("Syphon output server started.")
                        else:
                            self.log_display.log("Syphon output server failed to start. Webcam functionality may not work.")
                            # Optionally, set self.syphon_output to None if it failed
                            if self.syphon_output and not self.syphon_output.is_running:
                                 self.syphon_output = None
                    except Exception as e:
                        self.log_display.log(f"Error initializing Syphon output: {e}")
                        if self.syphon_output: # Ensure cleanup if partial init
                            self.syphon_output.stop()
                        self.syphon_output = None
            except Exception as e:
                error_msg = f"Error: Failed to start live view - {str(e)}"
                self.error_var.set(error_msg)
                self.log_display.log(error_msg)
                if self.live_view:
                    try:
                        self.live_view.stop()
                    except:
                        pass
                    self.live_view = None
                if self.controller: # Clean up controller
                    self.controller = None
                if self.camera:
                    try:
                        self.camera.disconnect()
                    except:
                        pass
                    self.camera = None
                return

            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.stats_var.set("Initializing stats...")
            
            # Start frame capture thread
            self.capture_thread = threading.Thread(target=self.capture_frames)
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
            # Start displaying frames
            self.show_frame()
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.error_var.set(error_msg)
            self.log_display.log(error_msg)
            # Clean up any resources if initialization failed
            if hasattr(self, 'camera') and self.camera:
                try:
                    self.camera.disconnect()
                except:
                    pass
                self.camera = None

    def capture_frames(self):
        """Continuously capture frames from the camera."""
        while self.is_running:
            try:
                with self.live_view.frame_context() as frame_data:
                    if frame_data:
                        try:
                            # Convert bytes to numpy array
                            nparr = np.frombuffer(frame_data, np.uint8)
                            # Decode image
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            if frame is not None:
                                # Convert BGR to RGB
                                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                if self.syphon_output and self.syphon_output.is_running:
                                    try:
                                        self.syphon_output.send_frame(frame_rgb)
                                    except Exception as e:
                                        self.log_display.log(f"Error sending frame to Syphon: {e}")
                                # Put frame in queue
                                if not self.frame_queue.full():
                                    self.frame_queue.put(frame_rgb)
                                    self.frame_monitor.update()
                                    
                            else:
                                self.log_display.log("Failed to decode image data")
                        except Exception as e:
                            self.log_display.log(f"Frame processing error: {e}")
                            continue
            except Exception as e:
                if self.is_running:
                    self.log_display.log(f"Capture error: {e}")
                    self.error_var.set(f"Capture error: {e}")

    def show_frame(self):
        """Display the most recent frame from the queue."""
        try:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                # Convert frame to PhotoImage
                image = Image.fromarray(frame)
                # Resize to fit canvas while maintaining aspect ratio
                canvas_ratio = self.canvas.winfo_width() / self.canvas.winfo_height()
                image_ratio = image.width / image.height
                
                if image_ratio > canvas_ratio:
                    new_width = self.canvas.winfo_width()
                    new_height = int(new_width / image_ratio)
                else:
                    new_height = self.canvas.winfo_height()
                    new_width = int(new_height * image_ratio)
                
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image=image)
                
                # Keep a reference to prevent garbage collection
                self.current_image = photo
                
                # Update canvas
                self.canvas.create_image(
                    self.canvas.winfo_width()//2,
                    self.canvas.winfo_height()//2,
                    image=photo,
                    anchor=tk.CENTER
                )
        except Exception as e:
            self.log_display.log(f"Display error: {e}")
            
        if self.is_running:
            self.show_frame_id = self.root.after(10, self.show_frame)

    def update_status(self):
        """Update status display with current statistics."""
        if self.is_running and self.controller:
            try:
                status = self.controller.get_status()
                stats = (
                    f"FPS: {self.frame_monitor.current_fps:.1f} "
                    f"(Avg: {self.frame_monitor.average_fps:.1f}) | "
                    f"Temp: {status.temperature_status:#x} | "
                    f"Mode: {status.mode}"
                )
                self.stats_var.set(stats)
                
                # Log warnings
                if status.temperature_status & 0x0002:
                    self.error_var.set("Warning: Camera temperature elevated")
                    
            except Exception as e:
                self.error_var.set(f"Status Error: {e}")
                
        # Schedule next update
        self.root.after(1000, self.update_status)

    def stop_camera(self):
        """Stop camera preview and clean up resources."""
        # Set flags first to stop any ongoing operations
        self.is_running = False
        
        # Cancel any pending frame updates
        if self.show_frame_id:
            try:
                self.root.after_cancel(self.show_frame_id)
            except:
                pass
            self.show_frame_id = None
        
        # Stop live view manager first
        if self.live_view:
            try:
                self.live_view.stop()
            except Exception as e:
                self.log_display.log(f"Error stopping live view: {e}")
            self.live_view = None
        
        # Disconnect camera last    
        if self.camera:
            try:
                self.camera.disconnect()
            except Exception as e:
                self.log_display.log(f"Error disconnecting camera: {e}")
            self.camera = None
        if self.syphon_output:
            try:
                self.syphon_output.stop()
                self.log_display.log("Syphon output server stopped.")
            except Exception as e:
                self.log_display.log(f"Error stopping Syphon output: {e}")
            self.syphon_output = None
        self.controller = None # Clean up controller
        
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.stats_var.set("")
        self.error_var.set("")
        self.canvas.delete("all")
        self.log_display.log("Camera stopped and resources cleaned up")

    def on_closing(self):
        """Handle window close event."""
        self.stop_camera()
        self.root.destroy()

def create_app():
    """Create and configure the main application window."""
    root = tk.Tk()
    return CameraApp(root)
