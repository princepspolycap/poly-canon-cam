"""
Canon Camera Interface Module - Refactored

This module has been refactored into two classes to separate concerns for a cleaner design:

1. CanonCameraConnection: Handles loading the EDSDK, initializing the SDK, connecting to a camera,
   performing the necessary warmup and low-level macOS cleanup, and disconnecting/resetting the connection.
2. CanonCameraController: Built on top of an active CanonCameraConnection, this class controls live view,
   event processing, image downloading, and overall camera operation.

Enhancements from previous versions remain:
- A _warmup() method to settle the EDSDK's internal event loop.
- Enhanced retry logic and macOS compatibility.
- Low-level macOS cleanup via a system call to restart the usbd daemon.

Usage Example:
    conn = CanonCameraConnection()
    conn.connect()
    controller = CanonCameraController(conn)
    if controller.start_live_view():
        image_bytes = controller.download_evf_image()
    controller.stop_live_view()
    conn.disconnect()
    conn.reset()
"""

import ctypes
import time
import os
import random
from typing import Optional
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

# Error Codes
kEdsErr_StreamInternalError = 97      # Stream I/O error
kEdsErr_ObjectNotReady = 41           # Object is not ready
kEdsErr_DeviceBusy = 129
kEdsErr_DeviceNotFound = 2
kEdsErr_DeviceInvalid = 3
kEdsErr_SessionNotOpen = 8
kEdsErr_InvalidParameter = 6
kEdsErr_MemoryFull = 7
kEdsErr_CommunicationError = 41
kEdsErr_BatteryLow = 49
kEdsErr_NotReady = 41
kEdsErr_UnsupportedCommand = 36110  # Command not supported

# EVF Recovery Delays (seconds)
RECOVERY_DELAY_SHORT = 0.1
RECOVERY_DELAY_MEDIUM = 0.2
RECOVERY_DELAY_LONG = 0.5

# Camera reference type
EdsCameraRef = ctypes.c_void_p

@dataclass
class CameraStatus:
    """Holds comprehensive status information for a camera."""
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
    def __init__(self, message: str, error_code: int, can_retry: bool = True,
                 recovery_delay: float = RECOVERY_DELAY_SHORT):
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

