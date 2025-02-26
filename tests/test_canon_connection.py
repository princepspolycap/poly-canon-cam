"""
Canon Camera Connection Test

This module provides a focused test for connecting to Canon cameras using the EDSDK.
It includes detailed debugging output and step-by-step connection verification.
"""

import unittest
import os
import ctypes
import time

# EDSDK Constants
EDS_ERR_OK = 0
kEdsPropID_SaveTo = 0x0000000b
kEdsSaveTo_Host = 1
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001

class CanonConnectionTest(unittest.TestCase):
    """Test Canon camera connection with detailed debugging"""

    def setUp(self):
        """Set up test environment"""
        self.edsdk = None
        self.camera = None
        self.camera_list = None
        self.session_open = False
        
    def tearDown(self):
        """Clean up resources"""
        try:
            if self.session_open and self.camera:
                print("\nClosing session...")
                self.edsdk.EdsCloseSession(self.camera)
                
            if self.camera:
                print("Releasing camera...")
                self.edsdk.EdsRelease(self.camera)
                
            if self.camera_list:
                print("Releasing camera list...")
                self.edsdk.EdsRelease(self.camera_list)
                
            if self.edsdk:
                print("Terminating SDK...")
                self.edsdk.EdsTerminateSDK()
        except Exception as e:
            print(f"Cleanup error: {e}")

    def test_camera_connection_sequence(self):
        """Test complete camera connection sequence using SDK low-level calls"""
        
        # Step 1: Load EDSDK
        print("\nStep 1: Loading EDSDK")
        edsdk_path = "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"
        try:
            self.edsdk = ctypes.CDLL(edsdk_path)
            print("✓ EDSDK loaded successfully")
        except Exception as e:
            self.fail(f"Failed to load EDSDK: {e}")

        # Step 2: Initialize SDK
        print("\nStep 2: Initializing SDK")
        err = self.edsdk.EdsInitializeSDK()
        self.assertEqual(err, EDS_ERR_OK, f"SDK initialization failed with error: {err}")
        print("✓ SDK initialized successfully")

        # Step 3: Get camera list
        print("\nStep 3: Getting camera list")
        self.camera_list = ctypes.c_void_p()
        err = self.edsdk.EdsGetCameraList(ctypes.byref(self.camera_list))
        self.assertEqual(err, EDS_ERR_OK, f"Failed to get camera list: {err}")
        print("✓ Got camera list")

        # Step 4: Get camera count
        print("\nStep 4: Getting camera count")
        count = ctypes.c_uint32()
        err = self.edsdk.EdsGetChildCount(self.camera_list, ctypes.byref(count))
        self.assertEqual(err, EDS_ERR_OK, f"Failed to get camera count: {err}")
        print(f"✓ Found {count.value} camera(s)")

        # Verify at least one camera is connected
        self.assertGreater(count.value, 0, "No cameras detected. Please check:\n" +
                          "1. Camera is powered on\n" +
                          "2. Camera is in shooting mode (not playback)\n" +
                          "3. USB connection is set to 'PTP' or 'PC Connect'\n" +
                          "4. USB cable is securely connected")

        # Step 5: Get camera handle
        print("\nStep 5: Getting camera handle")
        self.camera = ctypes.c_void_p()
        err = self.edsdk.EdsGetChildAtIndex(self.camera_list, 0, ctypes.byref(self.camera))
        self.assertEqual(err, EDS_ERR_OK, f"Failed to get camera handle: {err}")
        print("✓ Got camera handle")

        # Step 6: Open session
        print("\nStep 6: Opening session")
        err = self.edsdk.EdsOpenSession(self.camera)
        self.assertEqual(err, EDS_ERR_OK, f"Failed to open session: {err}")
        self.session_open = True
        print("✓ Session opened successfully")

        # Step 7: Configure camera settings
        print("\nStep 7: Configuring camera settings")
        
        # Extend shutdown timer
        print("- Extending shutdown timer...")
        err = self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_ExtendShutDownTimer, 0)
        if err != EDS_ERR_OK:
            print(f"Warning: Failed to extend shutdown timer: {err}")
        else:
            print("✓ Shutdown timer extended")

        # Set save location to host
        print("- Setting save location to host...")
        save_to = ctypes.c_uint32(kEdsSaveTo_Host)
        err = self.edsdk.EdsSetPropertyData(
            self.camera,
            kEdsPropID_SaveTo,
            0,
            ctypes.sizeof(save_to),
            ctypes.byref(save_to)
        )
        if err != EDS_ERR_OK:
            print(f"Warning: Failed to set save location: {err}")
        else:
            print("✓ Save location set to host")

        print("\nCamera connection test completed successfully!")

if __name__ == '__main__':
    unittest.main(verbosity=2)
