from src.camera_constants import (
    EDS_ERR_OK, EDS_ERR_OBJECT_NOTREADY, CameraError, CameraStatus, kEdsCameraCommand_ExtendShutDownTimer,
    kEdsErr_DeviceNotFound, kEdsPropID_SaveTo, kEdsSaveTo_Host,
    kEdsPropID_ProductName, kEdsPropID_BodyIDEx, kEdsPropID_FirmwareVersion,
    kEdsPropID_BatteryLevel, kEdsPropID_TempStatus, kEdsPropID_AEMode,
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
    kEdsStateEvent_CaptureError, kEdsStateEvent_InternalError,
    # Recovery timing constants
    RECOVERY_DELAY_SHORT, RECOVERY_DELAY_MEDIUM, RECOVERY_DELAY_LONG
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
        self._handler_context = None
        
        # Event for signaling when property changes are detected
        self._evf_output_device_changed_event = threading.Event()
        self._property_event_data = {"property_id": None, "event_type": None}

        self.command_queue = None
        self.data_queue = None
        self.worker_thread = None
        self.shutdown_event = threading.Event()
        self.live_view_active = False
        self._edsdk_path = "./EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework/Versions/A/EDSDK"
        
        # Frame capture tracking
        self._capture_attempt_logged = False
        self._frame_count = 0
        self._notready_count = 0

    def _reset_connection_state(self):
        """Fully reset all connection state variables to prepare for clean reconnection."""
        self._send_log("Resetting connection state...")
        self.camera = None
        self.session_open = False
        self.live_view_active = False
        self._handler_context = None
        self._capture_attempt_logged = False
        self._frame_count = 0
        self._notready_count = 0
        self._evf_output_device_changed_event.clear()
        self._property_event_data = {"property_id": None, "event_type": None}

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
                            connection._send_log("Received EVF output device property-change event.")
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

            # NOTE: Event handlers are now set AFTER a session is opened, not here.
            # This is the fix for the 'Error 97' during initialization.
            
            # Enhanced event processing after SDK initialization (critical for macOS camera detection)
            self._send_log("Processing events intensively after SDK initialization for camera detection...")
            try:
                # Process events intensively for camera detection (based on successful test pattern)
                event_processing_duration = 3.0  # 3 seconds of event processing
                start_time = time.time()
                event_count = 0
                
                while time.time() - start_time < event_processing_duration:
                    init_event_err = self.edsdk.EdsGetEvent()
                    event_count += 1
                    if init_event_err != EDS_ERR_OK and init_event_err != kEdsErr_DeviceNotFound:
                        self._send_log(f"Warning: EdsGetEvent #{event_count} returned: {init_event_err}")
                    time.sleep(0.05)  # 50ms intervals for proper timing
                
                self._send_log(f"Completed intensive event processing: {event_count} events processed over {event_processing_duration}s")
                
            except Exception as e: # Should not happen if SDK is initialized
                self._send_error(f"Crash during enhanced event processing: {e}", source_func="_initialize_sdk")
                return False # This indicates a severe problem

        self._send_log("SDK initialized successfully.")
        self._send_data(MSG_CONNECTION_STATUS, {"status": "sdk_initialized", "message": "SDK initialized."})
        return True

    def _wait_for_evf_output_device_ack(self, timeout=2.5):
        """Wait for Canon-required property change event after setting EVF output device."""
        self._process_events()
        camera_utils.pump_macos_runloop(duration_sec=0.05, iterations=4)
        self._send_log("Waiting for EVF output device change confirmation...")
        event_received = self._evf_output_device_changed_event.wait(timeout)
        self._evf_output_device_changed_event.clear()
        if event_received:
            self._send_log("EVF output device change event received.")
        else:
            self._send_log("Timed out waiting for EVF output device change event.")
        self._process_events()
        camera_utils.pump_macos_runloop(duration_sec=0.05, iterations=4)
        return event_received

    def _apply_evf_output_device(self, target_value):
        """Apply EVF output device value and wait for property-change acknowledgment."""
        self._evf_output_device_changed_event.clear()
        self._send_log(f"Setting EVF output device value to 0x{target_value:02x}...")
        output_device = ctypes.c_uint32(target_value)
        with self._event_lock:
            err = self.edsdk.EdsSetPropertyData(
                self.camera, kEdsPropID_Evf_OutputDevice, 0,
                ctypes.sizeof(output_device), ctypes.byref(output_device)
            )
        if err != EDS_ERR_OK:
            self._send_error(f"Failed to set EVF output device (Error: {err})",
                             code=err, source_func="_apply_evf_output_device")
            return False

        wait_result = self._wait_for_evf_output_device_ack()

        confirm_val = ctypes.c_uint32()
        with self._event_lock:
            confirm_err = self.edsdk.EdsGetPropertyData(
                self.camera, kEdsPropID_Evf_OutputDevice, 0,
                ctypes.sizeof(confirm_val), ctypes.byref(confirm_val))
        if confirm_err == EDS_ERR_OK:
            self._send_log(f"Confirmed EVF output device now 0x{confirm_val.value:02x}")
        else:
            self._send_log(f"Unable to confirm EVF output device value (Error: {confirm_err}).")

        if not wait_result:
            self._send_log("Proceeding without property-change confirmation; live view may still fail.")
        return True

    def _configure_evf_output_for_pc(self):
        """Ensure kEdsEvfOutputDevice_PC bit is set, per Canon Sample10 guidance."""
        current_val = ctypes.c_uint32()
        with self._event_lock:
            err = self.edsdk.EdsGetPropertyData(
                self.camera, kEdsPropID_Evf_OutputDevice, 0,
                ctypes.sizeof(current_val), ctypes.byref(current_val))
        if err != EDS_ERR_OK:
            self._send_log(f"Could not read EVF output device (Error {err}); assuming camera LCD only.")
            current_value = 0x01
        else:
            current_value = current_val.value
            self._send_log(f"Current EVF output device value: 0x{current_value:02x}")

        desired_value = current_value | kEdsEvfOutputDevice_PC
        if desired_value == current_value:
            self._send_log("PC output bit already set; reasserting to ensure property change event.")

        return self._apply_evf_output_device(desired_value)

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

        # CRITICAL: Reset state and perform system cleanup before connection attempt
        self._reset_connection_state()
        
        # System-level cleanup to ensure camera is not locked
        self._send_log("Performing system-level cleanup before connection...")
        camera_utils.cleanup_macos_camera_connection(send_log_func=self._send_log)
        
        # Allow USB and camera to stabilize after cleanup
        self._send_log("Waiting for USB/camera stabilization...")
        time.sleep(1.0)
        
        camera_list = ctypes.c_void_p()
        temp_camera = ctypes.c_void_p()
        camera_found = False

        try:
            self._send_log("Attempting to connect to camera...")
            camera_utils.pump_macos_runloop(duration_sec=0.05, iterations=20)
            self._process_events() # Process events before getting list

            with self._event_lock:
                err = self.edsdk.EdsGetCameraList(ctypes.byref(camera_list))
            if err != EDS_ERR_OK:
                self._send_error("Failed to get camera list", code=err, source_func="_handle_connect_command",
                                 recovery_hint="Check USB connection and camera power.")
                return

            camera_utils.pump_macos_runloop(duration_sec=0.05, iterations=10)
            self._process_events() # Process events after getting list

            # Enhanced camera detection with retry logic (based on successful test pattern)
            self._send_log("Detecting cameras with enhanced retry logic...")
            max_detection_attempts = 10  # More attempts for reliable detection
            detection_successful = False
            
            for attempt in range(max_detection_attempts):
                # Process events before each detection attempt
                for _ in range(5):
                    self._process_events()
                camera_utils.pump_macos_runloop(duration_sec=0.05, iterations=6)
                
                count_val = ctypes.c_uint32(0)
                with self._event_lock:
                    err = self.edsdk.EdsGetChildCount(camera_list, ctypes.byref(count_val))
                if err != EDS_ERR_OK:
                    self._send_error("Failed to get camera count", code=err, source_func="_handle_connect_command")
                    if camera_list: self.edsdk.EdsRelease(camera_list)
                    return
                
                if count_val.value > 0:
                    self._send_log(f"Found {count_val.value} camera(s) on attempt {attempt + 1}")
                    detection_successful = True
                    break
                
                if attempt < max_detection_attempts - 1:
                    self._send_log(f"Camera detection attempt {attempt + 1}/{max_detection_attempts}: No cameras yet, retrying...")
                    camera_utils.pump_macos_runloop(duration_sec=0.05, iterations=10)
                    time.sleep(0.5)  # Wait before retry
            
            if not detection_successful:
                self._send_error("No cameras detected after multiple attempts.", code=kEdsErr_DeviceNotFound, 
                               source_func="_handle_connect_command",
                               recovery_hint="Verify camera power, USB connection, and PTP mode. Check camera display for 'PC' indicator.")
                if camera_list: self.edsdk.EdsRelease(camera_list)
                return
            
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

        # CRITICAL: Process events and run loop before opening session
        # This is especially important on macOS to ensure camera is ready
        self._send_log("Preparing camera for session...")
        for _ in range(10):
            self._process_events()
            time.sleep(0.05)
        camera_utils.pump_macos_runloop(duration_sec=0.1, iterations=5)

        # Open session with the found camera
        self._send_log(f"Opening session with camera (ref: {temp_camera})...")
        
        # Try closing any existing session first (in case of stale session)
        # CRITICAL: Don't hold lock during EdsCloseSession - may need runloop
        close_err = self.edsdk.EdsCloseSession(temp_camera)
        if close_err == EDS_ERR_OK:
            self._send_log("Closed pre-existing session on camera.")
            time.sleep(0.2)  # Brief delay after closing
            self._process_events()
        
        # CRITICAL: EdsOpenSession MUST NOT hold the event lock!
        # It's a blocking call that requires macOS runloop to pump events.
        # Calling it inside a lock causes deadlock with _process_events().
        import threading
        import sys
        print(f"[DEBUG] Thread ID: {threading.get_ident()}, Process ID: {os.getpid()}")
        print(f"[DEBUG] About to call EdsOpenSession (camera ref: {temp_camera})...")
        
        # For packaged apps, pump macOS events before EdsOpenSession
        if sys.platform == 'darwin':
            print("[DEBUG] Pumping macOS runloop before EdsOpenSession...")
            camera_utils.pump_macos_runloop(duration_sec=0.1, iterations=5)
        
        err = self.edsdk.EdsOpenSession(temp_camera)
        print(f"[DEBUG] EdsOpenSession returned: {err}")
        
        # Pump events again after opening
        if sys.platform == 'darwin':
            camera_utils.pump_macos_runloop(duration_sec=0.1, iterations=5)
        
        if err != EDS_ERR_OK:
            self._send_error(f"Failed to open session with camera (Error code: {err} / 0x{err:04x})", 
                           code=err, 
                           source_func="_handle_connect_command",
                           recovery_hint="Check camera is in PTP mode and not connected to other software")
            with self._event_lock:
                self.edsdk.EdsRelease(temp_camera) # Release the camera ref if session failed
            return

        self.camera = temp_camera
        self.session_open = True
        self._send_log("Camera session opened successfully.")

        # Set event handlers now that we have a camera object and an open session
        with self._event_lock:
            self._handler_context = ctypes.py_object(self)
            context_ptr = self._handler_context
            self._send_log("Registering event handlers...")
            # Set state event handler
            err = self.edsdk.EdsSetCameraStateEventHandler(self.camera, 0, self._state_handler, context_ptr)
            if err != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to set state event handler after session open: {err}")
            
            # Set property event handler
            err = self.edsdk.EdsSetPropertyEventHandler(self.camera, 0, self._property_handler, context_ptr)
            if err != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to set property event handler after session open: {err}")

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
                    model_name = product_name_str.value.decode('utf-8', errors='ignore').strip()
                    info["model"] = model_name if model_name else "Unknown"
                else:
                    info["model"] = "Unknown"
            
            # Serial Number (BodyIDEx)
            serial_str = ctypes.create_string_buffer(256)
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_BodyIDEx, 0, 256, serial_str) == EDS_ERR_OK:
                    serial_num = serial_str.value.decode('utf-8', errors='ignore').strip()
                    info["serial"] = serial_num if serial_num else "Unknown"
                else:
                    info["serial"] = "Unknown"

            # Firmware Version
            firmware_str = ctypes.create_string_buffer(256)
            with self._event_lock:
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_FirmwareVersion, 0, 256, firmware_str) == EDS_ERR_OK:
                    firmware_ver = firmware_str.value.decode('utf-8', errors='ignore').strip()
                    info["firmware"] = firmware_ver if firmware_ver else "Unknown"
                else:
                    info["firmware"] = "Unknown"
            
            self._send_log(f"Camera Info Retrieved: {info.get('model', 'N/A')} (S/N: {info.get('serial', 'N/A')})")
            return info
        except Exception as e:
            self._send_error(f"Error getting camera info: {e}", source_func="_get_camera_info_internal")
            return {"model": "Unknown", "serial": "Unknown", "firmware": "Unknown"}

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
                if self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_AEMode, 0, ctypes.sizeof(ae_mode), ctypes.byref(ae_mode)) == EDS_ERR_OK:
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
            status_dict = status_obj.to_dict()
            # Override live_view_status with actual worker state, not just output_device flag
            # This fixes the bug where output_device check returns "inactive" even when live view is running
            status_dict["live_view_status"] = "active" if self.live_view_active else "inactive"
            self._send_data(MSG_STATUS_UPDATE, status_dict)
        else:
            self._send_data(MSG_STATUS_UPDATE, CameraStatus().to_dict()) # Send default if error

    def _get_camera_mode_string(self, ae_mode_value):
        """Convert AE mode numerical value to human-readable string."""
        mode_map = {
            0: "Auto",
            1: "Program (P)",
            2: "Tv (Shutter Priority)",
            3: "Av (Aperture Priority)", 
            4: "Manual (M)",
            5: "A-DEP",
            6: "DEP",
            7: "Custom (C1/C2)",
            8: "Portrait",
            9: "Landscape", 
            10: "Close-up",
            11: "Sports",
            12: "Night Portrait",
            13: "Children & Pets",
            14: "Creative Auto",
            15: "Movie",
            16: "Photo",
            17: "Scene Intelligent Auto",
            # Add more as needed
        }
        return mode_map.get(ae_mode_value, f"Unknown Mode ({ae_mode_value})")

    def _handle_start_live_view_command(self):
        """
        Canonical EDSDK live view initialization following official documentation.
        
        CRITICAL: Must process events between property changes to allow camera to 
        acknowledge and apply settings. This is required by EDSDK specification.
        """
        if not self.camera or not self.session_open:
            self._send_error("Cannot start live view: Not connected.", source_func="_handle_start_live_view_command")
            return
        if self.live_view_active:
            self._send_log("Live view is already active.")
            return

        try:
            self._send_log("🎬 Starting live view using canonical EDSDK pattern...")

            # Check camera's current shooting mode first for diagnostics
            ae_mode = ctypes.c_uint32()
            with self._event_lock:
                err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_AEMode, 0, 
                                                  ctypes.sizeof(ae_mode), ctypes.byref(ae_mode))
            if err == EDS_ERR_OK:
                mode_str = self._get_camera_mode_string(ae_mode.value)
                self._send_log(f"📷 Camera mode: {mode_str}")

            # Step 0: Process events to ensure camera is in clean state
            # Per Canon SAMPLE10, we don't need to disable EVF mode
            self._send_log("Preparing camera for live view...")
            self._process_events()
            time.sleep(RECOVERY_DELAY_SHORT)

            # Step 1: Set EVF output device to include PC (per Canon Sample10)
            if not self._configure_evf_output_for_pc():
                self._send_error("Failed to configure EVF output for PC streaming.",
                                 source_func="_handle_start_live_view_command",
                                 recovery_hint="Check USB connection and retry Connect + Start Live View.")
                return

            # Step 2: Process events to ensure camera is ready
            # Per Canon SAMPLE10, we don't need to set Evf_Mode explicitly
            # Setting the output device to PC is sufficient to enable live view
            self._send_log("Processing events to prepare for live view...")
            
            # Give camera time to process the output device change
            for _ in range(10):
                self._process_events()
                time.sleep(0.05)
            
            # Additional macOS run loop processing
            camera_utils.pump_macos_runloop(duration_sec=0.1, iterations=5)
            
            # Final event processing
            self._process_events()
            time.sleep(RECOVERY_DELAY_MEDIUM)
            self._process_events()

            # Live view is now active. The camera is ready for frame downloads.
            # Frame capture is handled by _capture_live_frame_internal.
            self.live_view_active = True
            self._send_log("✅ Live view started! Camera ready for frame downloads.")
            self._send_data(MSG_STATUS_UPDATE, {"live_view_status": "active"})

        except Exception as e:
            self.live_view_active = False
            self._send_error(f"Exception starting live view: {e}", source_func="_handle_start_live_view_command")

    def _revert_live_view_settings_on_failure(self, original_evf_output_device_target=1):
        """Simple live view settings revert to match simplified approach."""
        if not self.camera or not self.session_open or not self.edsdk:
            return

        try:
            self._send_log("Reverting live view settings...")
            
            # Set EVF output back to camera LCD
            output_device = ctypes.c_uint32(original_evf_output_device_target)
            with self._event_lock:
                self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0,
                                            ctypes.sizeof(output_device), ctypes.byref(output_device))
            
            self._send_log("Live view settings reverted.")
            
        except Exception as ex:
            self._send_error(f"Exception during revert: {ex}", source_func="_revert_live_view_settings_on_failure")


    def _handle_stop_live_view_command(self):
        """
        Stop live view and revert camera to default state.
        
        Per Canon SAMPLE10: Only manage kEdsPropID_Evf_OutputDevice.
        The camera automatically manages EVF mode internally.
        """
        if not self.camera or not self.session_open:
            self.live_view_active = False
            return
        if not self.live_view_active:
            self._send_log("Live view is already inactive.")
            return

        try:
            self._send_log("Stopping live view...")
            
            # ONLY revert EVF output device to Camera LCD (per Canon documentation)
            # The camera automatically handles EVF mode when we change this
            output_device = ctypes.c_uint32(0x01)  # Camera LCD only
            with self._event_lock:
                err = self.edsdk.EdsSetPropertyData(
                    self.camera, kEdsPropID_Evf_OutputDevice, 0, 
                    ctypes.sizeof(output_device), ctypes.byref(output_device)
                )
            
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to revert EVF output device (Error: {err})", 
                               code=err, source_func="_handle_stop_live_view_command")
            
            # Process events to let camera apply changes
            self._send_log("Processing events after EVF output device change...")
            for _ in range(10):
                self._process_events()
                time.sleep(0.05)
            
            camera_utils.pump_macos_runloop(duration_sec=0.1, iterations=5)

            self.live_view_active = False
            self._send_log("✅ Live view stopped successfully.")
            self._send_data(MSG_STATUS_UPDATE, {"live_view_status": "inactive"})

        except Exception as e:
            self._send_error(f"Exception stopping live view: {e}", source_func="_handle_stop_live_view_command")
            self.live_view_active = False


    def _capture_live_frame_internal(self):
        """Captures live view frame using canonical EDSDK pattern. Called by worker thread."""
        if not self.camera or not self.session_open or not self.live_view_active:
            return

        # Debug: Log first capture attempt and track performance
        if not hasattr(self, '_capture_attempt_logged'):
            self._send_log("🎥 Starting frame capture loop...")
            self._capture_attempt_logged = True
            self._frame_count = 0
            self._notready_count = 0

        stream = ctypes.c_void_p()
        evf_image_ref = ctypes.c_void_p()
        image_data_ptr = ctypes.c_void_p()
        image_length = ctypes.c_uint32()

        try:
            # Step 1: Create memory stream (as per Canon docs)
            with self._event_lock:
                err = self.edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to create memory stream (Error: {err})", code=err, source_func="_capture_live_frame_internal")
                return

            # Step 2: Create EVF image reference (CANONICAL EDSDK PATTERN)
            # From Canon docs: "Creates an object used to get the live view image data set"
            with self._event_lock:
                err = self.edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image_ref))
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to create EVF image reference (Error: {err})", code=err, source_func="_capture_live_frame_internal")
                if stream:
                    with self._event_lock:
                        self.edsdk.EdsRelease(stream)
                return

            # Step 3: Download EVF image using correct Canon API
            # From Canon docs: "EdsDownloadEvfImage(EdsCameraRef inCameraRef, EdsEvfImageRef inEvfImageRef)"
            # Note: "Be sure to retry if EDS_ERR_OBJECT_NOTREADY is returned"
            with self._event_lock:
                err = self.edsdk.EdsDownloadEvfImage(self.camera, evf_image_ref)
            if err != EDS_ERR_OK:
                if err == EDS_ERR_OBJECT_NOTREADY or err == 0x0000A102:  
                    # Per Canon docs: "OBJECT_NOTREADY returns when the image data set is not ready"
                    # This is normal - camera doesn't have a new frame yet
                    # Track for performance monitoring
                    self._notready_count += 1
                    if self._notready_count % 100 == 0:
                        ratio = self._frame_count / max(self._notready_count, 1) * 100
                        self._send_log(f"📊 Performance: {self._frame_count} frames, {self._notready_count} not-ready ({ratio:.1f}% success rate)")
                else:
                    # Only log unexpected errors once
                    if not hasattr(self, '_download_error_logged') or self._download_error_logged != err:
                        self._send_error(f"Failed to download EVF image (Error: {err} / 0x{err:04x})", 
                                       code=err, source_func="_capture_live_frame_internal")
                        self._download_error_logged = err
                self._cleanup_evf_resources(stream, evf_image_ref)
                return

            # Step 4: Extract image data from stream (Canon pattern)
            with self._event_lock:
                self.edsdk.EdsGetPointer(stream, ctypes.byref(image_data_ptr))
                self.edsdk.EdsGetLength(stream, ctypes.byref(image_length))

            if image_data_ptr and image_length.value > 0:
                # Copy image data and send to queue
                frame_data = ctypes.string_at(image_data_ptr, image_length.value)
                self._send_data(MSG_LIVE_FRAME, {"frame_data": frame_data, "timestamp": time.time()})
                
                # Track successful frames
                self._frame_count += 1
                
                # Log first successful frame capture
                if self._frame_count == 1:
                    self._send_log(f"📸 First frame captured! Size: {image_length.value} bytes")
                elif self._frame_count % 100 == 0:
                    self._send_log(f"📊 {self._frame_count} frames captured successfully")
            
            self._cleanup_evf_resources(stream, evf_image_ref)

        except Exception as e:
            self._send_error(f"Exception in live frame capture: {e}", source_func="_capture_live_frame_internal")
            self._cleanup_evf_resources(stream, evf_image_ref)

    def _cleanup_evf_resources(self, stream=None, evf_image_ref=None):
        """Clean up EVF resources following Canon's resource management pattern."""
        try:
            if evf_image_ref:
                with self._event_lock:
                    self.edsdk.EdsRelease(evf_image_ref)
            if stream:
                with self._event_lock:
                    self.edsdk.EdsRelease(stream)
        except Exception as e:
            # Resource cleanup should never fail, but log if it does
            self._send_error(f"Exception during EVF resource cleanup: {e}", source_func="_cleanup_evf_resources")


    def _handle_disconnect_command(self, called_by_shutdown=False):
        """Handles camera disconnection. Called by worker thread."""
        self._send_log("Disconnect command received.")
        if self.live_view_active:
            self._handle_stop_live_view_command() # Try to stop live view first

        if self.camera and self.session_open:
            try:
                # Unregister event handlers before closing the session to prevent callbacks on invalid objects
                with self._event_lock:
                    self._send_log("Unregistering event handlers before closing session...")
                    self.edsdk.EdsSetCameraStateEventHandler(self.camera, 0, None, None)
                    self.edsdk.EdsSetPropertyEventHandler(self.camera, 0, None, None)

                # CRITICAL: EdsCloseSession must NOT hold the event lock!
                # It may require macOS runloop to pump events, causing deadlock with _process_events()
                self.edsdk.EdsCloseSession(self.camera)
                self._send_log("Camera session closed.")
                
                # CRITICAL: Process events after closing session to ensure camera acknowledges
                self._send_log("Processing events after session close...")
                for _ in range(20):  # 1 second of event processing
                    self._process_events()
                    time.sleep(0.05)
                camera_utils.pump_macos_runloop(duration_sec=0.1, iterations=5)
                
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
        self._handler_context = None
        if not called_by_shutdown: # Don't send if part of full worker shutdown sequence
            self._send_data(MSG_CONNECTION_STATUS, {"status": "disconnected", "message": "Camera disconnected."})


    def _worker_shutdown_cleanup(self):
        """Cleans up SDK resources when worker thread is stopping."""
        self._send_log("Worker thread shutting down. Cleaning up resources...")
        
        # First, properly disconnect the camera
        self._handle_disconnect_command(called_by_shutdown=True)

        # CRITICAL: Do comprehensive cleanup BEFORE terminating SDK
        # The camera_utils function needs a valid SDK reference
        if self.edsdk:
            camera_utils.disconnect_and_cleanup_camera_resources(
                self.edsdk, self.camera, self.session_open, self.live_view_active,
                send_log_func=self._send_log, send_error_func=self._send_error, event_lock=self._event_lock
            )

        # NOW terminate SDK after cleanup is done
        if self.edsdk:
            try:
                with self._event_lock:
                    err = self.edsdk.EdsTerminateSDK()
                if err == EDS_ERR_OK:
                    self._send_log("EDSDK terminated successfully.")
                else:
                    self._send_log(f"Warning: EdsTerminateSDK returned error: {err}. This might be okay on macOS if resources were released.")
            except Exception as e:
                self._send_error(f"Exception during EdsTerminateSDK: {e}", source_func="_worker_shutdown_cleanup")
        
        self.edsdk = None
        self._send_log("Worker shutdown cleanup complete.")
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
        # Don't artificially limit FPS - let camera throttle naturally via OBJECT_NOTREADY
        # Camera will return frames at its natural rate (typically 30-60 FPS for Canon)
        live_view_frame_interval = 1.0 / 60  # Poll at 60 FPS, camera will throttle naturally

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
                # Minimal delay - let camera throttle via OBJECT_NOTREADY per Canon docs
                time.sleep(live_view_frame_interval) 

            # Periodic status check (e.g., every 2 seconds)
            current_time = time.time()
            if self.camera and self.session_open and (current_time - last_status_check_time > 2.0):
                status_obj = self._get_status_internal()
                if status_obj:
                    status_dict = status_obj.to_dict()
                    # Override live_view_status with actual worker state
                    status_dict["live_view_status"] = "active" if self.live_view_active else "inactive"
                    self._send_data(MSG_STATUS_UPDATE, status_dict)
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
