"""
Canon Camera Interface Module

This module provides a high-level interface to Canon cameras using the Canon EDSDK.
It handles camera connection, live view setup, and image capture through a clean
pythonic interface while managing EDSDK resources properly.
"""

import ctypes
import time
import os
from typing import Optional, Tuple
import random
from dataclasses import dataclass
from contextlib import contextmanager

# EDSDK Constants and Error Codes
# EVF Related
kEdsPropID_Evf_Mode = 0x00000501
kEdsPropID_Evf_OutputDevice = 0x00000500
kEdsPropID_Evf_DepthOfFieldPreview = 0x00000503
kEdsPropID_Evf_AFMode = 0x00000504
kEdsPropID_Evf_ZoomPosition = 0x00000507
kEdsPropID_Evf_HistogramStatus = 0x0000050B
kEdsPropID_TempStatus = 0x01000003
kEdsPropID_BatteryLevel = 0x00000008
kEdsPropID_Record = 0x00000510

# Device States
EDS_ERR_OK = 0
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
kEdsErr_StreamInternalError = 97  # Stream I/O error
kEdsErr_ObjectNotReady = 41  # Object is not ready
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

# EVF Recovery Delays (in seconds)
RECOVERY_DELAY_SHORT = 0.1   # For quick retries (not ready)
RECOVERY_DELAY_MEDIUM = 0.2  # For busy states
RECOVERY_DELAY_LONG = 0.5    # For serious errors

# Camera reference type
EdsCameraRef = ctypes.c_void_p 

@dataclass
class CameraStatus:
    """Comprehensive camera status information."""
    mode: int = 0                    # EVF mode
    output_device: int = 0           # Current output device
    histogram_status: int = 0        # Histogram display status
    temperature_status: int = 0      # Temperature warning level
    zoom_position: int = 0           # Current zoom level
    stream_position: int = 0         # Current stream position
    stream_length: int = 0           # Stream buffer length
    battery_level: int = 0           # Battery percentage (0-100)
    record_status: int = 0           # Recording status
    time_since_last_frame: float = 0 # Time since last frame received
    frames_captured: int = 0         # Total frames captured
    errors_since_start: int = 0      # Error count since streaming started
    last_error: str = ""            # Last error message

