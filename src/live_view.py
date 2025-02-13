import cv2
import numpy as np
from camera import CanonCamera

def main():
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
