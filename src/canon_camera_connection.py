from src.camera_constants import (
    EDS_ERR_OK, CameraError, CameraStatus, kEdsCameraCommand_ExtendShutDownTimer,
    kEdsErr_DeviceNotFound, kEdsPropID_SaveTo, kEdsSaveTo_Host,
    kEdsPropID_ProductName, kEdsPropID_BodyIDEx, kEdsPropID_FirmwareVersion,
    kEdsPropID_BatteryLevel, kEdsPropID_TempStatus, kEdsPropID_AEModuleMode,
    kEdsPropID_Evf_OutputDevice, kEdsEvfOutputDevice_PC,
    kEdsPropID_Evf_Mode, kEdsEvfMode_Enable,
    CMD_CONNECT, CMD_DISCONNECT, CMD_START_LIVE_VIEW, CMD_STOP_LIVE_VIEW,
    CMD_CAPTURE_FRAME, CMD_GET_CAMERA_INFO, CMD_GET_STATUS, CMD_SHUTDOWN,
    MSG_STATUS_UPDATE, MSG_ERROR, MSG_CAMERA_INFO, MSG_LIVE_FRAME,
    MSG_CONNECTION_STATUS, MSG_LOG,
    # Property and State Event constants
    kEdsPropertyEvent_PropertyChanged, kEdsPropertyEvent_PropertyDescChanged,
    kEdsStateEvent_Shutdown, kEdsStateEvent_JobStatusChanged,
    kEdsStateEvent_WillSoonShutDown, kEdsStateEvent_ShutDownTimerUpdate,
    kEdsStateEvent_CaptureError, kEdsStateEvent_InternalError
)
from src import camera_utils # For cleanup utilities

import ctypes
import os
import time
import threading
import queue
import platform


