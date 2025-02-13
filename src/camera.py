import ctypes
import time
from typing import Optional

# Define important EDSDK constants
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

# Define camera object reference type
EdsCameraRef = ctypes.c_void_p 

class CanonCamera:
    def __init__(self):
        self.edsdk = None
        self.camera = None
        self._load_edsdk()
        self._initialize_sdk()

    def _load_edsdk(self):
        """Load the EDSDK library"""
        try:
            self.edsdk = ctypes.CDLL("./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK")
        except Exception as e:
            raise RuntimeError(f"Failed to load EDSDK library: {e}")

    def _initialize_sdk(self):
        """Initialize the SDK"""
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
            raise RuntimeError(f"Failed to get camera list (Error code: {err})")

        count = ctypes.c_uint32()
        err = self.edsdk.EdsGetChildCount(camera_list, ctypes.byref(count))
        if err != EDS_ERR_OK:
            self.edsdk.EdsRelease(camera_list)
            raise RuntimeError(f"Failed to get camera count (Error code: {err})")
        
        print(f"Found {count.value} camera(s)")
        
        if count.value == 0:
            self.edsdk.EdsRelease(camera_list)
            raise RuntimeError("No cameras detected. Please check that:\n" +
                           "1. The camera is turned on\n" +
                           "2. The camera is properly connected via USB\n" +
                           "3. The camera is in the correct mode\n" +
                           "4. Try disconnecting and reconnecting the USB cable")

        print("Attempting to get camera handle...")
        err = self.edsdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera))
        if err != EDS_ERR_OK:
            self.edsdk.EdsRelease(camera_list)
            raise RuntimeError(f"Failed to get camera handle (Error code: {err})")

        self.edsdk.EdsRelease(camera_list)
        return camera

    def connect(self):
        """Connect to the first available camera"""
        if self.camera:
            return
        
        self.camera = self._get_first_camera()
        err = self.edsdk.EdsOpenSession(self.camera)
        if err != EDS_ERR_OK:
            raise RuntimeError(f"Failed to open session: {err}")
            
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
        """Disconnect from the camera and clean up"""
        if self.camera:
            print("Closing session...")
            self.edsdk.EdsCloseSession(self.camera)
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

    def start_live_view(self):
        """Start live view on the camera following official sample"""
        if not self.camera:
            raise RuntimeError("Camera not connected")

        # Lock UI to prevent camera operation conflicts
        err = self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_UILock, 0)
        if err != EDS_ERR_OK:
            print("Warning: Failed to lock camera UI")

        try:
            # Get current output device setting
            device = ctypes.c_uint32()
            err = self.edsdk.EdsGetPropertyData(
                self.camera,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device)
            )
            if err != EDS_ERR_OK:
                raise RuntimeError(f"Failed to get output device: {err}")

            # Add PC as output device (don't overwrite existing settings)
            device = ctypes.c_uint32(device.value | kEdsEvfOutputDevice_PC)
            err = self.edsdk.EdsSetPropertyData(
                self.camera,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device)
            )
            if err != EDS_ERR_OK:
                raise RuntimeError(f"Failed to set output device: {err}")

            # Wait for the change to take effect
            time.sleep(1)
            return err

        finally:
            # Always unlock UI
            self.edsdk.EdsSendCommand(self.camera, kEdsCameraCommand_UIUnLock, 0)

    def create_evf_image(self):
        """Create EVF image reference"""
        evf_image = ctypes.c_void_p()
        err = self.edsdk.EdsCreateMemoryStream(0, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            raise RuntimeError(f"Failed to create memory stream: {err}")
        return evf_image

    def download_evf_image(self, stream) -> Optional[bytes]:
        """Download live view image data following official sample"""
        if not self.camera or not stream:
            return None

        # Create EvfImageRef
        evf_image = ctypes.c_void_p()
        err = self.edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            return None

        try:
            # Download live view image data
            err = self.edsdk.EdsDownloadEvfImage(self.camera, evf_image)
            if err != EDS_ERR_OK:
                return None

            # Get the image data
            image_data = ctypes.c_void_p()
            err = self.edsdk.EdsGetPointer(stream, ctypes.byref(image_data))
            if err != EDS_ERR_OK:
                return None

            # Get data length
            image_len = ctypes.c_ulonglong()
            err = self.edsdk.EdsGetLength(stream, ctypes.byref(image_len))
            if err != EDS_ERR_OK:
                return None

            # Copy the image data
            buffer = (ctypes.c_ubyte * image_len.value).from_address(image_data.value)
            return bytes(buffer)

        finally:
            if evf_image:
                self.edsdk.EdsRelease(evf_image)

    def release_evf_image(self, evf_image):
        """Release EVF image resources"""
        if evf_image:
            self.edsdk.EdsRelease(evf_image)