class CanonCameraConnection:
    """
    Handles establishment of a connection with the Canon camera using the EDSDK.
    Responsibilities include:
     - Loading the EDSDK and initializing it.
     - Warming up the internal event loop.
     - Retrieving the camera list and selecting a camera.
     - Opening/closing sessions.
     - Performing low-level macOS cleanup.
    """
    def __init__(self):
        self.edsdk = None
        self.camera = None
        self.session_open = False
        self.status = CameraStatus()
        self.last_frame_time = 0
        self._event_handlers_set = False
        self._load_edsdk()
        self._initialize_sdk()

    def _load_edsdk(self):
        """Load the Canon EDSDK library."""
        try:
            edsdk_path = "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"
            print("Attempting to load EDSDK from:", os.path.abspath(edsdk_path))
            self.edsdk = ctypes.CDLL(edsdk_path)
            print("Successfully loaded EDSDK")
        except Exception as e:
            print("Error loading EDSDK:", e)
            print("Current working directory:", os.getcwd())
            raise RuntimeError(f"Failed to load EDSDK library: {e}")

    def _initialize_sdk(self):
        """Initialize the EDSDK."""
        if not self.edsdk:
            raise RuntimeError("EDSDK not loaded")
        err = self.edsdk.EdsInitializeSDK()
        if err != EDS_ERR_OK:
            raise RuntimeError(f"Failed to initialize SDK: {err}")

    def _process_events(self):
        """Process pending camera events."""
        if not self.edsdk or not self.camera:
            return
        try:
            err = self.edsdk.EdsGetEvent()
            if err != EDS_ERR_OK:
                print(f"Warning: Failed to process events: {err}")
        except Exception as e:
            print(f"Error processing events: {e}")

    def _warmup(self, duration: float = 3.0):
        """
        Warm up event processing to allow internal state to settle.
        Mirrors behavior in test scripts.
        """
        print("Warming up EDSDK events...")
        start_time = time.time()
        count = 0
        while time.time() - start_time < duration:
            self._process_events()
            count += 1
            time.sleep(0.05)
        print(f"Warmed up: called EdsGetEvent() {count} times over {duration:.1f}s")

    def _get_first_camera(self):
        """
        Locate the first available camera.
        Uses warmup and enhanced retry logic.
        """
        camera_list = ctypes.c_void_p()
        camera = ctypes.c_void_p()
        self._warmup(3.0)
        print("Processing events before getting camera list...")
        self._process_events()
        print("Attempting to get camera list...")
        err = self.edsdk.EdsGetCameraList(ctypes.byref(camera_list))
        if err != EDS_ERR_OK:
            raise CameraError("Failed to get camera list", err,
                              "Check USB connection and camera power")
        print("Processing events after getting camera list...")
        self._process_events()
        max_retries = 15
        count_val = ctypes.c_uint32(0)
        for attempt in range(max_retries):
            for _ in range(10):
                self._process_events()
            err = self.edsdk.EdsGetChildCount(camera_list, ctypes.byref(count_val))
            if err == EDS_ERR_OK and count_val.value > 0:
                break
            print(f"Retry {attempt+1}/{max_retries}: Found {count_val.value} camera(s), err: {err}")
            delay = 1.0 + (attempt * 0.5)
            print(f"Waiting {delay:.1f}s before next attempt...")
            time.sleep(delay)
            for _ in range(10):
                self._process_events()
        if count_val.value == 0:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("No cameras detected", kEdsErr_DeviceNotFound,
                              "Verify camera power and connection")
        print(f"Found {count_val.value} camera(s)")
        max_handle_retries = 10
        for attempt in range(max_handle_retries):
            for _ in range(10):
                self._process_events()
            err = self.edsdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera))
            if err == EDS_ERR_OK:
                break
            print(f"Retry {attempt+1}/{max_handle_retries}: Failed to get camera handle, err: {err}")
            delay = 0.5 + (attempt * 0.2)
            print(f"Waiting {delay:.1f}s before next attempt...")
            time.sleep(delay)
            for _ in range(10):
                self._process_events()
        if err != EDS_ERR_OK:
            self.edsdk.EdsRelease(camera_list)
            raise CameraError("Failed to get camera handle", err,
                              "Camera connection failed")
        try:
            print("Releasing camera list...")
            self.edsdk.EdsRelease(camera_list)
            print("Camera list released successfully")
        except Exception as e:
            print(f"Warning: Error releasing camera list: {e}")
        print("Camera handle obtained successfully")
        return camera

    def connect(self):
        """Connect to the camera."""
        if self.camera:
            return
        try:
            cam = self._get_first_camera()
            err = self.edsdk.EdsOpenSession(cam)
            if err != EDS_ERR_OK:
                if cam:
                    self.edsdk.EdsRelease(cam)
                raise CameraError("Failed to open session", err)
            self.camera = cam
            self.session_open = True
            self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_ExtendShutDownTimer, 0)
            save_to = ctypes.c_uint32(kEdsSaveTo_Host)
            self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_SaveTo, 0,
                                          ctypes.sizeof(save_to), ctypes.byref(save_to))
            print("Successfully connected to camera!")
        except Exception as e:
            if not self.camera and cam:
                try:
                    self.edsdk.EdsRelease(cam)
                except:
                    pass
            raise e

    def disconnect(self):
        """Disconnect and clean up the camera connection."""
        if self.camera:
            if self.session_open:
                try:
                    print("Closing session...")
                    self.edsdk.EdsCloseSession(self.camera)
                    self.session_open = False
                except Exception as e:
                    print(f"Warning: Error closing session: {e}")
                    self.session_open = False
            try:
                print("Releasing camera...")
                self.edsdk.EdsRelease(self.camera)
            except Exception as e:
                print(f"Warning: Error releasing camera: {e}")
            self.camera = None
        print("Connection cleanup complete")
        self.edsdk = None

    def _low_level_cleanup(self):
        """
        Perform low-level macOS cleanup.
        Restarts the 'usbd' daemon to reset USB connections.
        """
        import platform
        if platform.system() == "Darwin":
            try:
                print("Performing low-level macOS cleanup: restarting usbd daemon...")
                result = os.system("killall -HUP usbd")
                if result == 0:
                    print("Low-level cleanup: usbd restarted successfully")
                else:
                    print("Low-level cleanup: usbd restart command failed")
            except Exception as e:
                print(f"Low-level cleanup error: {e}")

    def reset(self):
        """Reset the connection to allow a new connection attempt."""
        print("Resetting camera connection state...")
        self.disconnect()
        self._low_level_cleanup()
        self.__init__()

