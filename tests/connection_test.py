"""
Minimal Canon Camera Connection Test

This script tests the camera connection sequence in isolation,
following the exact timing and sequence from Camera_Connections.md.

PYTHONPATH=$PYTHONPATH:. python tests/connection_test.py
"""

import ctypes
from src.canon_camera_connection import CanonCameraConnection
from src.canon_camera_controller import CanonCameraController

def test_connection():
    print("\n=== Canon Camera Connection Test ===")
    print("Following macOS-specific connection sequence...")
    
    try:
        # Create connection
        print("\n1. Creating connection object...")
        conn = CanonCameraConnection()
        
        # Attempt connection
        print("\n2. Attempting to connect...")
        conn.connect()
        
        if conn.camera:
            print("\n✓ Success! Camera connected.")
            
            # Test live view
            print("\n3. Testing live view...")
            controller = CanonCameraController(conn)
            
            print("Starting live view...")
            if controller.start_live_view():
                print("✓ Live view started successfully")
                
                # Test frame capture
                print("\nTesting frame capture...")
                stream = ctypes.c_void_p()
                err = conn.edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
                if err == 0:  # EDS_ERR_OK
                    print("Memory stream created")
                    frame_data = controller.download_evf_image(stream)
                    if frame_data:
                        print(f"✓ Successfully captured frame ({len(frame_data)} bytes)")
                        # Get status
                        status = controller.get_status()
                        print("\nCamera Status:")
                        print(f"- Battery Level: {status.battery_level}%")
                        print(f"- Temperature Status: {status.temperature_status}")
                        print(f"- Frames Captured: {status.frames_captured}")
                    else:
                        print("✗ Failed to capture frame")
                    conn.edsdk.EdsRelease(stream)
                else:
                    print(f"✗ Failed to create memory stream (error: {err})")
                
                print("\nStopping live view...")
                controller.stop_live_view()
                print("✓ Live view stopped")
            else:
                print("✗ Failed to start live view")
            
            print("\n4. Disconnecting...")
            conn.disconnect()
            print("✓ Camera disconnected cleanly.")
            return True
        else:
            print("\n✗ Failed to connect to camera.")
            return False
            
    except Exception as e:
        print(f"\n✗ Error during connection test: {e}")
        return False

if __name__ == "__main__":
    test_connection()
