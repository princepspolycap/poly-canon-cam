try:
    import syphon
    import numpy as np
    from syphon.utils.numpy import copy_image_to_mtl_texture
    SYPHON_AVAILABLE = True
except ImportError:
    SYPHON_AVAILABLE = False
    syphon = None
    print("Warning: Syphon not available. Syphon output disabled.")

try:
    import pyvirtualcam
    import numpy as np
    PYVIRTUALCAM_AVAILABLE = True
except ImportError:
    PYVIRTUALCAM_AVAILABLE = False
    pyvirtualcam = None
    print("Warning: PyVirtualCam not available. Virtual camera output disabled.")

import threading
import time
from collections import deque

class SyphonWebcamOutput:
    def __init__(self, server_name="CanonCamSyphon"):
        if not SYPHON_AVAILABLE:
            print(f"Warning: Syphon not available. {server_name} webcam output disabled.")
            
        self.server_name = server_name
        self.server = None
        self.texture = None
        self.is_running = False
        # Dimensions will be set on the first frame or explicitly
        self.width = 0
        self.height = 0

    def start(self, width, height):
        if not SYPHON_AVAILABLE:
            print("Syphon not available - virtual webcam start skipped")
            return
            
        if self.is_running:
            print("Syphon server already running.")
            return
        
        self.width = width
        self.height = height
        
        try:
            if not SYPHON_AVAILABLE:
                print("Syphon not available - cannot start server")
                return
                
            self.server = syphon.SyphonMetalServer(self.server_name)
            # Texture creation might be better here if size is fixed,
            # or it might be recreated if frame size can change.
            # For now, let's assume fixed size after start.
            # self.texture = create_mtl_texture(self.server.device, self.width, self.height) # Example from docs
            # Actual texture handling for dynamic frames will be refined.
            self.is_running = True
            print(f"Syphon server '{self.server_name}' started.")
        except Exception as e:
            print(f"Failed to start Syphon server: {e}")
            self.server = None
            self.is_running = False

    def send_frame(self, frame_rgb):
        if not SYPHON_AVAILABLE:
            return
            
        if not self.is_running or self.server is None:
            return

        # Resize frame if dimensions don't match
        if frame_rgb.shape[1] != self.width or frame_rgb.shape[0] != self.height:
            import cv2
            frame_rgb = cv2.resize(frame_rgb, (self.width, self.height))

        try:
            # Ensure frame is RGBA for Syphon Metal texture
            if frame_rgb.shape[2] == 3: # RGB
                frame_rgba = np.dstack((frame_rgb, np.full((self.height, self.width), 255, dtype=np.uint8)))
            elif frame_rgb.shape[2] == 4: # Already RGBA
                frame_rgba = frame_rgb
            else:
                print(f"Unsupported frame format with {frame_rgb.shape[2]} channels. Expected RGB or RGBA.")
                return

            # The syphon-python example creates one texture and updates it.
            # If self.texture is not created at start, it needs to be created here.
            if self.texture is None or \
               self.texture.width() != self.width or \
               self.texture.height() != self.height:
                # from syphon.metal import create_metal_texture # Correct import path if needed
                # This specific function might be slightly different, checking docs:
                # The example uses syphon.utils.raw.create_mtl_texture
                from syphon.utils.raw import create_mtl_texture as actual_create_mtl_texture
                self.texture = actual_create_mtl_texture(self.server.device, self.width, self.height)
                print(f"Syphon texture created: {self.width}x{self.height}")


            copy_image_to_mtl_texture(frame_rgba, self.texture)
            self.server.publish_frame_texture(self.texture)
        except Exception as e:
            print(f"Error sending frame to Syphon: {e}")

    def stop(self):
        if not SYPHON_AVAILABLE:
            return
            
        if self.server:
            try:
                self.server.stop()
                print(f"Syphon server '{self.server_name}' stopped.")
            except Exception as e:
                print(f"Error stopping Syphon server: {e}")
        self.is_running = False
        self.server = None
        self.texture = None # Release texture

