import os
import sys
import cv2
import numpy as np
import time
import ctypes

# Add src directory to Python path
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
sys.path.append(src_dir)

from camera import CanonCamera

def print_instructions():
    print("""
Canon Camera Live Preview
------------------------
For best results:
1. Set camera to Photo mode (not Movie mode)
2. Enable live view on your camera if available
3. Remove any lens caps
4. Ensure good lighting
5. Press 'q' to quit viewer
""")

def main():
    print_instructions()
    print("Initializing...")
    
    try:
        with CanonCamera() as camera:
            print("\n✓ Camera connected successfully")
            
            # Enable live view
            result = camera.start_live_view()
            if result == 0:
                print("✓ Live view started")
            else:
                print("\n⚠️  Live view failed to start")
                print("Please check that:")
                print("1. Camera is in Photo mode (not Movie mode)")
                print("2. Live view is enabled on the camera")
                return
            
            evf_image = camera.create_evf_image()
            print("✓ EVF image initialized")
            
            # Create a window
            cv2.namedWindow("Canon Live Preview", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Canon Live Preview", 1280, 720)
            
            print("\nStarting preview... (Press 'q' to quit)")
            
            frame_count = 0
            last_frame_time = time.time()
            error_count = 0
            max_errors = 10  # Max consecutive errors before giving up
            
            while True:
                frame_start = time.time()
                
                # Get preview frame
                image_data = camera.download_evf_image(evf_image)
                
                if image_data:
                    error_count = 0  # Reset error counter on success
                    
                    # Calculate FPS
                    current_time = time.time()
                    fps = 1.0 / (current_time - last_frame_time)
                    last_frame_time = current_time
                    
                    # Convert and display frame
                    nparr = np.frombuffer(image_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        # Add FPS counter to frame
                        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.imshow("Canon Live Preview", frame)
                    
                else:
                    error_count += 1
                    if error_count >= max_errors:
                        print("\n⚠️  Lost connection to camera")
                        print("Please check that:")
                        print("1. Camera is still on")
                        print("2. USB cable is connected")
                        print("3. Camera is in Photo mode")
                        print("4. Live view is enabled")
                        break
                    time.sleep(0.1)  # Wait before retry
                
                frame_count += 1
                
                # Break if 'q' is pressed
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                # Cap frame rate
                elapsed = time.time() - frame_start
                if elapsed < 1/30:  # Target 30fps
                    time.sleep(1/30 - elapsed)
            
            cv2.destroyAllWindows()
            camera.release_evf_image(evf_image)
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting steps:")
        print("1. Ensure camera is in Photo mode (not Movie mode)")
        print("2. Turn camera off")
        print("3. Disconnect USB cable")
        print("4. Wait 5 seconds")
        print("5. Connect USB cable")
        print("6. Turn camera on")
        print("7. Enable live view")
        print("8. Try running viewer again")
        sys.exit(1)

if __name__ == "__main__":
    main()