# Provide backwards compatibility alias
CanonCamera = CanonCameraConnection

class CanonCameraController:
    """
    Controls camera operations on top of an active CanonCameraConnection.
    Provides methods to start/stop live view, process events, and download EVF images.
    """
    def __init__(self, connection: CanonCameraConnection):
        if connection.camera is None:
            raise RuntimeError("Camera connection not established")
        self.connection = connection
        self.status = connection.status  # Shared status
        self.last_frame_time = connection.last_frame_time
        self.live_view_active = False

    def _process_events(self):
        self.connection._process_events()

    @contextmanager
    def evf_image_context(self):
        """
        Context manager for EVF image resources.
        """
        stream = ctypes.c_void_p()
        evf_image = ctypes.c_void_p()
        err = self.connection.edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
        if err != EDS_ERR_OK:
            raise StreamError("Failed to create memory stream", err)
        err = self.connection.edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            raise StreamError("Failed to create EVF image", err)
        try:
            yield (stream, evf_image)
        finally:
            try:
                self.connection.edsdk.EdsRelease(evf_image)
            except:
                pass
            try:
                self.connection.edsdk.EdsRelease(stream)
            except:
                pass

    def _retry_with_backoff(self, operation, max_attempts=3, initial_delay=0.1):
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
                if isinstance(e, StreamError):
                    delay = e.recovery_delay
                jitter = random.uniform(0, 0.1)
                time.sleep(delay + jitter)
                delay *= 2
                self.status.errors_since_start += 1
                self.status.last_error = str(e)
        return False, last_error

    def get_status(self) -> CameraStatus:
        """Retrieve current camera status."""
        if not self.connection.camera:
            return self.status
        try:
            now = time.time()
            self.status.time_since_last_frame = now - self.connection.last_frame_time
            evf_mode = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Evf_Mode,
                                                            0, ctypes.sizeof(evf_mode),
                                                            ctypes.byref(evf_mode))
            if err == EDS_ERR_OK:
                self.status.mode = evf_mode.value
            device = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Evf_OutputDevice,
                                                            0, ctypes.sizeof(device),
                                                            ctypes.byref(device))
            if err == EDS_ERR_OK:
                self.status.output_device = device.value
            hist = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Evf_HistogramStatus,
                                                            0, ctypes.sizeof(hist),
                                                            ctypes.byref(hist))
            if err == EDS_ERR_OK:
                self.status.histogram_status = hist.value
            temp = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_TempStatus,
                                                            0, ctypes.sizeof(temp),
                                                            ctypes.byref(temp))
            if err == EDS_ERR_OK:
                self.status.temperature_status = temp.value
            battery = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_BatteryLevel,
                                                            0, ctypes.sizeof(battery),
                                                            ctypes.byref(battery))
            if err == EDS_ERR_OK:
                self.status.battery_level = battery.value
            record = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Record,
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
        Start live view operation.
        Returns True if live view is successfully started.
        """
        # Verify connection is ready
        try:
            self.connection._process_events()
            # Get current EVF mode
            evf_mode = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Evf_Mode,
                                                             0, ctypes.sizeof(evf_mode),
                                                             ctypes.byref(evf_mode))
            if err == EDS_ERR_OK:
                print(f"Current EVF mode: {evf_mode.value}")
            else:
                print(f"Warning: Could not get EVF mode (error {err})")
            if evf_mode.value != 1:
                print("Enabling EVF mode...")
                evf_mode = ctypes.c_uint32(1)
                for attempt in range(3):
                    err = self.connection.edsdk.EdsSetPropertyData(self.connection.camera, kEdsPropID_Evf_Mode,
                                                                     0, ctypes.sizeof(evf_mode),
                                                                     ctypes.byref(evf_mode))
                    if err == EDS_ERR_OK:
                        print("EVF mode enabled successfully")
                        break
                    if err == kEdsErr_DeviceBusy:
                        print(f"Camera busy, retrying... (attempt {attempt + 1}/3)")
                        self._process_events()
                        time.sleep(0.5)
                        continue
                    print(f"Failed to enable EVF mode: {err}")
                    return False
                time.sleep(0.5)
                self._process_events()
            device = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Evf_OutputDevice,
                                                             0, ctypes.sizeof(device),
                                                             ctypes.byref(device))
            if err == EDS_ERR_OK:
                print(f"Current output device: {device.value}")
            else:
                print(f"Warning: Could not get output device (error {err})")
            if not (device.value & kEdsEvfOutputDevice_PC):
                print("Setting PC as output device...")
                device = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
                for attempt in range(3):
                    err = self.connection.edsdk.EdsSetPropertyData(self.connection.camera, kEdsPropID_Evf_OutputDevice,
                                                                     0, ctypes.sizeof(device),
                                                                     ctypes.byref(device))
                    if err == EDS_ERR_OK:
                        print("Output device set successfully")
                        break
                    if err == kEdsErr_DeviceBusy:
                        print(f"Camera busy, retrying... (attempt {attempt + 1}/3)")
                        self._process_events()
                        time.sleep(0.5)
                        continue
                    print(f"Failed to set output device: {err}")
                    return False
                time.sleep(0.5)
                self._process_events()
            device = ctypes.c_uint32()
            err = self.connection.edsdk.EdsGetPropertyData(self.connection.camera, kEdsPropID_Evf_OutputDevice,
                                                             0, ctypes.sizeof(device),
                                                             ctypes.byref(device))
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
        Stop live view operation.
        Returns True if successful.
        """
        if not self.live_view_active:
            return True
        try:
            device = ctypes.c_uint32(0)
            err = self.connection.edsdk.EdsSetPropertyData(self.connection.camera, kEdsPropID_Evf_OutputDevice,
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
            self.live_view_active = False
            return False

    def download_evf_image(self, stream) -> Optional[bytes]:
        """
        Download the current live view image data.
        Returns image data as bytes, or None on failure.
        """
        if not self.connection.camera or not stream:
            return None
        if not self.live_view_active:
            return None
        if not self._verify_live_view_state():
            print("EVF state invalid - attempting recovery")
            if not self.start_live_view():
                return None
        with self.evf_image_context() as (mem_stream, evf_image):
            try:
                def download_frame():
                    self._process_events()
                    err = self.connection.edsdk.EdsDownloadEvfImage(self.connection.camera, evf_image)
                    if err != EDS_ERR_OK:
                        if err == kEdsErr_ObjectNotReady:
                            raise StreamError("Camera not ready - waiting for next frame",
                                              err, recovery_delay=RECOVERY_DELAY_SHORT)
                        elif err == kEdsErr_StreamInternalError:
                            raise StreamError("Stream I/O error - attempting recovery",
                                              err, recovery_delay=RECOVERY_DELAY_MEDIUM)
                        elif err == kEdsErr_DeviceBusy:
                            raise StreamError("Camera busy - retrying",
                                              err, recovery_delay=RECOVERY_DELAY_MEDIUM)
                        else:
                            print(f"Download error: {err}")
                            if err == kEdsErr_DeviceInvalid:
                                self.live_view_active = False
                                raise StreamError("Camera connection lost",
                                                  err, can_retry=False)
                        raise StreamError("Failed to download EVF image", err)
                    return True
                success, result = self._retry_with_backoff(download_frame,
                                                            max_attempts=3,
                                                            initial_delay=RECOVERY_DELAY_SHORT)
                if not success:
                    if isinstance(result, StreamError) and not result.can_retry:
                        self.live_view_active = False
                    return None
                image_data = ctypes.c_void_p()
                length = ctypes.c_ulonglong()
                err = self.connection.edsdk.EdsGetLength(mem_stream, ctypes.byref(length))
                if err != EDS_ERR_OK:
                    return None
                err = self.connection.edsdk.EdsGetPointer(mem_stream, ctypes.byref(image_data))
                if err != EDS_ERR_OK:
                    return None
                try:
                    buffer = (ctypes.c_ubyte * length.value).from_address(image_data.value)
                    self.connection.last_frame_time = time.time()
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

    def _verify_live_view_state(self) -> bool:
        """Verify live view is properly configured."""
        return self.connection.camera is not None and self.live_view_active

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
