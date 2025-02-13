"""
Canon Camera Interface Module

This module provides a high-level interface to Canon cameras using the Canon EDSDK.
It handles camera connection, live view setup, and image capture through a clean
pythonic interface while managing EDSDK resources properly.

Key Features:
- Automatic camera detection and connection
- Live view support with proper cleanup
- Resource management via context manager protocol
- Error handling and status reporting
- UI locking for thread-safe operations
- State monitoring and recovery
- Exponential backoff for retries

Example:
    with CanonCamera() as camera:
        camera.start_live_view()
        image = camera.download_evf_image(camera.create_evf_image())
"""

import ctypes
import time
import os
from typing import Optional, Tuple
import random

# EDSDK Constants
EDS_ERR_OK = 0
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsPropID_Evf_Mode = 0x00000501
kEdsEvfOutputDevice_PC = 0x02
kEdsPropID_SaveTo = 0x0000000b
kEdsSaveTo_Host = 1
kEdsCameraCommand_TakePicture = 0x00000000
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_DriveLensEvf = 0x00000103
kEdsCameraCommand_DoEvfAf = 0x00000102
kEdsCameraCommand_PressShutterButton = 0x00000004
kEdsCameraCommand_UILock = 0x00000000
kEdsCameraCommand_UIUnLock = 0x00000001

# Error codes
kEdsErr_DeviceBusy = 129
kEdsErr_DeviceNotFound = 2
kEdsErr_DeviceInvalid = 3
kEdsErr_SessionNotOpen = 8
kEdsErr_InvalidParameter = 6
kEdsErr_MemoryFull = 7
kEdsErr_CommunicationError = 41
kEdsErr_BatteryLow = 49
kEdsErr_NotReady = 41
kEdsErr_UnsupportedCommand = 36110  # Error when command not supported in current state

# Camera reference type
EdsCameraRef = ctypes.c_void_p 

class CameraError(Exception):
    """Custom exception for camera-related errors with recovery hints."""
    def __init__(self, message: str, error_code: int, recovery_hint: str = None):
        self.error_code = error_code
        self.recovery_hint = recovery_hint
        super().__init__(f"{message} (Error: {error_code})" + 
                        (f"\nRecovery hint: {recovery_hint}" if recovery_hint else ""))

