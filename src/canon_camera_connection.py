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
    MSG_CONNECTION_STATUS, MSG_LOG
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

        EdsStateEventHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
        @EdsStateEventHandler
        def camera_state_callback(event, param, context):
            # This callback runs in an EDSDK internal thread.
            # For now, it's a no-op. If it needs to interact with Python state
            # or send messages, it must do so in a thread-safe manner,
            # potentially by putting items onto a queue processed by the worker.
            # print(f"Camera State Event: {event}, Param: {param}")
            return EDS_ERR_OK
        self._state_handler = camera_state_callback # Keep a reference

        with self._event_lock:
            err = self.edsdk.EdsInitializeSDK()
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to initialize SDK", code=err, source_func="_initialize_sdk")
                return False

            # Set state event handler (optional but good practice)
            # Passing None for context as this callback is simple.
            err = self.edsdk.EdsSetCameraStateEventHandler(None, 0, self._state_handler, None)
            if err != EDS_ERR_OK:
                self._send_log(f"Warning: Failed to set state event handler: {err}")
            
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
            # Set EVF output device to PC
            self._send_log("Setting EVF output device to PC...")
            output_device = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
            with self._event_lock:
                err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(output_device), ctypes.byref(output_device))
            
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to set EVF output device to PC (Error: {err}).", code=err, source_func="_handle_start_live_view_command")
                return
            self._send_log(f"Successfully set EVF output device to PC (Result: {err}).")

            # Enable EVF mode
            self._send_log("Enabling EVF mode...")
            evf_mode = ctypes.c_uint32(kEdsEvfMode_Enable)
            with self._event_lock:
                err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_Mode, 0, ctypes.sizeof(evf_mode), ctypes.byref(evf_mode))
            
            if err != EDS_ERR_OK:
                self._send_error(f"Failed to enable EVF mode (Error: {err}).", code=err, source_func="_handle_start_live_view_command")
                # Attempt to revert output device if EVF mode fails
                self._send_log("Attempting to revert EVF output device due to EVF mode failure...")
                output_device.value = 0 # Typically 0 is Camera LCD
                with self._event_lock:
                    revert_err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(output_device), ctypes.byref(output_device))
                if revert_err != EDS_ERR_OK:
                    self._send_log(f"Warning: Failed to revert EVF output device (Error: {revert_err}).")
                else:
                    self._send_log("Successfully reverted EVF output device.")
                return
            self._send_log(f"Successfully enabled EVF mode (Result: {err}).")
            
            self.live_view_active = True
            self._send_log("Live view started successfully (live_view_active set to True).")
            self._send_data(MSG_STATUS_UPDATE, {"live_view_status": "active"})

        except Exception as e:
            self.live_view_active = False
            self._send_error(f"Exception starting live view: {e}", source_func="_handle_start_live_view_command")

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
