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

import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
from camera import CanonCamera
import threading
import queue

class CameraApp:
    """
    Main GUI application class for Canon camera control.
    
    This class creates a window with camera preview and control buttons.
    It handles:
    - Camera connection and disconnection
    - Live preview display with proper scaling
    - Thread-safe frame capture and display
    - Resource cleanup on exit
    
    The live preview runs in a separate thread to prevent UI freezing,
    with thread-safe communication via a queue.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Canon Camera Viewer - Princeps Polycap Productions")
        
        # Create main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create canvas for video display
        self.canvas = tk.Canvas(self.main_frame, width=1280, height=720, bg="black")
        self.canvas.grid(row=0, column=0, columnspan=2, pady=5)
        
        # Create control buttons
        self.btn_frame = ttk.Frame(self.main_frame)
        self.btn_frame.grid(row=1, column=0, columnspan=2, pady=5)
        
        self.start_btn = ttk.Button(self.btn_frame, text="Start Camera", command=self.start_camera)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(self.btn_frame, text="Stop Camera", command=self.stop_camera, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_label = ttk.Label(self.main_frame, text="Camera: Disconnected")
        self.status_label.grid(row=2, column=0, columnspan=2, pady=5)
        
        # Initialize variables
        self.camera = None
        self.is_running = False
        self.frame_queue = queue.Queue(maxsize=1)
        self.show_frame_id = None
        
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_camera(self):
        """
        Initialize camera connection and start live preview.
        
        This method:
        1. Connects to the camera
        2. Starts live view
        3. Creates EVF image buffer
        4. Launches frame capture thread
        5. Updates UI elements
        
        Any errors during startup are displayed in the status label.
        """
        try:
            print("Initializing camera connection...")
            self.camera = CanonCamera()
            self.camera.connect()
            
            print("Connected to camera, waiting for device to stabilize...")
            self.status_label.configure(text="Camera: Initializing...")
            self.root.update()  # Force UI update
            
            # Allow camera to stabilize before starting live view
            self.root.after(1000)  # Wait 1 second
            
            print("Starting live view...")
            if not self.camera.start_live_view():
                self.status_label.configure(text="Error: Failed to start live view")
                if self.camera:
                    self.camera.disconnect()
                    self.camera = None
                return
            
            print("Creating EVF image buffer...")
            try:
                self.evf_image = self.camera.create_evf_image()
            except Exception as e:
                self.status_label.configure(text=f"Error: Failed to create EVF buffer - {str(e)}")
                if self.camera:
                    self.camera.disconnect()
                    self.camera = None
                return
            
            self.is_running = True
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.status_label.configure(text="Camera: Live view active")
            
            # Start frame capture thread
            self.capture_thread = threading.Thread(target=self.capture_frames)
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
            # Start displaying frames
            self.show_frame()
            
        except Exception as e:
            self.status_label.configure(text=f"Error: {str(e)}")

    def capture_frames(self):
        """
        Continuously capture frames from the camera.
        
        This method runs in a separate thread and:
        1. Downloads frames from the camera
        2. Converts them to the correct format
        3. Places them in the frame queue for display
        
        The loop continues until self.is_running is False.
        """
        while self.is_running:
            try:
                image_data = self.camera.download_evf_image(self.evf_image)
                if image_data:
                    try:
                        # Convert bytes to numpy array
                        nparr = np.frombuffer(image_data, np.uint8)
                        # Decode image
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            # Convert BGR to RGB
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            # Put frame in queue
                            if not self.frame_queue.full():
                                self.frame_queue.put(frame_rgb)
                        else:
                            print("Failed to decode image data")
                    except Exception as e:
                        print(f"Frame processing error: {e}")
                        # Don't break the capture loop for frame errors
                        continue
            except Exception as e:
                print(f"Capture error: {e}")
                if not self.is_running:
                    break

    def show_frame(self):
        """
        Display the most recent frame from the queue.
        
        This method:
        1. Gets the latest frame from the queue
        2. Resizes it to fit the canvas while maintaining aspect ratio
        3. Converts it to a format tkinter can display
        4. Updates the canvas
        
        This runs in the main thread and is scheduled using root.after()
        to maintain UI responsiveness.
        """
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
            print(f"Display error: {e}")
            
        if self.is_running:
            self.show_frame_id = self.root.after(10, self.show_frame)

    def stop_camera(self):
        """
        Stop camera preview and clean up resources.
        
        This method:
        1. Stops the frame capture thread
        2. Releases camera resources
        3. Updates UI elements
        4. Clears the preview canvas
        """
        self.is_running = False
        if self.show_frame_id:
            self.root.after_cancel(self.show_frame_id)
        if self.camera:
            if self.evf_image:
                self.camera.release_evf_image(self.evf_image)
            self.camera.disconnect()
            self.camera = None
        
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="Camera: Disconnected")
        self.canvas.delete("all")

    def on_closing(self):
        """
        Handle window close event.
        
        Ensures proper cleanup of camera resources before destroying the window.
        """
        self.stop_camera()
        self.root.destroy()

def main():
    """
    Application entry point.
    
    Creates the main window and starts the tkinter event loop.
    """
    root = tk.Tk()
    app = CameraApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
