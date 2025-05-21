import os
import platform
import time
import subprocess
import ctypes # Required for EDSDK types

# Import EDSDK constants - assuming they are in camera_constants
# We need these for the new disconnect_and_cleanup_camera_resources function
from .camera_constants import (
    EDS_ERR_OK, kEdsPropID_Evf_Mode, kEdsPropID_Evf_OutputDevice
)

def cleanup_macos_camera_connection(extra_kill_canon_processes=True, verbose=True, send_log_func=print):
    """
    Robustly clean up macOS USB and Canon camera connection state.

    - On macOS, sends HUP to the USB daemon (`usbd`) to reset USB state.
    - Optionally kills Canon EOS Webcam Utility background processes, which can block exclusive camera access.
    - Waits a short time for the OS to reset USB state.

    This should be called before attempting a new camera connection, especially after a crash or failed connection.

    Args:
        extra_kill_canon_processes (bool): If True, will also kill Canon webcam background processes.
        verbose (bool): If True, prints status messages via send_log_func.
        send_log_func (callable): Function to use for logging messages.
    Returns:
        None
    """
    send_log_func_internal = send_log_func if callable(send_log_func) else print
    
    if platform.system() != "Darwin":
        if verbose:
            send_log_func_internal("[CameraUtils] cleanup_macos_camera_connection: Not macOS, skipping USB daemon reset.")
        return
    
    send_log_func_internal("[CameraUtils] Starting macOS-specific cleanup...")

    # Reset macOS USB daemon
    try:
        if verbose:
            send_log_func_internal("[CameraUtils] Attempting to reset macOS USB daemon (usbd)...")
        # Use subprocess for better control and error handling if needed in future
        result = subprocess.run(["killall", "-HUP", "usbd"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            if verbose:
                send_log_func_internal("[CameraUtils] macOS USB daemon (usbd) reset successfully.")
        else:
            if verbose:
                send_log_func_internal(f"[CameraUtils] Failed to reset usbd. Return code: {result.returncode}. Stderr: {result.stderr.strip()}")
        time.sleep(2)  # Give the OS a moment to reset USB state
    except Exception as e:
        if verbose:
            send_log_func_internal(f"[CameraUtils] Exception while trying to reset usbd: {e}")

    # Optionally kill Canon EOS Webcam Utility background processes
    if extra_kill_canon_processes:
        try:
            if verbose:
                send_log_func_internal("[CameraUtils] Attempting to kill Canon EOS Webcam Utility background processes (if any)...")
            # Using pkill via subprocess
            result = subprocess.run(['pkill', '-f', "com.canon.cusa.eoswebcam"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                 if verbose:
                    send_log_func_internal("[CameraUtils] Canon EOS Webcam Utility processes killed successfully (if they were running).")
            # pkill exits with 1 if no processes are found, which is not an error in this context.
            elif result.returncode == 1 and ("No matching processes" in result.stderr or not result.stdout):
                 if verbose:
                    send_log_func_internal("[CameraUtils] No Canon EOS Webcam Utility processes found to kill.")
            else: # Other non-zero return codes might indicate an issue
                if verbose:
                    send_log_func_internal(f"[CameraUtils] pkill command for Canon webcam processes finished. Return code: {result.returncode}. Stdout: {result.stdout.strip()}. Stderr: {result.stderr.strip()}")
            time.sleep(1)
        except Exception as e:
            if verbose:
                send_log_func_internal(f"[CameraUtils] Exception while trying to kill Canon webcam processes: {e}")

    if verbose:
        send_log_func_internal("[CameraUtils] macOS camera connection cleanup actions complete.")


def disconnect_and_cleanup_camera_resources(edsdk, camera_ref, session_open, live_view_active,
                                            send_log_func=print, send_error_func=print, event_lock=None):
    """
    Comprehensive function to disconnect from the camera, release EDSDK resources,
    and perform system-level cleanup.

    Args:
        edsdk: The EDSDK library instance.
        camera_ref: The reference to the camera object.
        session_open (bool): True if a camera session is currently open.
        live_view_active (bool): True if live view is currently active.
        send_log_func (callable): Function for logging messages.
        send_error_func (callable): Function for logging error messages.
        event_lock (threading.Lock): Lock for synchronizing EDSDK calls if used in threaded context.
    """
    send_log_func_internal = send_log_func if callable(send_log_func) else print
    send_error_func_internal = send_error_func if callable(send_error_func) else print

    def _sdk_call(func, *args):
        """Wrapper for SDK calls to handle locking if an event_lock is provided."""
        if event_lock:
            with event_lock:
                return func(*args)
        else:
            return func(*args)

    send_log_func_internal("Starting camera disconnection and resource cleanup...")

    if edsdk and camera_ref and live_view_active:
        send_log_func_internal("Stopping live view...")
        try:
            evf_mode_off = ctypes.c_uint32(0)
            err = _sdk_call(edsdk.EdsSetPropertyData, camera_ref, kEdsPropID_Evf_Mode, 0, ctypes.sizeof(evf_mode_off), ctypes.byref(evf_mode_off))
            if err != EDS_ERR_OK:
                send_error_func_internal(f"Failed to disable EVF mode during cleanup: {err}", code=err)
            
            output_device_camera = ctypes.c_uint32(0) # Revert to camera LCD
            err = _sdk_call(edsdk.EdsSetPropertyData, camera_ref, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(output_device_camera), ctypes.byref(output_device_camera))
            if err != EDS_ERR_OK:
                 send_error_func_internal(f"Failed to set EVF output to camera during cleanup: {err}", code=err)
            send_log_func_internal("Live view stopped.")
        except Exception as e:
            send_error_func_internal(f"Exception stopping live view during cleanup: {e}")
        # live_view_active = False # State change handled by caller if needed

    if edsdk and camera_ref and session_open:
        send_log_func_internal("Closing camera session...")
        try:
            err = _sdk_call(edsdk.EdsCloseSession, camera_ref)
            if err != EDS_ERR_OK:
                send_error_func_internal(f"Failed to close camera session: {err}", code=err)
            else:
                send_log_func_internal("Camera session closed.")
        except Exception as e:
            send_error_func_internal(f"Exception closing camera session: {e}")
        # session_open = False # State change handled by caller

    if edsdk and camera_ref:
        send_log_func_internal("Releasing camera object...")
        try:
            released_count = _sdk_call(edsdk.EdsRelease, camera_ref)
            send_log_func_internal(f"Camera object released. Ref count after release: {released_count}")
        except Exception as e:
            send_error_func_internal(f"Exception releasing camera object: {e}")
        # camera_ref = None # State change handled by caller

    if edsdk:
        send_log_func_internal("Terminating EDSDK...")
        try:
            err = _sdk_call(edsdk.EdsTerminateSDK) # No lock needed for TerminateSDK as it's final
            if err != EDS_ERR_OK:
                send_error_func_internal(f"EDSDK termination failed with error: {err}. This might be acceptable on macOS if resources were released.", code=err)
            else:
                send_log_func_internal("EDSDK terminated successfully.")
        except Exception as e:
            send_error_func_internal(f"Exception during EDSDK termination: {e}")
        # edsdk = None # State change handled by caller

    # Perform macOS specific system-level cleanup
    if platform.system() == "Darwin":
        send_log_func_internal("Performing macOS specific system cleanup...")
        cleanup_macos_camera_connection(verbose=True, send_log_func=send_log_func_internal)
    
    send_log_func_internal("Camera disconnection and resource cleanup process finished.")
