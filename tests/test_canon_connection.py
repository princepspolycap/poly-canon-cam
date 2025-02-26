"""
Canon Camera Connection Test - Enhanced macOS Version

This module provides a robust test for connecting to Canon cameras using the EDSDK on macOS.
It includes enhanced macOS-specific handling, detailed debugging output, and comprehensive
error recovery mechanisms.

Based on Canon EDSDK API Programming Reference documentation for macOS:
"macOS 13(Ventura) or later, the number of cameras may be returned as 0 when 
getting the camera list. In such cases, try runloop processing before getting 
the camera list."
"""

import unittest
import os
import ctypes
import time
import subprocess
import platform

# EDSDK Constants
EDS_ERR_OK = 0
kEdsPropID_SaveTo = 0x0000000b
kEdsSaveTo_Host = 1
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001

class CanonConnectionTest(unittest.TestCase):
    """Test Canon camera connection with enhanced macOS compatibility"""

    def setUp(self):
        """Set up test environment"""
        self.edsdk = None
        self.camera = None
        self.camera_list = None
        self.session_open = False
        
        # Print system information for diagnostics
        print(f"\nRunning test on {platform.system()} {platform.release()}")
        print(f"Python version: {platform.python_version()}")
        
    def tearDown(self):
        """
        Clean up resources in the correct order to prevent memory leaks and crashes.
        
        Order of operations:
        1. Close the session with the camera
        2. Release the camera object
        3. Release the camera list
        4. Clear references
        
        Note: We intentionally avoid calling EdsTerminateSDK() as it can cause
        segmentation faults on application exit, particularly on macOS.
        """
        try:
            # First close the session
            if self.session_open and self.camera:
                print("\nClosing session...")
                self.edsdk.EdsCloseSession(self.camera)
                self.session_open = False
            
            # Then release the camera object
            if self.camera:
                print("Releasing camera...")
                self.edsdk.EdsRelease(self.camera)
                self.camera = None
            
            # Then release the camera list
            if self.camera_list:
                print("Releasing camera list...")
                self.edsdk.EdsRelease(self.camera_list)
                self.camera_list = None
            
            # We intentionally avoid calling EdsTerminateSDK() as it can cause
            # segmentation faults, particularly on macOS. Instead, we just
            # clear our reference to the library and let the OS clean up
            # when the process exits.
            print("Cleanup complete")
            # macOS-specific cleanup: restart usbd daemon to clear lingering USB state
            import platform
            if platform.system() == "Darwin":
                try:
                    os.system("killall -HUP usbd")
                    print("macOS cleanup: usbd restarted")
                except Exception as e:
                    print(f"macOS cleanup failed: {e}")
            
        except Exception as e:
            print(f"Cleanup error: {e}")

    def check_system_usb_devices(self):
        """
        Check if any Canon cameras are visible at the OS level using system_profiler
        
        Returns:
            bool: True if a Canon device is found, False otherwise
        """
        try:
            result = subprocess.run(
                ['system_profiler', 'SPUSBDataType'], 
                capture_output=True, 
                text=True
            )
            output = result.stdout
            
            print("\nUSB Device Check:")
            
            # Check for any Canon device
            if 'Canon' in output:
                print("✓ Canon device found in system USB devices")
                # Extract the Canon device details
                lines = output.split('\n')
                for i, line in enumerate(lines):
                    if 'Canon' in line:
                        # Print a few lines around the Canon device for context
                        start = max(0, i-2)
                        end = min(len(lines), i+5)
                        for j in range(start, end):
                            if j < len(lines):
                                print(f"  {lines[j]}")
                return True
            else:
                print("✗ No Canon devices found in system USB devices")
                return False
        except Exception as e:
            print(f"Error checking USB devices: {e}")
            return False

    def run_intensive_event_processing(self, duration=3.0, message="Running event processing..."):
        """
        Run intensive event processing loop for the specified duration
        
        Args:
            duration (float): Duration in seconds to run event processing
            message (str): Message to display while processing
        """
        print(message)
        start_time = time.time()
        count = 0
        while time.time() - start_time < duration:
            self.edsdk.EdsGetEvent()
            count += 1
            time.sleep(0.05)  # Small delay to prevent CPU thrashing
        print(f"✓ Called EdsGetEvent() {count} times over {duration:.1f} seconds")

    def test_camera_connection_sequence(self):
        """Test complete camera connection sequence with enhanced macOS compatibility"""
        
        # Pre-check: Verify camera is visible at OS level
        self.check_system_usb_devices()
        
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

        # Step 3: CRITICAL - Run intensive event processing BEFORE getting camera list
        # This is explicitly mentioned in the documentation for macOS 13+
        self.run_intensive_event_processing(
            duration=3.0,
            message="\nStep 3: Running intensive initial event processing (critical for macOS)..."
        )
        
        # Step 4: Get camera list
        print("\nStep 4: Getting camera list")
        self.camera_list = ctypes.c_void_p()
        err = self.edsdk.EdsGetCameraList(ctypes.byref(self.camera_list))
        self.assertEqual(err, EDS_ERR_OK, f"Failed to get camera list: {err}")
        print("✓ Got camera list")

        # Step 5: Process events AFTER getting camera list
        self.run_intensive_event_processing(
            duration=1.0,
            message="\nStep 5: Processing events after getting camera list..."
        )

        # Step 6: Get camera count with enhanced retry logic
        print("\nStep 6: Getting camera count with enhanced retry logic")
        
        max_retries = 15  # More retries for challenging connections
        count = ctypes.c_uint32()
        camera_found = False
        
        for attempt in range(max_retries):
            # More aggressive event processing (multiple calls)
            for _ in range(10):  # Call EdsGetEvent multiple times
                self.edsdk.EdsGetEvent()
            
            err = self.edsdk.EdsGetChildCount(self.camera_list, ctypes.byref(count))
            self.assertEqual(err, EDS_ERR_OK, f"Failed to get camera count: {err}")
            
            if count.value > 0:
                camera_found = True
                break
                
            print(f"Retry {attempt+1}/{max_retries}: Found {count.value} camera(s)")
            
            # Increasing delay with each attempt with a max cap
            delay = min(5.0, 1.0 + (attempt * 0.5))
            print(f"Waiting {delay:.1f}s before next attempt...")
            time.sleep(delay)
            
            # More aggressive event processing after waiting
            for _ in range(10):  # Call EdsGetEvent multiple times again
                self.edsdk.EdsGetEvent()
        
        print(f"✓ Found {count.value} camera(s)")
        
        # If no cameras were found, check for macOS version issues
        if not camera_found:
            macos_version = platform.mac_ver()[0]
            
            if macos_version.startswith('14.0') or macos_version.startswith('14.1'):
                print("\n⚠️ IMPORTANT: You're running macOS 14.0 or 14.1, which has known EDSDK connection issues.")
                print("   The Canon documentation explicitly states:")
                print("   'In macOS 14.0-14.1, connection failures occur. Please use macOS 14.2 or later.'")
            
            # Gather more diagnostic information
            print("\nDiagnostic information:")
            print("1. Verify your camera is powered on and in shooting mode (not playback)")
            print("2. Check USB connection and cable")
            print("3. Try disconnecting and reconnecting the camera")
            print("4. Check for any macOS permission dialogs that might be hidden")
        
        # Verify at least one camera is connected
        self.assertTrue(camera_found, "No cameras detected after multiple attempts. Please check:\n" +
                       "1. Camera is powered on\n" +
                       "2. Camera is in shooting mode (not playback)\n" +
                       "3. USB connection is set to 'PTP' or 'PC Connect'\n" +
                       "4. USB cable is securely connected\n" +
                       "5. On macOS 13+, try disconnecting and reconnecting the camera\n" +
                       "6. On macOS 14.0-14.1, upgrade to macOS 14.2+ per Canon documentation\n" +
                       "7. Wait a few seconds after connecting before trying again")

        # Step 7: Get camera handle with enhanced retry logic
        print("\nStep 7: Getting camera handle")
        self.camera = ctypes.c_void_p()
        
        # Process events before getting camera handle
        for _ in range(5):
            self.edsdk.EdsGetEvent()
        
        # Retry loop to get the camera handle
        max_handle_retries = 10
        handle_obtained = False
        
        for attempt in range(max_handle_retries):
            # Process events before getting camera handle
            self.edsdk.EdsGetEvent()
            
            err = self.edsdk.EdsGetChildAtIndex(self.camera_list, 0, ctypes.byref(self.camera))
            if err == EDS_ERR_OK:
                handle_obtained = True
                break
                
            print(f"Retry {attempt+1}/{max_handle_retries}: Failed to get camera handle, err: {err}")
            
            # Longer delay between retries
            delay = 0.5 + (attempt * 0.2)
            print(f"Waiting {delay:.1f}s before next attempt...")
            time.sleep(delay)
            
            # Process events after waiting
            self.edsdk.EdsGetEvent()
        
        self.assertTrue(handle_obtained, "Failed to get camera handle after multiple attempts")
        print("✓ Got camera handle")
        
        # Process events after getting camera handle
        for _ in range(5):
            self.edsdk.EdsGetEvent()

        # Step 8: Open session
        print("\nStep 8: Opening session")
        err = self.edsdk.EdsOpenSession(self.camera)
        self.assertEqual(err, EDS_ERR_OK, f"Failed to open session: {err}")
        self.session_open = True
        print("✓ Session opened successfully")

        # Step 9: Configure camera settings
        print("\nStep 9: Configuring camera settings")
        
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
