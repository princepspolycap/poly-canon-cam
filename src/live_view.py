"""
Live View Module

This module handles live view streaming from Canon cameras with frame rate control
and proper synchronization to prevent overwhelming the camera or running into
stream I/O errors.
"""

import time
import threading
from typing import Optional, Callable
from contextlib import contextmanager

class FrameRateController:
    """Controls frame timing and synchronization for live view streaming."""
    
    def __init__(self, target_fps: float = 30.0):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        self.last_frame_time = 0.0
        self.frame_count = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
        
    def wait_for_next_frame(self) -> float:
        """
        Wait until it's time for the next frame.
        
        Returns:
            float: Time waited in seconds
        """
        with self._lock:
            now = time.time()
            elapsed = now - self.last_frame_time
            
            # If we're running behind, don't wait
            if elapsed >= self.frame_interval:
                wait_time = 0
            else:
                wait_time = self.frame_interval - elapsed
                time.sleep(wait_time)
            
            self.last_frame_time = time.time()
            self.frame_count += 1
            return wait_time
            
    @property
    def current_fps(self) -> float:
        """Calculate current frames per second."""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.frame_count / elapsed
        return 0.0
        
    def reset(self):
        """Reset frame timing stats."""
        with self._lock:
            self.frame_count = 0
            self.start_time = time.time()
            self.last_frame_time = self.start_time

class LiveViewManager:
    """
    Manages live view streaming with proper frame timing and error recovery.
    
    This class coordinates between the camera and display code to ensure:
    1. Frame rate stays within camera capabilities
    2. Proper cleanup of resources
    3. Synchronized frame updates
    4. Error recovery and retry logic
    """
    
    def __init__(self, camera, target_fps: float = 30.0):
        self.camera = camera
        self.frame_controller = FrameRateController(target_fps)
        self.running = False
        self._lock = threading.Lock()
        
    def start(self):
        """Start live view streaming."""
        with self._lock:
            if not self.running:
                # Don't start live view if it's already active
                if not self.camera.live_view_active:
                    if not self.camera.start_live_view():
                        raise RuntimeError("Failed to start live view")
                self.running = True
                self.frame_controller.reset()
    
    def stop(self):
        """Stop live view streaming."""
        with self._lock:
            if self.running:
                self.camera.stop_live_view()
                self.running = False
    
    def _verify_live_view_state(self):
        """Verify and attempt to recover live view state if needed."""
        if not self.camera.live_view_active:
            print("Live view state lost - attempting recovery")
            if not self.camera.start_live_view():
                raise RuntimeError("Failed to recover live view state")
            print("Live view state recovered")

    @contextmanager
    def frame_context(self):
        """
        Context manager for frame acquisition.
        
        This ensures proper timing between frames and handles cleanup.
        Includes state verification and recovery.
        
        Example:
            with live_view.frame_context() as frame:
                if frame:
                    display_frame(frame)
        """
        if not self.running:
            raise RuntimeError("Live view not started")
            
        # Verify live view state before proceeding
        self._verify_live_view_state()
            
        # Wait for appropriate frame timing
        wait_time = self.frame_controller.wait_for_next_frame()
        
        # Create EVF image resources
        stream = None
        try:
            stream = self.camera.create_evf_image()
            
            # Verify live view state again after resource creation
            self._verify_live_view_state()
            
            # Get frame data
            frame_data = self.camera.download_evf_image(stream)
            
            # If frame capture failed, verify state once more
            if frame_data is None:
                self._verify_live_view_state()
                
            yield frame_data
            
        except Exception as e:
            print(f"Frame capture error: {e}")
            # Attempt recovery on next frame
            self._verify_live_view_state()
            yield None
            
        finally:
            # Clean up resources
            if stream is not None:
                try:
                    self.camera.release_evf_image(stream)
                except Exception as e:
                    print(f"Resource cleanup error: {e}")
    
    @property
    def fps(self) -> float:
        """Get current frames per second."""
        return self.frame_controller.current_fps

def main():
    """Example usage of live view manager."""
    from .camera import CanonCamera
    import cv2
    import numpy as np
    
    def display_frame(frame_data):
        if not frame_data:
            return
            
        # Convert frame data to OpenCV format
        nparr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None:
            cv2.imshow('Live View', frame)
    
    try:
        with CanonCamera() as camera:
            manager = LiveViewManager(camera)
            manager.start()
            
            print("Press 'q' to exit")
            
            while True:
                with manager.frame_context() as frame:
                    if frame:
                        display_frame(frame)
                        
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
                # Print FPS every 30 frames
                if manager.frame_controller.frame_count % 30 == 0:
                    print(f"FPS: {manager.fps:.1f}")
                    
    finally:
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