class PyVirtualCamOutput:
    """
    Virtual camera output using PyVirtualCam with dedicated delivery thread.
    
    Maintains consistent frame rate (24-30 FPS) independent of source timing.
    Uses frame buffer to smooth out Canon camera's variable frame delivery.
    """
    def __init__(self, name="PolyCanonCam"):
        if not PYVIRTUALCAM_AVAILABLE:
            print(f"Warning: PyVirtualCam not available. {name} virtual camera disabled.")
            
        self.name = name
        self.cam = None
        self.is_running = False
        self.width = 0
        self.height = 0
        self.target_fps = 30
        
        # Frame buffer and delivery thread
        self.frame_buffer = deque(maxlen=10)  # Keep last 10 frames for better smoothing
        self.buffer_lock = threading.Lock()
        self.delivery_thread = None
        self.stop_event = threading.Event()
        
        # Stats for monitoring
        self.frames_sent = 0
        self.frames_dropped = 0
        self.frames_queued = 0
        self.last_frame = None

    def start(self, width, height, fps=30):
        """Start virtual camera output with dedicated delivery thread"""
        if not PYVIRTUALCAM_AVAILABLE:
            print("PyVirtualCam not available - cannot start virtual camera")
            return False
            
        if self.is_running:
            print("Virtual camera already running.")
            return True
        
        self.width = width
        self.height = height
        self.target_fps = max(24, min(fps, 30))  # Clamp to 24-30 FPS range
        
        try:
            # On macOS, this requires OBS Virtual Camera to be installed
            self.cam = pyvirtualcam.Camera(width, height, self.target_fps, fmt=pyvirtualcam.PixelFormat.RGB)
            self.is_running = True
            
            # Start dedicated delivery thread
            self.stop_event.clear()
            self.delivery_thread = threading.Thread(
                target=self._frame_delivery_loop,
                name=f"{self.name}_DeliveryThread",
                daemon=True
            )
            self.delivery_thread.start()
            
            print(f"Virtual camera '{self.name}' started at {width}x{height} @ {self.target_fps}fps")
            print(f"Device: {self.cam.device}")
            print(f"Frame buffer: {self.frame_buffer.maxlen} frames for timing smoothness")
            return True
        except Exception as e:
            print(f"Failed to start virtual camera: {e}")
            print("On macOS: Install OBS Studio and start 'Tools > Start Virtual Camera'")
            self.cam = None
            self.is_running = False
            return False

    def send_frame(self, frame_rgb):
        """
        Queue RGB frame for delivery to virtual camera.
        Frames are sent by dedicated thread at consistent FPS.
        """
        if not PYVIRTUALCAM_AVAILABLE or not self.is_running:
            return
            
        try:
            # PyVirtualCam expects RGB format (H, W, 3)
            if frame_rgb.shape[2] == 4:  # RGBA to RGB
                frame_rgb = frame_rgb[:, :, :3]
            
            # Verify dimensions match - resize if needed
            if frame_rgb.shape[0] != self.height or frame_rgb.shape[1] != self.width:
                import cv2
                frame_rgb = cv2.resize(frame_rgb, (self.width, self.height))
            
            # Add to buffer (thread-safe)
            with self.buffer_lock:
                was_full = len(self.frame_buffer) >= self.frame_buffer.maxlen
                self.frame_buffer.append(frame_rgb.copy())
                self.frames_queued += 1
                
                if was_full:
                    self.frames_dropped += 1
                    # Only log every 50th drop to avoid spam
                    if self.frames_dropped % 50 == 0:
                        print(f"[{self.name}] Warning: Buffer full, {self.frames_dropped} frames dropped total")
                
        except Exception as e:
            print(f"Error queuing frame to virtual camera: {e}")

    def _frame_delivery_loop(self):
        """
        Dedicated thread that delivers frames at consistent FPS.
        
        This ensures OBS Virtual Camera receives frames at exactly the target
        frame rate, preventing disconnects and logo flashing.
        """
        print(f"[{self.name}] Frame delivery thread started (target: {self.target_fps} FPS)")
        
        while not self.stop_event.is_set():
            try:
                # Get latest frame from buffer
                frame_to_send = None
                with self.buffer_lock:
                    if self.frame_buffer:
                        # Always use the most recent frame
                        frame_to_send = self.frame_buffer[-1]
                        self.last_frame = frame_to_send
                    elif self.last_frame is not None:
                        # No new frames - reuse last frame to maintain stream
                        frame_to_send = self.last_frame
                
                # Send frame to virtual camera
                if frame_to_send is not None and self.cam is not None:
                    self.cam.send(frame_to_send)
                    self.frames_sent += 1
                    
                    # Log stats periodically
                    if self.frames_sent % 300 == 0:  # Every 10 seconds at 30 FPS
                        queue_rate = (self.frames_queued / max(1, self.frames_sent)) * 100
                        print(f"[{self.name}] Delivered {self.frames_sent} frames "
                              f"(queued: {self.frames_queued}, dropped: {self.frames_dropped}, "
                              f"queue/send ratio: {queue_rate:.1f}%, buffer: {len(self.frame_buffer)})")
                    
                    # Use PyVirtualCam's adaptive sleep for precise timing
                    self.cam.sleep_until_next_frame()
                else:
                    # No frame available yet or cam not ready - wait briefly
                    time.sleep(1.0 / self.target_fps)
                        
            except Exception as e:
                print(f"[{self.name}] Error in delivery thread: {e}")
                time.sleep(0.1)  # Brief pause on error
        
        print(f"[{self.name}] Frame delivery thread stopped")

    def stop(self):
        """Stop virtual camera output and delivery thread"""
        if not PYVIRTUALCAM_AVAILABLE:
            return
        
        self.is_running = False
        
        # Stop delivery thread
        if self.delivery_thread and self.delivery_thread.is_alive():
            print(f"Stopping {self.name} delivery thread...")
            self.stop_event.set()
            self.delivery_thread.join(timeout=2.0)
        
        # Close camera
        if self.cam:
            try:
                self.cam.close()
                print(f"Virtual camera '{self.name}' stopped.")
                print(f"Final stats: {self.frames_sent} frames sent, {self.frames_queued} queued, {self.frames_dropped} dropped")
            except Exception as e:
                print(f"Error stopping virtual camera: {e}")
        
        self.cam = None
        self.frame_buffer.clear()
        self.last_frame = None


