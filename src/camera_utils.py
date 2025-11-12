import os
import platform
import time
import subprocess
import ctypes # Required for EDSDK and CoreFoundation types

# Import EDSDK constants - assuming they are in camera_constants
# We need these for the new disconnect_and_cleanup_camera_resources function
from .camera_constants import (
    EDS_ERR_OK, kEdsPropID_Evf_Mode, kEdsPropID_Evf_OutputDevice
)

# CoreFoundation symbols for macOS run loop pumping
_CFRunLoopRunInMode = None
_CFStringCreateWithCString = None
_CFRelease = None
_kCFAllocatorDefault = None
_corefoundation_loaded = False
_kCFStringEncodingUTF8 = 0x08000100


def _ensure_corefoundation_loaded():
    """Lazy-load CoreFoundation symbols required for run loop pumping."""
    global _corefoundation_loaded, _CFRunLoopRunInMode, _CFStringCreateWithCString, _CFRelease, _kCFAllocatorDefault
    if _corefoundation_loaded:
        return
    cf_path = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    cf = ctypes.CDLL(cf_path)
    _CFRunLoopRunInMode = cf.CFRunLoopRunInMode
    _CFRunLoopRunInMode.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
    _CFRunLoopRunInMode.restype = ctypes.c_int32

    _CFStringCreateWithCString = cf.CFStringCreateWithCString
    _CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    _CFStringCreateWithCString.restype = ctypes.c_void_p

    _CFRelease = cf.CFRelease
    _CFRelease.argtypes = [ctypes.c_void_p]
    _CFRelease.restype = None

    _kCFAllocatorDefault = ctypes.c_void_p.in_dll(cf, "kCFAllocatorDefault")
    _corefoundation_loaded = True


def pump_macos_runloop(duration_sec=0.1, iterations=1, mode="kCFRunLoopDefaultMode", log_func=None):
    """
    Run the macOS run loop for a short period, as recommended by Canon's documentation
    for reliable camera detection on Ventura/Sonoma (see "Notes on Developing Macintosh Applications").
    """
    log_fn = log_func if callable(log_func) else None

    if platform.system() != "Darwin":
        # On other OSes, a simple sleep is sufficient
        time.sleep(duration_sec * max(iterations, 1))
        return

    try:
        _ensure_corefoundation_loaded()
    except Exception as exc:
        if log_fn:
            log_fn(f"[CameraUtils] Failed to load CoreFoundation symbols: {exc}. Falling back to sleep.")
        time.sleep(duration_sec * max(iterations, 1))
        return

    mode_bytes = mode.encode("utf-8")
    for idx in range(max(iterations, 1)):
        try:
            mode_ref = _CFStringCreateWithCString(_kCFAllocatorDefault, mode_bytes, _kCFStringEncodingUTF8)
            if mode_ref:
                _CFRunLoopRunInMode(mode_ref, ctypes.c_double(duration_sec), False)
                _CFRelease(mode_ref)
            else:
                time.sleep(duration_sec)
            if log_fn:
                log_fn(f"[CameraUtils] macOS runloop pulse {idx + 1}/{iterations}")
        except Exception as exc:
            if log_fn:
                log_fn(f"[CameraUtils] Runloop pulse error: {exc}")
            time.sleep(duration_sec)


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

    # CRITICAL: Kill PTPCamera process that locks Canon devices
    try:
        if verbose:
            send_log_func_internal("[CameraUtils] Attempting to kill PTPCamera process...")
        result = subprocess.run(["killall", "PTPCamera"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            if verbose:
                send_log_func_internal("[CameraUtils] ✅ PTPCamera process killed successfully.")
            time.sleep(0.5)
        else:
            if verbose:
                send_log_func_internal("[CameraUtils] ℹ️  PTPCamera not running (or already terminated).")
    except Exception as e:
        if verbose:
            send_log_func_internal(f"[CameraUtils] Exception killing PTPCamera: {e}")

    # CRITICAL: Kill Image Capture Extension that maintains camera lock
    try:
        if verbose:
            send_log_func_internal("[CameraUtils] Attempting to kill Image Capture Extension...")
        result = subprocess.run(["killall", "Image Capture Extension"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            if verbose:
                send_log_func_internal("[CameraUtils] ✅ Image Capture Extension killed successfully.")
            time.sleep(0.5)
        else:
            if verbose:
                send_log_func_internal("[CameraUtils] ℹ️  Image Capture Extension not running (or already terminated).")
    except Exception as e:
        if verbose:
            send_log_func_internal(f"[CameraUtils] Exception killing Image Capture Extension: {e}")

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
        send_log_func_internal("[CameraUtils] ✅ macOS camera connection cleanup actions complete.")


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
