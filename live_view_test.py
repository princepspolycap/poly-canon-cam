import os
import sys

# Add src directory to Python path
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
sys.path.append(src_dir)

import cv2
import numpy as np
from camera import CanonCamera
import time

def test_live_view():
    print("Starting live view test...")
    try:
        with CanonCamera() as camera:
            print("Camera connected")
            camera.start_live_view()
            print("Live view started")
            
            evf_image = camera.create_evf_image()
            print("EVF image created")
            
            # Create a window
            cv2.namedWindow("Live View", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Live View", 1280, 720)
            
            print("Press 'q' to quit")
            
            while True:
                image_data = camera.download_evf_image(evf_image)
                if image_data:
                    # Convert bytes to numpy array
                    nparr = np.frombuffer(image_data, np.uint8)
                    # Decode image
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        cv2.imshow("Live View", frame)
                
                # Break if 'q' is pressed
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                # Small delay to prevent high CPU usage
                time.sleep(0.01)
            
            cv2.destroyAllWindows()
            camera.release_evf_image(evf_image)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_live_view()
