"""
Live View Module for Poly Canon Cam

This module provides a simplified live view implementation for testing and development.
It demonstrates basic camera connection and live view functionality without the additional
features of the main viewer (like FPS counter, error recovery, etc.).

This is primarily used for testing camera connectivity and basic live view operation.
For the full-featured viewer, use viewer.py instead.
"""

import cv2
import numpy as np
from .camera import CanonCamera

def main():
    """
    Simple live view demonstration.
    
    This function:
    1. Connects to the first available Canon camera
    2. Starts live view
    3. Displays the camera feed in a basic window
    4. Cleans up resources on exit
    
    The preview can be stopped by pressing 'q'.
    
    This implementation is intentionally minimal to serve as a test bed
    for basic camera functionality.
    """
    try:
        # Use context manager for automatic cleanup
        with CanonCamera() as camera:
            print("Starting live view...")
            camera.start_live_view()
            evf_image = camera.create_evf_image()

            print("Streaming live view. Press 'q' to exit...")
            try:
                while True:
                    # Download and display the image
                    image_data = camera.download_evf_image(evf_image)
                    if image_data:
                        # Convert bytes to numpy array
                        nparr = np.frombuffer(image_data, np.uint8)
                        # Decode image
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            cv2.imshow('Live View', frame)
                    
                    # Check for 'q' key to quit (wait 1ms for key event)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

            finally:
                # Clean up resources
                cv2.destroyAllWindows()
                camera.release_evf_image(evf_image)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