class StreamError(Exception):
    """Custom exception for streaming-related errors."""
    def __init__(self, message: str, error_code: int, can_retry: bool = True, recovery_delay: float = RECOVERY_DELAY_SHORT):
        self.error_code = error_code
        self.can_retry = can_retry
        self.recovery_delay = recovery_delay
        super().__init__(message)

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
    """
    def __init__(self):
        self.edsdk = None
        self.camera = None
        self.ui_locked = False
        self.live_view_active = False
        self.session_open = False
        self.status = CameraStatus()
        self.last_frame_time = 0
        self._load_edsdk()
        self._initialize_sdk()
        self._event_handlers_set = False

    def _load_edsdk(self):
        """Load the Canon EDSDK library."""
        try:
            print("Attempting to load EDSDK from:", os.path.abspath("./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"))
            self.edsdk = ctypes.CDLL("./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK")
            print("Successfully loaded EDSDK")
        except Exception as e:
            print("Error loading EDSDK:", str(e))
            print("Current working directory:", os.getcwd())
            raise RuntimeError(f"Failed to load EDSDK library: {e}")

    def _initialize_sdk(self):
        """Initialize the EDSDK library."""
        if not self.edsdk:
            raise RuntimeError("EDSDK not loaded")
        
        err = self.edsdk.EdsInitializeSDK()
        if err != EDS_ERR_OK:
            raise RuntimeError(f"Failed to initialize SDK: {err}")
            
    def _get_first_camera(self):
        """Get the first connected camera with retries."""
        camera_list = ctypes.c_void_p()
        camera = ctypes.c_void_p()
        
        print("Attempting to get camera list...")
        err = self.edsdk.EdsGetCameraList(ctypes.byref(camera_list))
        if err != EDS_ERR_OK:
            raise CameraError("Failed to get camera list", err,
                              "Check USB connection and camera power")
    
        # Retry loop to allow the list to update
        max_retries = 3
        count = ctypes.c_uint32(0)
        for attempt in range(max_retries):
            err = self.edsdk.EdsGetChildCount(camera_list, ctypes.byref(count))
            if err == EDS_ERR_OK and count.value > 0:
                break
            print(f"Retry {attempt+1}/{max_retries}: Found {count.value} camera(s), err: {err}")
            time.sleep(0.5)
    
        if count.value == 0:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("No cameras detected", kEdsErr_DeviceNotFound,
                              "Please check:\n"
                              "1. Camera is powered on\n"
                              "2. Camera is in shooting mode (not playback)\n"
                              "3. USB connection is set to 'PTP' or 'PC Connect'\n"
                              "4. USB cable is securely connected\n"
                              "5. Consider a brief delay before reconnecting")
    
        print(f"Found {count.value} camera(s)")
    
        # Retry loop to get the camera handle
        max_handle_retries = 3
        for attempt in range(max_handle_retries):
            err = self.edsdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera))
            if err == EDS_ERR_OK:
                break
            print(f"Retry {attempt+1}/{max_handle_retries}: Failed to get camera handle, err: {err}")
            time.sleep(0.5)
    
        if err != EDS_ERR_OK:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("Failed to get camera handle", err,
                              "Camera connection failed")
    
        try:
            self.edsdk.EdsRelease(camera_list)
        except:
            pass
    
        return camera

    def connect(self):
        """Connect to the first available Canon camera."""
        if self.camera:
            return
            
        try:
            # Get camera first
            camera = self._get_first_camera()
            
            # Then try to open session
            err = self.edsdk.EdsOpenSession(camera)
            if err != EDS_ERR_OK:
                if camera:
                    self.edsdk.EdsRelease(camera)
                raise CameraError("Failed to open session", err)
                
            # Only set camera after successful connection
            self.camera = camera
            self.session_open = True
            
            # Configure camera settings
            self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_ExtendShutDownTimer, 0)
            
            save_to = ctypes.c_uint32(kEdsSaveTo_Host)
            self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_SaveTo, 0,
                                        ctypes.sizeof(save_to), ctypes.byref(save_to))
                                        
            print("Successfully connected to camera!")
            
        except Exception as e:
            if not self.camera and camera:
                try:
                    self.edsdk.EdsRelease(camera)
                except:
                    pass
            raise e

    def _verify_camera_ready(self):
        """Verify camera is in a ready state."""
        if not self.camera:
            raise CameraError("Camera not connected", kEdsErr_DeviceInvalid)
            
        if not self.session_open:
            raise CameraError("Camera session not open", kEdsErr_SessionNotOpen)
            
        self._process_events()

    def _verify_live_view_state(self) -> bool:
        """Verify live view is properly configured."""
        status = self.get_status()
        
        if status.mode != 1:
            print(f"Warning: Unexpected EVF mode: {status.mode}")
            return False
            
        if not (status.output_device & kEdsEvfOutputDevice_PC):
            print(f"Warning: PC not set as output device: {status.output_device}")
            return False
            
        return True

    def _setup_event_handlers(self):
        """Set up camera event handlers."""
        if not self.camera or self._event_handlers_set:
            return

        try:
            # Property event handler
            @ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)
            def property_event_callback(event, property_id, param, context):
                try:
                    self._handle_property_event(property_id, param)
                except Exception as e:
                    print(f"Property event error: {e}")
                return EDS_ERR_OK

            # Object event handler
            @ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
            def object_event_callback(event, object_event, context):
                try:
                    self._handle_object_event(object_event)
                except Exception as e:
                    print(f"Object event error: {e}")
                return EDS_ERR_OK

            # State event handler
            @ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)
            def state_event_callback(event, state_event, param, context):
                try:
                    self._handle_state_event(state_event, param)
                except Exception as e:
                    print(f"State event error: {e}")
                return EDS_ERR_OK

            # Keep references to prevent garbage collection
            self._property_callback = property_event_callback
            self._object_callback = object_event_callback
            self._state_callback = state_event_callback

            # Set handlers
            err = self.edsdk.EdsSetPropertyEventHandler(
                self.camera,
                0x00000100,  # kEdsPropertyEvent_All
                self._property_callback,
                None
            )
            if err != EDS_ERR_OK:
                print(f"Warning: Failed to set property event handler: {err}")

            err = self.edsdk.EdsSetObjectEventHandler(
                self.camera,
                0x00000200,  # kEdsObjectEvent_All
                self._object_callback,
                None
            )
            if err != EDS_ERR_OK:
                print(f"Warning: Failed to set object event handler: {err}")

            err = self.edsdk.EdsSetCameraStateEventHandler(
                self.camera,
                0x00000300,  # kEdsStateEvent_All
                self._state_callback,
                None
            )
            if err != EDS_ERR_OK:
                print(f"Warning: Failed to set state event handler: {err}")

            self._event_handlers_set = True
            print("Successfully set up event handlers")

        except Exception as e:
            print(f"Error setting up event handlers: {e}")

    def _handle_property_event(self, property_id: int, param: int):
        """Handle property change events."""
        print(f"Property event - ID: {property_id:#x}, Param: {param:#x}")
        # Update status based on property changes
        self.get_status()

    def _handle_object_event(self, object_event: int):
        """Handle object events."""
        print(f"Object event: {object_event:#x}")

    def _handle_state_event(self, state_event: int, param: int):
        """Handle camera state events."""
        print(f"State event - Event: {state_event:#x}, Param: {param:#x}")
        if state_event == 0x00000514:  # kEdsStateEvent_Shutdown
            print("Camera shutdown detected")
            self.disconnect()

    def _process_events(self):
        """Process any pending camera events."""
        if not self.edsdk or not self.camera:
            return
            
        try:
            err = self.edsdk.EdsGetEvent()
            if err != EDS_ERR_OK:
                print(f"Warning: Failed to process events: {err}")
        except Exception as e:
            print(f"Error processing events: {e}")

    def _retry_with_backoff(self, operation, max_attempts=3, initial_delay=0.1):
        """Execute operation with exponential backoff retry logic."""
        delay = initial_delay
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                result = operation()
                return True, result
            except Exception as e:
                last_error = e
                if attempt == max_attempts - 1:
                    break
                    
                # Use error-specific delay if available
                if isinstance(e, StreamError):
                    delay = e.recovery_delay
                
                jitter = random.uniform(0, 0.1)
                sleep_time = delay + jitter
                print(f"Retry {attempt + 1}/{max_attempts} after {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                delay *= 2
                
                self.status.errors_since_start += 1
                self.status.last_error = str(e)
                
        return False, last_error

    def get_status(self) -> CameraStatus:
        """Get comprehensive camera status."""
        if not self.camera:
            return self.status
            
        try:
            # Update frame timing
            now = time.time()
            self.status.time_since_last_frame = now - self.last_frame_time
            
            # Get EVF mode
            evf_mode = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Evf_Mode,
                                              0, ctypes.sizeof(evf_mode),
                                              ctypes.byref(evf_mode))
            if err == EDS_ERR_OK:
                self.status.mode = evf_mode.value
                
            # Get output device
            device = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice,
                                              0, ctypes.sizeof(device),
                                              ctypes.byref(device))
            if err == EDS_ERR_OK:
                self.status.output_device = device.value
                
            # Get histogram status
            hist = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Evf_HistogramStatus,
                                              0, ctypes.sizeof(hist),
                                              ctypes.byref(hist))
            if err == EDS_ERR_OK:
                self.status.histogram_status = hist.value
                
            # Get temperature status
            temp = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_TempStatus,
                                              0, ctypes.sizeof(temp),
                                              ctypes.byref(temp))
            if err == EDS_ERR_OK:
                self.status.temperature_status = temp.value
                
            # Get battery level
            battery = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_BatteryLevel,
                                              0, ctypes.sizeof(battery),
                                              ctypes.byref(battery))
            if err == EDS_ERR_OK:
                self.status.battery_level = battery.value
                
            # Get recording status
            record = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Record,
                                              0, ctypes.sizeof(record),
                                              ctypes.byref(record))
            if err == EDS_ERR_OK:
                self.status.record_status = record.value
                
        except Exception as e:
            print(f"Warning: Error getting camera status: {e}")
            self.status.errors_since_start += 1
            self.status.last_error = str(e)
            
        return self.status

    def start_live_view(self) -> bool:
        """
        Start live view on the camera.
        
        Follows the exact sequence from EDSDK documentation:
        1. Get current EVF mode
        2. Enable EVF mode if needed
        3. Get current output device
        4. Set PC as output device if needed
        
        Returns:
            bool: True if successful, False otherwise
        """
        self._verify_camera_ready()
        
        try:
            print("Starting live view sequence...")
            
            # First check if live view is already active
            if self.live_view_active:
                if self._verify_live_view_state():
                    print("Live view already active")
                    return True
                self.live_view_active = False
            
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
                        self._process_events()  # Process events before retry
                        time.sleep(0.5)  # Longer delay between retries
                        continue
                    print(f"Failed to enable EVF mode: {err}")
                    return False
                    
                # Wait for EVF mode to stabilize
                time.sleep(0.5)
                self._process_events()
            
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
                        self._process_events()  # Process events before retry
                        time.sleep(0.5)
                        continue
                    print(f"Failed to set output device: {err}")
                    return False
                    
                # Wait for output device change to stabilize
                time.sleep(0.5)
                self._process_events()
            
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
            device = ctypes.c_uint32(0)  # Clear all output devices
            err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice,
                                              0, ctypes.sizeof(device),
                                              ctypes.byref(device))
            if err != EDS_ERR_OK:
                if err == kEdsErr_DeviceBusy:
                    time.sleep(RECOVERY_DELAY_SHORT)
                    return self.stop_live_view()
                return False
                
            self.live_view_active = False
            return True
            
        except Exception as e:
            print(f"Error stopping live view: {e}")
            self.live_view_active = False  # Force state update even on error
            return False

    @contextmanager
    def evf_image_context(self):
        """Context manager for EVF image resources."""
        stream = None
        evf_image = None
        
        try:
            stream = ctypes.c_void_p()
            err = self.edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
            if err != EDS_ERR_OK:
                raise StreamError("Failed to create memory stream", err)

            evf_image = ctypes.c_void_p()
            err = self.edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
            if err != EDS_ERR_OK:
                raise StreamError("Failed to create EVF image", err)

            yield (stream, evf_image)

        finally:
            if evf_image and self.edsdk:
                try:
                    self.edsdk.EdsRelease(evf_image)
                except:
                    pass
            if stream and self.edsdk:
                try:
                    self.edsdk.EdsRelease(stream)
                except:
                    pass

    def download_evf_image(self, stream) -> Optional[bytes]:
        """Download the current live view image data."""
        if not self.camera or not stream:
            return None

        if not self.live_view_active:
            return None

        status = self.get_status()
        if not self._verify_live_view_state():
            print("EVF state invalid - attempting recovery")
            if not self.start_live_view():
                return None
        
        with self.evf_image_context() as (mem_stream, evf_image):
            try:
                def download_frame():
                    self._process_events()
                    err = self.edsdk.EdsDownloadEvfImage(self.camera, evf_image)
                    if err != EDS_ERR_OK:
                        if err == kEdsErr_ObjectNotReady:
                            raise StreamError(
                                "Camera not ready - waiting for next frame",
                                err,
                                recovery_delay=RECOVERY_DELAY_SHORT
                            )
                        elif err == kEdsErr_StreamInternalError:
                            raise StreamError(
                                "Stream I/O error - attempting recovery",
                                err,
                                recovery_delay=RECOVERY_DELAY_MEDIUM
                            )
                        elif err == kEdsErr_DeviceBusy:
                            raise StreamError(
                                "Camera busy - retrying",
                                err,
                                recovery_delay=RECOVERY_DELAY_MEDIUM
                            )
                        else:
                            print(f"Download error: {err}")
                            if err == kEdsErr_DeviceInvalid:
                                self.live_view_active = False
                                raise StreamError(
                                    "Camera connection lost",
                                    err,
                                    can_retry=False
                                )
                        raise StreamError("Failed to download EVF image", err)
                    return True

                success, result = self._retry_with_backoff(
                    download_frame,
                    max_attempts=3,
                    initial_delay=RECOVERY_DELAY_SHORT
                )

                if not success:
                    if isinstance(result, StreamError) and not result.can_retry:
                        self.live_view_active = False
                    return None

                # Get the image data
                image_data = ctypes.c_void_p()
                length = ctypes.c_ulonglong()
                
                err = self.edsdk.EdsGetLength(mem_stream, ctypes.byref(length))
                if err != EDS_ERR_OK:
                    return None
                    
                err = self.edsdk.EdsGetPointer(mem_stream, ctypes.byref(image_data))
                if err != EDS_ERR_OK:
                    return None

                try:
                    buffer = (ctypes.c_ubyte * length.value).from_address(image_data.value)
                    # Update status on successful frame
                    self.last_frame_time = time.time()
                    self.status.frames_captured += 1
                    return bytes(buffer)
                except Exception as e:
                    print(f"Error copying image data: {e}")
                    self.status.errors_since_start += 1
                    self.status.last_error = str(e)
                    return None

            except Exception as e:
                print(f"Error during EVF download: {e}")
                self.status.errors_since_start += 1
                self.status.last_error = str(e)
                return None

    def disconnect(self):
        """Disconnect from the camera and clean up resources."""
        if self.live_view_active:
            try:
                self.stop_live_view()
            except Exception as e:
                print(f"Warning: Error stopping live view: {e}")
                
        if self.ui_locked:
            try:
                self._unlock_ui()
            except Exception as e:
                print(f"Warning: Error unlocking UI: {e}")
                
        if self.camera:
            if self.session_open:
                try:
                    print("Closing session...")
                    self.edsdk.EdsCloseSession(self.camera)
                except Exception as e:
                    print(f"Warning: Error closing session: {e}")
                self.session_open = False
                
            try:
                print("Releasing camera...")
                self.edsdk.EdsRelease(self.camera)
            except Exception as e:
                print(f"Warning: Error releasing camera: {e}")
            self.camera = None
        
        if self.edsdk:
            try:
                print("Terminating SDK...")
                self.edsdk.EdsTerminateSDK()
            except Exception as e:
                print(f"Warning: Error terminating SDK: {e}")
            self.edsdk = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def release_evf_image(self, evf_image):
        """Release EVF image resources."""
        if evf_image and self.edsdk:
            try:
                self.edsdk.EdsRelease(evf_image)
            except Exception as e:
                print(f"Error releasing EVF image: {e}")
