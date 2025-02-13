import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
from camera import CanonCamera
import threading
import queue

class CameraApp:
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
        try:
            self.camera = CanonCamera()
            self.camera.connect()
            self.camera.start_live_view()
            self.evf_image = self.camera.create_evf_image()
            
            self.is_running = True
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.status_label.configure(text="Camera: Connected")
            
            # Start frame capture thread
            self.capture_thread = threading.Thread(target=self.capture_frames)
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
            # Start displaying frames
            self.show_frame()
            
        except Exception as e:
            self.status_label.configure(text=f"Error: {str(e)}")

    def capture_frames(self):
        while self.is_running:
            try:
                image_data = self.camera.download_evf_image(self.evf_image)
                if image_data:
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
            except Exception as e:
                print(f"Capture error: {e}")

    def show_frame(self):
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
        self.stop_camera()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = CameraApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