class CanonCameraConnection:
    """
    Handles establishment and management of a connection with a Canon camera
    using the EDSDK in a dedicated worker thread.
    """
    def __init__(self):
        self.edsdk = None
        self.camera = None
        self.session_open = False
        self.status = CameraStatus() # Managed by worker thread
        self._event_lock = threading.Lock()
        self._state_handler = None # To prevent garbage collection
        self._property_handler = None # To prevent garbage collection
        
        # Event for signaling when property changes are detected
        self._evf_output_device_changed_event = threading.Event()
        self._property_event_data = {"property_id": None, "event_type": None}

        self.command_queue = None
        self.data_queue = None
        self.worker_thread = None
        self.shutdown_event = threading.Event()
        self.live_view_active = False
        self._edsdk_path = "./EDSDK 13.19.0 Macintosh/EDSDK.framework/Versions/A/EDSDK"

    def _send_data(self, msg_type, payload):
        if self.data_queue:
            try:
                self.data_queue.put_nowait({"type": msg_type, "payload": payload})
            except queue.Full:
                print(f"Warning: Data queue full. Dropping message: {msg_type}")

    def _send_log(self, message):
        self._send_data(MSG_LOG, {"message": message})

    def _send_error(self, message, code=None, recovery_hint=None, source_func=None):
        error_payload = {"message": message}
        if code is not None:
            error_payload["code"] = code
        if recovery_hint:
            error_payload["recovery_hint"] = recovery_hint
        if source_func:
            error_payload["source"] = source_func
        self._send_data(MSG_ERROR, error_payload)

    def _load_edsdk(self):
        """Load the Canon EDSDK library. Called by worker thread."""
        try:
            self._send_log(f"Attempting to load EDSDK from: {os.path.abspath(self._edsdk_path)}")
            self.edsdk = ctypes.CDLL(self._edsdk_path)
            self._send_log("Successfully loaded EDSDK.")
            self._send_data(MSG_CONNECTION_STATUS, {"status": "sdk_loaded", "message": "EDSDK loaded successfully."})
            return True
        except Exception as e:
            err_msg = f"Failed to load EDSDK library: {e}. CWD: {os.getcwd()}"
            self._send_error(err_msg, source_func="_load_edsdk")
            return False

    def _initialize_sdk(self):
        """Initialize the EDSDK. Called by worker thread."""
        if not self.edsdk:
            self._send_error("EDSDK not loaded, cannot initialize.", source_func="_initialize_sdk")
            return False

        # Reset property change event flag at initialization
        self._evf_output_device_changed_event.clear()

        # Define state event handler callback
        EdsStateEventHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
        @EdsStateEventHandler
        def camera_state_callback(event, param, context):
            # This callback runs in an EDSDK internal thread.
            # Handle state events if needed in the future
            return EDS_ERR_OK
        self._state_handler = camera_state_callback # Keep a reference

        # Define property event handler callback
        EdsPropertyEventHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
        @EdsPropertyEventHandler
        def camera_property_callback(event, property_id, param, context):
            # This callback runs in an EDSDK internal thread
            try:
                # Check if this is a property change event
                if event == kEdsPropertyEvent_PropertyChanged:
                    # We need to track property_id to determine which property changed
                    if property_id == kEdsPropID_Evf_OutputDevice:
                        # Signal the event when Evf_OutputDevice property changes
                        # This allows the main thread to know when the camera has processed the change
                        connection = ctypes.cast(context, ctypes.py_object).value
                        if connection and hasattr(connection, '_evf_output_device_changed_event'):
                            connection._property_event_data["property_id"] = property_id
                            connection._property_event_data["event_type"] = event
                            connection._evf_output_device_changed_event.set()
                            # Can't use send_log directly from callback thread
                            # Must use thread-safe methods or flags
            except Exception:
                # Callbacks should never raise exceptions back to the SDK
                pass
            return EDS_ERR_OK
        self._property_handler = camera_property_callback  # Keep a reference

        with self._event_lock:
            err = self.edsdk.EdsInitializeSDK()
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to initialize SDK", code=err, source_func="_initialize_sdk")
                return False

            # Set state event handler
            err = self.edsdk.EdsSetCameraStateEventHandler(None, 0, self._state_handler, None)
            if err != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to set state event handler: {err}")
                
            # Set property event handler - use 'self' as context so callback can access instance variables
            context_ptr = ctypes.py_object(self)
            err = self.edsdk.EdsSetPropertyEventHandler(None, 0, self._property_handler, context_ptr)
            if err != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to set property event handler: {err}")
            
            # Process one event immediately after SDK initialization (critical for macOS)
            self._send_log("Processing one event immediately after SDK initialization...")
            try:
                init_event_err = self.edsdk.EdsGetEvent()
                if init_event_err != EDS_ERR_OK:
                    self._send_log(f"Warning: EdsGetEvent after SDK init returned: {init_event_err}")
            except Exception as e: # Should not happen if SDK is initialized
                self._send_error(f"Crash during EdsGetEvent after SDK init: {e}", source_func="_initialize_sdk")
                return False # This indicates a severe problem

        self._send_log("SDK initialized successfully.")
        self._send_data(MSG_CONNECTION_STATUS, {"status": "sdk_initialized", "message": "SDK initialized."})
        return True

    def _process_events(self):
        """Process pending camera events. Called by worker thread."""
        if not self.edsdk or self.shutdown_event.is_set():
            return
        try:
            with self._event_lock:
                err = self.edsdk.EdsGetEvent()
            if err != EDS_ERR_OK and err != kEdsErr_DeviceNotFound: # DeviceNotFound is common if no camera
                self._send_log(f"Warning: EdsGetEvent returned: {err}")
        except Exception as e: # Should not happen with proper SDK state
            self._send_error(f"Error processing EDSDK events: {e}", source_func="_process_events")


    def _handle_connect_command(self):
        """Handles camera connection logic. Called by worker thread."""
        if self.camera and self.session_open:
            self._send_log("Already connected.")
            self._send_data(MSG_CONNECTION_STATUS, {"status": "connected", "message": "Already connected."})
            # Optionally send current camera info again
            info = self._get_camera_info_internal()
            if info: self._send_data(MSG_CAMERA_INFO, info)
            return

        camera_list = ctypes.c_void_p()
        temp_camera = ctypes.c_void_p()
        camera_found = False

        try:
            self._send_log("Attempting to connect to camera...")
            self._process_events() # Process events before getting list

            with self._event_lock:
                err = self.edsdk.EdsGetCameraList(ctypes.byref(camera_list))
            if err != EDS_ERR_OK:
                self._send_error("Failed to get camera list", code=err, source_func="_handle_connect_command",
                                 recovery_hint="Check USB connection and camera power.")
                return

            self._process_events() # Process events after getting list

            count_val = ctypes.c_uint32(0)
            with self._event_lock:
                err = self.edsdk.EdsGetChildCount(camera_list, ctypes.byref(count_val))
            if err != EDS_ERR_OK:
                self._send_error("Failed to get camera count", code=err, source_func="_handle_connect_command")
                if camera_list: self.edsdk.EdsRelease(camera_list)
                return

            if count_val.value == 0:
                self._send_error("No cameras detected.", code=kEdsErr_DeviceNotFound, source_func="_handle_connect_command",
                                 recovery_hint="Verify camera power, USB connection, PTP mode.")
                if camera_list: self.edsdk.EdsRelease(camera_list)
                return

            self._send_log(f"Found {count_val.value} camera(s). Attempting to connect to the first one.")
            
            with self._event_lock:
                err = self.edsdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(temp_camera))
            if err != EDS_ERR_OK:
                self._send_error("Failed to get camera handle from list", code=err, source_func="_handle_connect_command")
                if camera_list: self.edsdk.EdsRelease(camera_list)
                return
            
            camera_found = True # temp_camera now holds a reference

        finally:
            if camera_list:
                with self._event_lock:
                    self.edsdk.EdsRelease(camera_list) # Release the list regardless

        if not camera_found or not temp_camera: # Should be redundant if logic above is correct
            self._send_error("Failed to obtain camera handle.", source_func="_handle_connect_command")
            return

        # Open session with the found camera
        with self._event_lock:
            err = self.edsdk.EdsOpenSession(temp_camera)
        if err != EDS_ERR_OK:
            self._send_error("Failed to open session with camera", code=err, source_func="_handle_connect_command")
            with self._event_lock:
                self.edsdk.EdsRelease(temp_camera) # Release the camera ref if session failed
            return

        self.camera = temp_camera
        self.session_open = True
        self._send_log("Camera session opened successfully.")

        # Configure camera (extend shutdown timer, save to host)
        try:
            with self._event_lock:
                self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_ExtendShutDownTimer, 0)
            self._send_log("Extended camera shutdown timer.")
            
            save_to = ctypes.c_uint32(kEdsSaveTo_Host)
            with self._event_lock:
                self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_SaveTo, 0,
                                            ctypes.sizeof(save_to), ctypes.byref(save_to))
            self._send_log("Set camera to save images to host.")
        except Exception as e:
            self._send_log(f"Warning: Non-critical error during post-connection setup: {e}")

        self._send_data(MSG_CONNECTION_STATUS, {"status": "connected", "message": "Camera connected successfully."})
        info = self._get_camera_info_internal()
        if info: self._send_data(MSG_CAMERA_INFO, info)
        status_obj = self._get_status_internal()
        if status_obj: self._send_data(MSG_STATUS_UPDATE, status_obj.to_dict())


    def _get_camera_info_internal(self):
        """Retrieves camera information. Called by worker thread."""
        if not self.camera or not self.session_open:
            return None
        
        info = {}
        try:
            # Product Name
            product_name_str = ctypes.create_string_buffer(256)
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_ProductName, 0, 256, product_name_str) == EDS_ERR_OK:
                    info["product_name"] = product_name_str.value.decode('utf-8', errors='ignore').strip()
            
            # Serial Number (BodyIDEx)
            serial_str = ctypes.create_string_buffer(256)
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_BodyIDEx, 0, 256, serial_str) == EDS_ERR_OK:
                    info["serial_number"] = serial_str.value.decode('utf-8', errors='ignore').strip()

            # Firmware Version
            firmware_str = ctypes.create_string_buffer(256)
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_FirmwareVersion, 0, 256, firmware_str) == EDS_ERR_OK:
                    info["firmware_version"] = firmware_str.value.decode('utf-8', errors='ignore').strip()
            
            return info
        except Exception as e:
            self._send_error(f"Error getting camera info: {e}", source_func="_get_camera_info_internal")
            return None

    def _get_status_internal(self):
        """Retrieves camera status. Called by worker thread."""
        if not self.camera or not self.session_open:
            return None
        
        current_status = CameraStatus() # Create a new status object
        try:
            # Battery Level
            battery_level = ctypes.c_uint32()
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_BatteryLevel, 0, ctypes.sizeof(battery_level), ctypes.byref(battery_level)) == EDS_ERR_OK:
                    # Convert specific Canon battery values if necessary, or use raw value
                    # For now, using raw value. Canon spec: 0x00-0x64 normal, 0xFF low, 0xFE very low
                    # Let's assume it's a percentage if <= 100, otherwise special code
                    current_status.battery_level = battery_level.value if battery_level.value <= 100 else -1 
            
            # Temperature Status
            temp_status = ctypes.c_uint32()
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_TempStatus, 0, ctypes.sizeof(temp_status), ctypes.byref(temp_status)) == EDS_ERR_OK:
                    current_status.temperature_status = temp_status.value
            
            # AE Mode (Shooting Mode)
            ae_mode = ctypes.c_uint32()
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_AEModuleMode, 0, ctypes.sizeof(ae_mode), ctypes.byref(ae_mode)) == EDS_ERR_OK:
                    current_status.mode = ae_mode.value # This is a numerical code

            self.status = current_status # Update the class instance status
            return current_status
        except Exception as e:
            self._send_error(f"Error getting camera status: {e}", source_func="_get_status_internal")
            return None

    def _handle_get_camera_info_command(self):
        info = self._get_camera_info_internal()
        if info:
            self._send_data(MSG_CAMERA_INFO, info)
        else: # Error already sent by _get_camera_info_internal if it failed
            self._send_data(MSG_CAMERA_INFO, {}) # Send empty if no info but no error

    def _handle_get_status_command(self):
        status_obj = self._get_status_internal()
        if status_obj:
            self._send_data(MSG_STATUS_UPDATE, status_obj.to_dict())
        else:
            self._send_data(MSG_STATUS_UPDATE, CameraStatus().to_dict()) # Send default if error

    def _handle_start_live_view_command(self):
        if not self.camera or not self.session_open:
            self._send_error("Cannot start live view: Not connected.", source_func="_handle_start_live_view_command")
            return
        if self.live_view_active:
            self._send_log("Live view is already active.")
            return

        try:
            self._send_log("Attempting to start live view...")

            # Get the original EVF output device value for potential revert
            self._send_log("Reading original EVF output device value from camera for potential revert...")
            original_evf_output_device_for_revert = ctypes.c_uint32()
            err_get_orig_device = EDS_ERR_OK # Assume OK for now
            with self._event_lock:
                if self.camera and self.session_open and self.edsdk: # Check before SDK call
                    err_get_orig_device = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(original_evf_output_device_for_revert), ctypes.byref(original_evf_output_device_for_revert))
                else:
                    err_get_orig_device = kEdsErr_DeviceNotFound # Simulate error if no camera/session

            original_device_to_revert_val = 0 # Default to Camera LCD
            if err_get_orig_device == EDS_ERR_OK:
                self._send_log(f"Original EVF output device value (for revert): {original_evf_output_device_for_revert.value}")
                original_device_to_revert_val = original_evf_output_device_for_revert.value
            else:
                self._send_log(f"Warning: Failed to get original EVF output device (Error: {err_get_orig_device}). Will revert to 0 (Camera LCD) on failure.")

            # Set EVF output device to PC by ORing with the current value
            self._send_log("Reading current EVF output device value from camera for ORing...")
            current_device_val_for_or = ctypes.c_uint32()
            err_get_current_for_or = EDS_ERR_OK
            with self._event_lock:
                if self.camera and self.session_open and self.edsdk:
                    err_get_current_for_or = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(current_device_val_for_or), ctypes.byref(current_device_val_for_or))
                else:
                    err_get_current_for_or = kEdsErr_DeviceNotFound

            if err_get_current_for_or != EDS_ERR_OK:
                self._send_error(f"Failed to read current EVF output device before ORing (Error: {err_get_current_for_or}). Aborting live view start.", code=err_get_current_for_or, source_func="_handle_start_live_view_command")
                # No revert needed here as we haven't changed it yet, and original_device_to_revert_val is what it was.
                return
            self._send_log(f"Current EVF output device value from camera (for ORing): {current_device_val_for_or.value}")

            new_output_device_val = current_device_val_for_or.value | kEdsEvfOutputDevice_PC
            self._send_log(f"Setting EVF output device to: {new_output_device_val} (current ORed with PC value {kEdsEvfOutputDevice_PC})")
            output_device_to_set = ctypes.c_uint32(new_output_device_val)
            
            err_set_prop = EDS_ERR_OK
            with self._event_lock:
                if self.camera and self.session_open and self.edsdk:
                    err_set_prop = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(output_device_to_set), ctypes.byref(output_device_to_set))
                else:
                    err_set_prop = kEdsErr_DeviceNotFound
            
            if err_set_prop != EDS_ERR_OK:
                self._send_error(f"Failed to set ORed EVF output device (Error: {err_set_prop}).", code=err_set_prop, source_func="_handle_start_live_view_command")
                self._revert_live_view_settings_on_failure(original_device_to_revert_val)
                return
            self._send_log(f"Successfully set ORed EVF output device (Result: {err_set_prop}).")

            # Clear the property change event flag before setting the property
            self._evf_output_device_changed_event.clear()
            self._property_event_data["property_id"] = None
            self._property_event_data["event_type"] = None
            
            self._send_log("Property change event flag cleared. Waiting for Evf_OutputDevice property change event...")
            
            # Process events to detect property change notification
            max_wait_time = 3.0  # Maximum wait time in seconds
            start_wait_time = time.time()
            property_change_detected = False
            
            # Wait for property change event or timeout
            while time.time() - start_wait_time < max_wait_time:
                # Process events to receive notifications
                self._process_events()
                
                # Check if our property change event was set by the callback
                if self._evf_output_device_changed_event.is_set():
                    property_change_detected = True
                    self._send_log(f"Evf_OutputDevice property change event detected! Property ID: {self._property_event_data['property_id']}, Event Type: {self._property_event_data['event_type']}")
                    break
                
                time.sleep(0.05)  # Small sleep to prevent busy waiting
            
            if property_change_detected:
                self._send_log("Successfully detected property change event for Evf_OutputDevice.")
            else:
                self._send_log("Warning: Timed out waiting for Evf_OutputDevice property change event. Proceeding with caution.")

            # Read back EVF output device property to confirm change
            self._send_log("Reading back EVF output device property to confirm change...")
            current_output_device_readback = ctypes.c_uint32()
            with self._event_lock:
                err_read_output = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(current_output_device_readback), ctypes.byref(current_output_device_readback))
            
            if err_read_output == EDS_ERR_OK:
                self._send_log(f"Confirmed EVF output device is: {current_output_device_readback.value} (PC bit is {kEdsEvfOutputDevice_PC})")
                if not (current_output_device_readback.value & kEdsEvfOutputDevice_PC):
                    self._send_error(f"EVF output device did not have PC bit set. Value: {current_output_device_readback.value}, PC bit: {kEdsEvfOutputDevice_PC}", 
                                    source_func="_handle_start_live_view_command")
                    # If the PC bit isn't set, attempting to enable EVF mode is likely to fail
                    self._revert_live_view_settings_on_failure(original_device_to_revert_val)
                    return
                else:
                    self._send_log(f"EVF output device correctly has PC bit set ({current_output_device_readback.value}).")
            else:
                self._send_log(f"Warning: Failed to read back EVF output device property (Error: {err_read_output}). Proceeding with caution.")

            # Log current camera mode (optional, but can be useful for debugging)
            current_cam_status = self._get_status_internal()
            if current_cam_status and hasattr(current_cam_status, 'mode'):
                self._send_log(f"Camera AE Mode before attempting live view download: {current_cam_status.mode}")
            else:
                self._send_log("Could not determine camera AE mode before attempting live view download.")

            # Per EDSDK Sample, kEdsPropID_Evf_Mode is NOT explicitly set.
            # Instead, after setting kEdsPropID_Evf_OutputDevice, we process events
            # and then attempt to download the EVF image.
            self._send_log("Skipping explicit kEdsPropID_Evf_Mode set, aligning with EDSDK sample.")

            # Enhanced event processing after setting Evf_OutputDevice - wait for property change notification
            self._send_log("Enhanced event processing after setting Evf_OutputDevice (up to 2.0s)...")
            start_event_processing_time = time.time()
            event_loops = 0
            
            # Poll events for up to 2 seconds, waiting for the camera to process the output device change
            # and issue property change notifications.
            while time.time() - start_event_processing_time < 2.0:
                self._process_events()
                event_loops += 1
                time.sleep(0.05) # Small sleep between event polls
            
            self._send_log(f"Completed {event_loops} event processing loops after setting Evf_OutputDevice.")
            
            # Proceed to attempt download. The camera should be ready if Evf_OutputDevice was set correctly
            # and property change events have been processed.

            # Attempt a "priming" download with multiple retries for OBJECT_NOTREADY
            self._send_log("Attempting a priming download of the first EVF image with retries...")
            priming_stream = ctypes.c_void_p()
            max_retries = 10  # Maximum number of download attempts
            retry_delay = 0.2  # Delay between retries in seconds
            download_success = False
            
            try:
                with self._event_lock:
                    err_create_stream = self.edsdk.EdsCreateMemoryStream(0, ctypes.byref(priming_stream))
                if err_create_stream != EDS_ERR_OK:
                    self._send_error(f"Priming: Failed to create memory stream (Error: {err_create_stream}). Aborting live view start.", code=err_create_stream, source_func="_handle_start_live_view_command")
                    self._revert_live_view_settings_on_failure(original_device_to_revert_val)
                    return
                
                # Retry loop for handling EDS_ERR_OBJECT_NOTREADY
                for retry_count in range(max_retries):
                    # Process events before each download attempt
                    self._process_events()
                    
                    # Try to download the EVF image
                    with self._event_lock:
                        err_download_prime = self.edsdk.EdsDownloadEvfImage(self.camera, priming_stream)
                    
                    if err_download_prime == EDS_ERR_OK:
                        # Success!
                        self._send_log(f"Priming download successful on attempt {retry_count + 1}. First EVF image obtained.")
                        download_success = True
                        break
                    elif err_download_prime == 0x00008D04:  # EDS_ERR_OBJECT_NOTREADY
                        # This is expected if the camera isn't ready yet
                        self._send_log(f"EVF image not ready on attempt {retry_count + 1} (Error: 0x8D04). Waiting and retrying...")
                        time.sleep(retry_delay)  # Wait before next attempt
                        
                        # Increase delay slightly for each retry to give camera more time
                        retry_delay += 0.1
                        
                        # Continue to next retry
                        continue
                    else:
                        # Some other error occurred
                        self._send_error(f"Priming: Failed to download EVF image (Error: {err_download_prime}) on attempt {retry_count + 1}. Aborting live view start.", 
                                       code=err_download_prime, source_func="_handle_start_live_view_command")
                        break
                
                # Check if we ever succeeded
                if not download_success:
                    self._send_log(f"Priming: Failed to download EVF image after {max_retries} attempts. Aborting live view start.")
                    self._revert_live_view_settings_on_failure(original_device_to_revert_val)
                    return
                
                # We successfully downloaded an image, but don't need to process it
            finally:
                if priming_stream: # Ensure stream is released even if download part failed after creation
                    with self._event_lock:
                        release_err = self.edsdk.EdsRelease(priming_stream)
                    if release_err != EDS_ERR_OK:
                        self._send_log(f"Priming: Warning, failed to release priming stream (Error: {release_err})")
            
            # If priming was successful, proceed to activate live view for the loop
            if download_success: # Check if priming download was actually successful
                self.live_view_active = True
                self._send_log("Live view started successfully (live_view_active set to True) after priming.")
                self._send_data(MSG_STATUS_UPDATE, {"live_view_status": "active"})
            # If download_success is false, the revert and return path is already handled within the priming block.

        except Exception as e:
            self.live_view_active = False # Ensure it's off if any exception occurs
            self._send_error(f"Exception starting live view: {e}", source_func="_handle_start_live_view_command")
            # Ensure original_device_to_revert_val is defined in this scope for the except block
            # It should be, as it's defined at the beginning of the try block.
            self._revert_live_view_settings_on_failure(original_device_to_revert_val) # Attempt cleanup

    def _revert_live_view_settings_on_failure(self, original_evf_output_device_target=0):
        """
        Helper to attempt reverting EVF mode and output device on failure.
        :param original_evf_output_device_target: The EVF output device value to revert to.
                                                 Defaults to 0 (typically Camera LCD).
        """
        self._send_log(f"Attempting to revert live view settings. Target EVF output device: {original_evf_output_device_target}")
        if not self.camera or not self.session_open or not self.edsdk:
            self._send_log("Cannot revert live view settings: No camera, session, or SDK.")
            return

        try:
            # Disable EVF mode
            self._send_log("Reverting: Disabling EVF mode...")
            evf_mode_off = ctypes.c_uint32(0) # 0 to disable
            err_mode_off = EDS_ERR_OK
            with self._event_lock:
                err_mode_off = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_Mode, 0, ctypes.sizeof(evf_mode_off), ctypes.byref(evf_mode_off))
            if err_mode_off != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to disable EVF mode during revert (Error: {err_mode_off}).")
            else:
                self._send_log("Reverting: EVF mode disabled.")
            
            # Revert EVF output device to the original_evf_output_device_target
            self._send_log(f"Reverting: Setting EVF output device back to {original_evf_output_device_target}...")
            output_device_revert_val = ctypes.c_uint32(original_evf_output_device_target)
            err_revert_device = EDS_ERR_OK
            with self._event_lock:
                err_revert_device = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(output_device_revert_val), ctypes.byref(output_device_revert_val))
            if err_revert_device != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to revert EVF output device to {original_evf_output_device_target} (Error: {err_revert_device}).")
            else:
                self._send_log(f"Reverting: EVF output device set to {original_evf_output_device_target}.")
            
            self._send_log("Live view settings revert attempt finished.")
        except Exception as ex:
            self._send_error(f"Exception during live view settings revert: {ex}", source_func="_revert_live_view_settings_on_failure")


    def _handle_stop_live_view_command(self):
        if not self.camera or not self.session_open:
            # self._send_error("Cannot stop live view: Not connected.", source_func="_handle_stop_live_view_command")
            self.live_view_active = False # Ensure it's off
            return
        if not self.live_view_active:
            self._send_log("Live view is already inactive.")
            return

        try:
            # Disable EVF mode
            evf_mode = ctypes.c_uint32(0) # 0 to disable
            with self._event_lock:
                err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_Mode, 0, ctypes.sizeof(evf_mode), ctypes.byref(evf_mode))
            if err != EDS_ERR_OK:
                self._send_error("Failed to disable EVF mode.", code=err, source_func="_handle_stop_live_view_command")
                # Live view might still be considered active by camera if this fails
            
            # Revert EVF output device to Camera LCD (usually 0 or 1)
            # It's good practice to release PC control
            output_device = ctypes.c_uint32(0) # Try 0 for camera LCD
            with self._event_lock:
                self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(output_device), ctypes.byref(output_device))

            self.live_view_active = False
            self._send_log("Live view stopped successfully.")
            self._send_data(MSG_STATUS_UPDATE, {"live_view_status": "inactive"})

        except Exception as e:
            # State might be uncertain here
            self._send_error(f"Exception stopping live view: {e}", source_func="_handle_stop_live_view_command")


    def _capture_live_frame_internal(self):
        """Captures and sends one live view frame. Called by worker thread."""
        if not self.camera or not self.session_open or not self.live_view_active:
            return

        stream = ctypes.c_void_p()
        image_data_ptr = ctypes.c_void_p()
        image_length = ctypes.c_uint32()
        frame_data = None

        try:
            # Create memory stream for image data
            self._send_log("Creating memory stream for EVF image...")
            with self._event_lock:
                err = self.edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to create memory stream for EVF (Error: {err}).", code=err, source_func="_capture_live_frame_internal")
                return
            self._send_log(f"Memory stream created (Result: {err}).")

            # Download EVF image
            self._send_log("Downloading EVF image...")
            with self._event_lock:
                err = self.edsdk.EdsDownloadEvfImage(self.camera, stream)
            if err != EDS_ERR_OK:
                if err == 0x00008D04: # EDS_ERR_OBJECT_NOTREADY - common if camera is busy or LV not fully ready
                    self._send_log(f"EVF image not ready (Error: {err}, 0x8D04). Retrying shortly.")
                else:
                    self._send_error(f"Failed to download EVF image (Error: {err}).", code=err, source_func="_capture_live_frame_internal")
                if stream: 
                    with self._event_lock:
                        self.edsdk.EdsRelease(stream)
                return
            self._send_log(f"EVF image downloaded (Result: {err}).")

            # Get pointer and length of the image data
            self._send_log("Getting pointer and length of image data...")
            with self._event_lock:
                self.edsdk.EdsGetPointer(stream, ctypes.byref(image_data_ptr))
                self.edsdk.EdsGetLength(stream, ctypes.byref(image_length))

            if image_data_ptr and image_length.value > 0:
                self._send_log(f"Image data pointer: {image_data_ptr}, Length: {image_length.value}. Copying data...")
                # Create a copy of the image data
                frame_data = ctypes.string_at(image_data_ptr, image_length.value)
                self._send_data(MSG_LIVE_FRAME, {"data": frame_data, "timestamp": time.time()})
                self._send_log("Live frame data sent to queue.")
            else:
                self._send_log(f"Downloaded EVF image is empty or invalid. Pointer: {image_data_ptr}, Length: {image_length.value}.")

        except Exception as e:
            self._send_error(f"Exception capturing live frame: {e}", source_func="_capture_live_frame_internal")
        finally:
            if stream:
                self._send_log("Releasing memory stream.")
                with self._event_lock:
                    release_err = self.edsdk.EdsRelease(stream)
                if release_err != EDS_ERR_OK:
                     self._send_log(f"Warning: Failed to release memory stream (Error: {release_err}).")
                else:
                    self._send_log("Memory stream released.")


    def _handle_disconnect_command(self, called_by_shutdown=False):
        """Handles camera disconnection. Called by worker thread."""
        self._send_log("Disconnect command received.")
        if self.live_view_active:
            self._handle_stop_live_view_command() # Try to stop live view first

        if self.camera and self.session_open:
            try:
                with self._event_lock:
                    self.edsdk.EdsCloseSession(self.camera)
                self._send_log("Camera session closed.")
            except Exception as e:
                self._send_error(f"Error closing session: {e}", source_func="_handle_disconnect_command")
            self.session_open = False
        
        if self.camera:
            try:
                with self._event_lock:
                    self.edsdk.EdsRelease(self.camera)
                self._send_log("Camera object released.")
            except Exception as e:
                self._send_error(f"Error releasing camera object: {e}", source_func="_handle_disconnect_command")
            self.camera = None
        
        self.live_view_active = False # Ensure it's marked off
        if not called_by_shutdown: # Don't send if part of full worker shutdown sequence
            self._send_data(MSG_CONNECTION_STATUS, {"status": "disconnected", "message": "Camera disconnected."})


    def _worker_shutdown_cleanup(self):
        """Cleans up SDK resources when worker thread is stopping."""
        self._send_log("Worker thread shutting down. Cleaning up resources...")
        self._handle_disconnect_command(called_by_shutdown=True) # Ensure camera is disconnected

        if self.edsdk:
            try:
                with self._event_lock: # Though SDK termination should be final
                    err = self.edsdk.EdsTerminateSDK()
                if err == EDS_ERR_OK:
                    self._send_log("EDSDK terminated successfully.")
                else:
                    # This can happen if resources weren't released properly or SDK is in a bad state
                    self._send_log(f"Warning: EdsTerminateSDK returned error: {err}. This might be okay on macOS if resources were released.")
            except Exception as e:
                self._send_error(f"Exception during EdsTerminateSDK: {e}", source_func="_worker_shutdown_cleanup")
        
        self.edsdk = None
        # self._send_log("Low-level macOS cleanup (usbd restart) if applicable...")
        # self._low_level_cleanup() # Perform macOS specific cleanup
        # The comprehensive cleanup will be handled by camera_utils
        camera_utils.disconnect_and_cleanup_camera_resources(
            self.edsdk, self.camera, self.session_open, self.live_view_active,
            send_log_func=self._send_log, send_error_func=self._send_error, event_lock=self._event_lock
        )
        self._send_log("Worker shutdown cleanup complete using camera_utils.")
        self._send_data(MSG_CONNECTION_STATUS, {"status": "shutdown_complete", "message": "Worker shut down."})


    def _sdk_worker_loop(self):
        """Main loop for the SDK worker thread."""
        # Perform pre-emptive macOS cleanup BEFORE loading SDK
        self._send_log("Performing pre-emptive macOS cleanup before SDK load...")
        camera_utils.cleanup_macos_camera_connection(send_log_func=self._send_log)
        self._send_log("Pre-emptive macOS cleanup finished.")

        if not self._load_edsdk():
            self._send_error("Worker exiting: Failed to load EDSDK.", source_func="_sdk_worker_loop")
            # Attempt final cleanup even if load failed
            camera_utils.disconnect_and_cleanup_camera_resources(
                self.edsdk, self.camera, self.session_open, self.live_view_active,
                send_log_func=self._send_log, send_error_func=self._send_error, event_lock=self._event_lock
            )
            return
        if not self._initialize_sdk():
            self._send_error("Worker exiting: Failed to initialize EDSDK.", source_func="_sdk_worker_loop")
            # Attempt to terminate SDK if init failed after load
            if self.edsdk: self.edsdk.EdsTerminateSDK()
            return

        self._send_log("SDK Worker thread started and initialized.")
        last_status_check_time = 0
        live_view_frame_interval = 1.0 / 15 # Target ~15 FPS for live view processing

        while not self.shutdown_event.is_set():
            self._process_events() # Keep SDK events flowing

            # Handle commands
            try:
                command_data = self.command_queue.get_nowait()
                action = command_data.get("action")
                self._send_log(f"Worker received command: {action}")

                if action == CMD_CONNECT:
                    self._handle_connect_command()
                elif action == CMD_DISCONNECT: # Disconnect also implies stopping worker for now
                    self._handle_disconnect_command()
                    # self.shutdown_event.set() # Let CMD_SHUTDOWN handle this
                elif action == CMD_START_LIVE_VIEW:
                    self._handle_start_live_view_command()
                elif action == CMD_STOP_LIVE_VIEW:
                    self._handle_stop_live_view_command()
                elif action == CMD_GET_CAMERA_INFO:
                    self._handle_get_camera_info_command()
                elif action == CMD_GET_STATUS:
                    self._handle_get_status_command()
                elif action == CMD_SHUTDOWN:
                    self._send_log("Shutdown command received by worker.")
                    self.shutdown_event.set() # Signal loop to exit
                else:
                    self._send_error(f"Unknown command: {action}", source_func="_sdk_worker_loop")
                self.command_queue.task_done()
            except queue.Empty:
                pass # No command, continue
            except Exception as e: # Catch errors in command handling
                self._send_error(f"Error processing command: {e}", source_func="_sdk_worker_loop")
                if self.command_queue.unfinished_tasks > 0: # Check if get_nowait() raised before task_done
                    self.command_queue.task_done()


            # Live view frame capture
            if self.live_view_active and self.camera and self.session_open:
                self._capture_live_frame_internal()
                # Add a small delay to control live view FPS from worker side
                # This is a simple way; a more robust timer could be used.
                time.sleep(live_view_frame_interval) 

            # Periodic status check (e.g., every 2 seconds)
            current_time = time.time()
            if self.camera and self.session_open and (current_time - last_status_check_time > 2.0):
                status_obj = self._get_status_internal()
                if status_obj: self._send_data(MSG_STATUS_UPDATE, status_obj.to_dict())
                last_status_check_time = current_time
            
            if not self.live_view_active: # If not in active live view, sleep a bit more
                time.sleep(0.05) # Short sleep to prevent busy loop if no commands

        self._worker_shutdown_cleanup()


    def start_worker(self, command_queue, data_queue):
        """Starts the SDK worker thread."""
        if self.worker_thread and self.worker_thread.is_alive():
            self._send_log("Worker thread is already running.")
            return

        self.command_queue = command_queue
        self.data_queue = data_queue
        self.shutdown_event.clear()
        self.live_view_active = False # Reset state

        self.worker_thread = threading.Thread(target=self._sdk_worker_loop, daemon=True)
        self.worker_thread.name = "CanonSDKWorker"
        self.worker_thread.start()
        self._send_log("SDK worker thread initiated.")

    def stop_worker(self):
        """Signals the SDK worker thread to stop and waits for it to join."""
        self._send_log("Attempting to stop SDK worker thread...")
        if self.worker_thread and self.worker_thread.is_alive():
            if self.command_queue:
                # Send a shutdown command to ensure graceful cleanup within the worker
                try:
                    self.command_queue.put_nowait({"action": CMD_SHUTDOWN})
                except queue.Full:
                    self._send_log("Warning: Command queue full when trying to send SHUTDOWN. Forcing shutdown event.")
                    self.shutdown_event.set() # Force if queue is full
            else:
                self.shutdown_event.set() # If no queue, just set event

            self.worker_thread.join(timeout=10.0) # Wait for worker to finish
            if self.worker_thread.is_alive():
                self._send_log("Warning: SDK worker thread did not stop in time.")
                # Forcibly try to ensure resources are cleaned if thread is stuck
                # This is risky but might be needed if EdsTerminateSDK hangs
                if self.edsdk:
                    self._send_log("Attempting forceful EdsTerminateSDK due to unresponsive worker.")
                    try:
                        self.edsdk.EdsTerminateSDK()
                    except: pass # Ignore errors during forceful termination
            else:
                self._send_log("SDK worker thread stopped.")
        else:
            self._send_log("SDK worker thread was not running or already stopped.")
        self.worker_thread = None


    def _low_level_cleanup(self):
        """
        Perform low-level macOS cleanup.
        Restarts the 'usbd' daemon to reset USB connections.
        """
        if platform.system() == "Darwin":
            try:
                self._send_log("Performing low-level macOS cleanup: restarting usbd daemon...")
                # Note: This requires admin privileges and might be disruptive.
                # Consider making this optional or providing user guidance.
                # For now, it's included as per original logic.
                # result = os.system("sudo killall -HUP usbd") # sudo might be needed
                result = os.system("killall -HUP usbd") # Original command
                if result == 0:
                    self._send_log("Low-level cleanup: usbd restarted successfully.")
                else:
                    self._send_log(f"Low-level cleanup: usbd restart command failed (exit code: {result}). May require sudo.")
            except Exception as e:
                self._send_error(f"Low-level macOS cleanup error: {e}", source_func="_low_level_cleanup")
