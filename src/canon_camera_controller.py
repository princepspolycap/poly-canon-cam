from typing import Optional
from src.camera_constants import EDS_ERR_OK, RECOVERY_DELAY_MEDIUM, RECOVERY_DELAY_SHORT, CameraStatus, StreamError, kEdsErr_DeviceBusy, kEdsErr_DeviceInvalid, kEdsErr_ObjectNotReady, kEdsErr_StreamInternalError, kEdsEvfOutputDevice_PC, kEdsPropID_BatteryLevel, kEdsPropID_Evf_HistogramStatus, kEdsPropID_Evf_Mode, kEdsPropID_Evf_OutputDevice, kEdsPropID_Record, kEdsPropID_TempStatus
from src.canon_camera_connection import CanonCameraConnection


import ctypes
import random
import time
from contextlib import contextmanager


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