class VirtualWebcamManager:
    """Manages both Syphon and PyVirtualCam outputs simultaneously"""
    def __init__(self, name="PolyCanonCam"):
        self.name = name
        self.syphon = SyphonWebcamOutput(f"{name}_Syphon") if SYPHON_AVAILABLE else None
        self.virtualcam = PyVirtualCamOutput(name) if PYVIRTUALCAM_AVAILABLE else None
        self._started = False
        
    @property
    def is_running(self):
        """Check if any output is actually running"""
        if not self._started:
            return False
        
        # Check actual state of outputs AND their threads
        syphon_running = self.syphon and self.syphon.is_running
        virtualcam_running = (self.virtualcam and 
                             self.virtualcam.is_running and 
                             self.virtualcam.delivery_thread and 
                             self.virtualcam.delivery_thread.is_alive())
        
        return syphon_running or virtualcam_running
        
    def start(self, width, height, fps=30):
        """Start all available outputs (only starts if not already started)"""
        # If already started, don't call start() again on child outputs
        # This prevents restart loops!
        if self._started:
            return self.is_running
            
        results = []
        
        if self.syphon:
            self.syphon.start(width, height)
            if self.syphon.is_running:
                results.append("Syphon")
        
        if self.virtualcam:
            if self.virtualcam.start(width, height, fps):
                results.append("Virtual Camera")
        
        # Mark as started - this prevents calling start() multiple times
        self._started = True
        
        if results:
            print(f"Started outputs: {', '.join(results)}")
        else:
            print("No virtual outputs available")
            
        return self.is_running
    
    def send_frame(self, frame_rgb):
        """Send frame to all active outputs"""
        if not self._started:
            return
            
        if self.syphon and self.syphon.is_running:
            self.syphon.send_frame(frame_rgb)
            
        if self.virtualcam and self.virtualcam.is_running:
            self.virtualcam.send_frame(frame_rgb)
    
    def stop(self):
        """Stop all outputs"""
        if self.syphon:
            self.syphon.stop()
        if self.virtualcam:
            self.virtualcam.stop()
        self._started = False


if __name__ == '__main__':
    # Test usage
    import time
    import numpy as np
    
    manager = VirtualWebcamManager("TestOutput")
    
    if manager.start(1920, 1080, 30):
        print("Sending test frames for 5 seconds...")
        
        # Create a test pattern (gradient)
        for i in range(150):  # 5 seconds at 30fps
            frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
            # Moving gradient
            frame[:, :, 0] = (i * 5) % 255  # Red channel
            frame[:, :, 1] = 128  # Green channel
            frame[:, :, 2] = 255 - ((i * 5) % 255)  # Blue channel
            
            manager.send_frame(frame)
            time.sleep(1/30)  # 30fps
            
        manager.stop()
        print("Test complete")
    else:
        print("Failed to start any virtual outputs")