class CanonCamera:
    """
    A high-level interface to Canon cameras using the EDSDK.
    
    This class provides a pythonic interface to Canon cameras, handling all the 
    low-level EDSDK calls and resource management. It implements the context
    manager protocol for safe resource cleanup.
    
    Usage:
        with CanonCamera() as camera:
            camera.start_live_view()
            # Work with camera...
    
    The camera will be automatically disconnected and resources cleaned up when
    exiting the context manager block.
    """
    def __init__(self):
        self.edsdk = None
        self.camera = None
        self.ui_locked = False
        self.live_view_active = False
        self.session_open = False
        self._load_edsdk()
        self._initialize_sdk()

    def _load_edsdk(self):
        """
        Load the Canon EDSDK library.
        
        Raises:
            RuntimeError: If the EDSDK library cannot be loaded
        """
        try:
            print("Attempting to load EDSDK from:", os.path.abspath("./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"))
            self.edsdk = ctypes.CDLL("./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK")
            print("Successfully loaded EDSDK")
        except Exception as e:
            print("Error loading EDSDK:", str(e))
            print("Current working directory:", os.getcwd())
            raise RuntimeError(f"Failed to load EDSDK library: {e}")

    def _initialize_sdk(self):
        """
        Initialize the EDSDK library.
        
        This must be called before any other EDSDK operations.
        
        Raises:
            RuntimeError: If SDK initialization fails
        """
        if not self.edsdk:
            raise RuntimeError("EDSDK not loaded")
        
        err = self.edsdk.EdsInitializeSDK()
        if err != EDS_ERR_OK:
            raise RuntimeError(f"Failed to initialize SDK: {err}")

    def _get_first_camera(self) -> EdsCameraRef:
        """Get the first connected camera"""
        camera_list = ctypes.c_void_p()
        camera = ctypes.c_void_p()
        
        print("Attempting to get camera list...")
        err = self.edsdk.EdsGetCameraList(ctypes.byref(camera_list))
        if err != EDS_ERR_OK:
            raise CameraError("Failed to get camera list", err,
                            "Check USB connection and camera power")

        count = ctypes.c_uint32()
        err = self.edsdk.EdsGetChildCount(camera_list, ctypes.byref(count))
        if err != EDS_ERR_OK:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("Failed to get camera count", err,
                            "Camera enumeration failed")
        
        print(f"Found {count.value} camera(s)")
        
        if count.value == 0:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("No cameras detected", kEdsErr_DeviceNotFound,
                            "Please check:\n" +
                            "1. Camera is powered on\n" +
                            "2. Camera is in shooting mode (not playback)\n" +
                            "3. USB connection setting on camera is set to 'PTP' or 'PC Connect'\n" +
                            "4. USB cable is securely connected\n" +
                            "5. If using USB hub, try connecting directly to computer\n" +
                            "6. Try disconnecting USB, waiting 10 seconds, then reconnecting\n" +
                            "7. Check camera menu settings for USB connection mode")

        print("Attempting to get camera handle...")
        err = self.edsdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera))
        if err != EDS_ERR_OK:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("Failed to get camera handle", err,
                            "Camera connection failed")

        self.edsdk.EdsRelease(camera_list)
        return camera

    def _retry_with_backoff(self, operation, max_attempts=5, initial_delay=0.1):
        """
        Execute an operation with exponential backoff retry logic.
        
        Args:
            operation: Function to execute
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay between retries in seconds
            
        Returns:
            Tuple[bool, Any]: Success status and operation result
            
        The delay between retries increases exponentially with some random jitter
        to prevent thundering herd problems.
        """
        delay = initial_delay
        for attempt in range(max_attempts):
            try:
                result = operation()
                return True, result
            except Exception as e:
                if attempt == max_attempts - 1:  # Last attempt
                    return False, e
                if isinstance(e, CameraError) and e.error_code != kEdsErr_DeviceBusy:
                    return False, e
                
                # Add random jitter to prevent synchronized retries
                jitter = random.uniform(0, 0.1)
                sleep_time = delay + jitter
                print(f"Retry {attempt + 1}/{max_attempts} after {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                delay *= 2  # Exponential backoff

    def _process_events(self):
        """Process any pending camera events"""
        err = self.edsdk.EdsGetEvent()
        if err != EDS_ERR_OK:
            print(f"Warning: Failed to process events: {err}")

    def _lock_ui(self, timeout=2.0) -> bool:
        """
        Attempt to lock camera UI, but proceed if not supported.
        
        Args:
            timeout: Maximum time to wait for lock in seconds
            
        Returns:
            bool: Always returns True since we proceed even without lock
        """
        if self.ui_locked:
            return True
        
        # Some camera models don't require UI lock for live view
        # So we'll try to lock but continue even if it fails
        print("Checking if UI lock is supported...")
            
        # For other errors, try with retries and event processing
        def lock_operation():
            self._process_events()  # Process events before each attempt
            err = self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_UILock, 0)
            if err != EDS_ERR_OK:
                if err == kEdsErr_DeviceBusy:
                    print("Camera UI is busy")
                elif err == kEdsErr_DeviceInvalid:
                    print("Camera is not responding")
                elif err == kEdsErr_UnsupportedCommand:
                    print("UI lock not supported - proceeding")
                    return True
                elif err == kEdsErr_NotReady:
                    print("Camera not ready for UI lock")
                else:
                    print(f"UI lock error: {err}")
                raise CameraError("Failed to lock UI", err)
            time.sleep(0.3)  # Allow lock to take effect
            return True
            
        # Try multiple times with increasing delays
        success, result = self._retry_with_backoff(
            lock_operation,
            max_attempts=5,  # Increased attempts
            initial_delay=0.5
        )
        
        if success:
            if isinstance(result, bool) and result:
                print("Successfully locked camera UI")
                self.ui_locked = True
                return True
        
        print("Failed to lock camera UI - proceeding without lock")
        return True  # Continue without UI lock since some models don't require it

    def _unlock_ui(self):
        """Unlock camera UI"""
        if not self.ui_locked:
            return
            
        # Process events before unlocking
        for _ in range(2):
            self._process_events()
            time.sleep(0.1)
            
        err = self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_UIUnLock, 0)
        if err != EDS_ERR_OK:
            if err == kEdsErr_UnsupportedCommand:
                print("UI unlock not supported - ignoring")
            else:
                print(f"Warning: Failed to unlock UI: {err}")
        self.ui_locked = False
        time.sleep(0.2)  # Allow unlock to take effect

    def connect(self):
        """
        Connect to the first available Canon camera.
        
        This method:
        1. Gets a handle to the first connected camera
        2. Opens a session with the camera
        3. Configures basic camera settings (save location, etc.)
        
        Raises:
            CameraError: If connection fails with specific error details
        """
        if self.camera:
            return
        
        self.camera = self._get_first_camera()
        
        def open_session():
            err = self.edsdk.EdsOpenSession(self.camera)
            if err != EDS_ERR_OK:
                raise CameraError("Failed to open session", err,
                                "Check camera connection and power")
            return True
            
        success, result = self._retry_with_backoff(open_session)
        if not success:
            raise result
            
        self.session_open = True
            
        # Keep camera awake
        err = self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_ExtendShutDownTimer, 0)
        if err != EDS_ERR_OK:
            print("Warning: Failed to extend shutdown timer")
            
        # Set save location to host (PC)
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
            
        print("Successfully connected to camera!")

    def disconnect(self):
        """
        Disconnect from the camera and clean up resources.
        
        This releases all EDSDK resources and terminates the SDK properly.
        """
        if self.live_view_active:
            try:
                self.stop_live_view()
            except:
                pass
                
        if self.ui_locked:
            try:
                self._unlock_ui()
            except:
                pass
                
        if self.camera:
            if self.session_open:
                print("Closing session...")
                self.edsdk.EdsCloseSession(self.camera)
                self.session_open = False
            self.edsdk.EdsRelease(self.camera)
            self.camera = None
        
        if self.edsdk:
            print("Terminating SDK...")
            self.edsdk.EdsTerminateSDK()
            self.edsdk = None

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def start_live_view(self) -> bool:
        """
        Start live view on the camera.
        
        This method:
        1. Checks current EVF state
        2. Enables EVF mode if needed
        3. Sets PC as output device
        4. Verifies live view is active
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.camera:
            raise CameraError("Camera not connected", kEdsErr_DeviceInvalid,
                            "Connect to camera first")

        print("Starting live view sequence...")
        
        try:
            # First check if live view is already active
            if self.live_view_active:
                print("Live view already active")
                return True
                
            # Clear any pending events
            for _ in range(3):
                self._process_events()
                time.sleep(0.1)
            
            # Step 1: Get current EVF mode
            evf_mode = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(
                self.camera,
                kEdsPropID_Evf_Mode,
                0,
                ctypes.sizeof(evf_mode),
                ctypes.byref(evf_mode)
            )
            if err == EDS_ERR_OK:
                print(f"Current EVF mode: {evf_mode.value}")
            else:
                print(f"Warning: Could not get EVF mode (error {err})")
            
            # Step 2: Enable EVF mode if not already enabled
            if evf_mode.value != 1:
                print("Enabling EVF mode...")
                evf_mode = ctypes.c_uint32(1)
                for attempt in range(3):
                    err = self.edsdk.EdsSetPropertyData(
                        self.camera,
                        kEdsPropID_Evf_Mode,
                        0,
                        ctypes.sizeof(evf_mode),
                        ctypes.byref(evf_mode)
                    )
                    if err == EDS_ERR_OK:
                        print("EVF mode enabled successfully")
                        break
                    if err == kEdsErr_DeviceBusy:
                        print(f"Camera busy, retrying... (attempt {attempt + 1}/3)")
                        time.sleep(0.5)  # Longer delay between retries
                        continue
                    print(f"Failed to enable EVF mode: {err}")
                    return False
                    
                # Wait for EVF mode to stabilize
                time.sleep(0.5)
            
            # Step 3: Get current output device
            device = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(
                self.camera,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device)
            )
            if err == EDS_ERR_OK:
                print(f"Current output device: {device.value}")
            else:
                print(f"Warning: Could not get output device (error {err})")
            
            # Step 4: Set PC as output device if not already set
            if not (device.value & kEdsEvfOutputDevice_PC):
                print("Setting PC as output device...")
                device = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
                for attempt in range(3):
                    err = self.edsdk.EdsSetPropertyData(
                        self.camera,
                        kEdsPropID_Evf_OutputDevice,
                        0,
                        ctypes.sizeof(device),
                        ctypes.byref(device)
                    )
                    if err == EDS_ERR_OK:
                        print("Output device set successfully")
                        break
                    if err == kEdsErr_DeviceBusy:
                        print(f"Camera busy, retrying... (attempt {attempt + 1}/3)")
                        time.sleep(0.5)
                        continue
                    print(f"Failed to set output device: {err}")
                    return False
                    
                # Wait for output device change to stabilize
                time.sleep(0.5)
            # Step 5: Verify live view is active by checking output device again
            device = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(
                self.camera,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device)
            )
            if err == EDS_ERR_OK and (device.value & kEdsEvfOutputDevice_PC):
                print("Verified live view is active")
                self.live_view_active = True
                return True
            else:
                print("Failed to verify live view state")
                return False

        except Exception as e:
            print(f"Error during live view start: {e}")
            return False

    def stop_live_view(self) -> bool:
        """
        Stop live view and restore camera settings.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.live_view_active:
            return True
            
        try:
            # Get current output device
            device = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(
                self.camera,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device)
            )
            if err != EDS_ERR_OK:
                if err == kEdsErr_DeviceBusy:
                    time.sleep(0.1)  # Brief delay if device is busy
                    return self.stop_live_view()  # Retry once
                return False

            # Remove PC from output device
            device = ctypes.c_uint32(device.value & ~kEdsEvfOutputDevice_PC)
            err = self.edsdk.EdsSetPropertyData(
                self.camera,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device)
            )
            if err != EDS_ERR_OK:
                if err == kEdsErr_DeviceBusy:
                    time.sleep(0.1)  # Brief delay if device is busy
                    return self.stop_live_view()  # Retry once
                return False
                
            self.live_view_active = False
            return True
            
        except Exception as e:
            print(f"Error stopping live view: {e}")
            return False

    def create_evf_image(self):
        """
        Create an EVF (Electronic ViewFinder) image reference.
            ctypes.c_void_p: Memory stream reference
            
        Raises:
            CameraError: If memory stream creation fails
        """
        evf_image = ctypes.c_void_p()
        err = self.edsdk.EdsCreateMemoryStream(0, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            raise CameraError("Failed to create memory stream", err,
                            "Memory allocation failed")
        return evf_image

    def download_evf_image(self, stream) -> Optional[bytes]:
        """
        Download the current live view image data.
        
        This downloads the current EVF frame from the camera into a memory stream,
        following the official EDSDK sample implementation.
        
        Args:
            stream: Memory stream reference from create_evf_image()
            
        Returns:
            Optional[bytes]: Raw image data that can be decoded by OpenCV,
                           or None if download fails
        """
        if not self.camera or not stream:
            print("Camera or stream not available")
            return None

        if not self.live_view_active:
            print("Live view is not active")
            return None

        # Process events and wait for camera to be ready
        for _ in range(3):
            self._process_events()
            time.sleep(0.1)

        # Create EvfImageRef
        evf_image = ctypes.c_void_p()
        err = self.edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            print(f"Failed to create EVF image reference: {err}")
            if err == kEdsErr_DeviceInvalid:
                print("Camera connection lost")
                self.live_view_active = False
            elif err == kEdsErr_NotReady:
                print("Camera not ready for live view")
            elif err == kEdsErr_UnsupportedCommand:
                print("Live view not supported in current state")
            return None

        try:
            def download_frame():
                # Process events before each download attempt
                self._process_events()
                
                err = self.edsdk.EdsDownloadEvfImage(self.camera, evf_image)
                if err != EDS_ERR_OK:
                    if err == kEdsErr_DeviceBusy:
                        print("Camera is busy - retrying...")
                    elif err == kEdsErr_DeviceInvalid:
                        print("Camera connection lost")
                        self.live_view_active = False
                    elif err == kEdsErr_NotReady:
                        print("Camera not ready - waiting for next frame")
                    elif err == kEdsErr_UnsupportedCommand:
                        print("Live view command not supported in current state")
                    else:
                        print(f"Download error: {err}")
                    raise CameraError("Failed to download EVF image", err)
                return True
                
            success, result = self._retry_with_backoff(
                download_frame,
                max_attempts=5,  # Increased attempts
                initial_delay=0.2  # Increased initial delay
            )
            
            if not success:
                if isinstance(result, CameraError):
                    if result.error_code == kEdsErr_DeviceInvalid:
                        self.live_view_active = False
                    elif result.error_code == kEdsErr_NotReady:
                        # Not ready means no new frame yet, which is normal
                        return None
                    elif result.error_code == kEdsErr_UnsupportedCommand:
                        print("Live view not supported in current camera state")
                        self.live_view_active = False
                return None

            # Process events before getting image data
            self._process_events()

            # Get the image data
            image_data = ctypes.c_void_p()
            err = self.edsdk.EdsGetPointer(stream, ctypes.byref(image_data))
            if err != EDS_ERR_OK:
                print(f"Failed to get image pointer: {err}")
                if err == kEdsErr_DeviceInvalid:
                    self.live_view_active = False
                elif err == kEdsErr_NotReady:
                    print("Camera not ready to transfer image data")
                return None

            # Get data length
            image_len = ctypes.c_ulonglong()
            err = self.edsdk.EdsGetLength(stream, ctypes.byref(image_len))
            if err != EDS_ERR_OK:
                print(f"Failed to get image length: {err}")
                if err == kEdsErr_DeviceInvalid:
                    self.live_view_active = False
                elif err == kEdsErr_NotReady:
                    print("Camera not ready to get image length")
                return None

            # Copy the image data
            try:
                buffer = (ctypes.c_ubyte * image_len.value).from_address(image_data.value)
                return bytes(buffer)
            except Exception as e:
                print(f"Error copying image data: {e}")
                return None

        finally:
            if evf_image:
                try:
                    self.edsdk.EdsRelease(evf_image)
                except:
                    pass

    def release_evf_image(self, evf_image):
        """
        Release EVF image resources.
        
        Args:
            evf_image: EVF image reference to release
        """
        if evf_image:
            self.edsdk.EdsRelease(evf_image)
