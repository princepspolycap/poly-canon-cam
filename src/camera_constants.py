"""Camera-related constants and shared classes."""

import ctypes
from dataclasses import dataclass

# EDSDK Constants and Error Codes
# Camera Properties
kEdsPropID_ProductName = 0x00000004
kEdsPropID_BodyIDEx = 0x00000101
kEdsPropID_FirmwareVersion = 0x00000003
kEdsPropID_AEModuleMode = 0x00000100 # Auto Exposure Mode (shooting mode)

# EVF Related
kEdsPropID_Evf_Mode = 0x00000501
kEdsEvfMode_Enable = 0x01 # Enable EVF mode
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
EDS_ERR_OBJECT_NOTREADY = 97         # Image data set not ready for live view - CRITICAL FOR EVF
kEdsErr_StreamInternalError = 97      # Stream I/O error (same as OBJECT_NOTREADY)
kEdsErr_ObjectNotReady = 41           # General object not ready
kEdsErr_DeviceBusy = 129              # Device is busy
kEdsErr_DeviceNotFound = 2
kEdsErr_DeviceInvalid = 3
kEdsErr_SessionNotOpen = 8
kEdsErr_SessionAlreadyOpen = 0x00002006
kEdsErr_InvalidParameter = 6
kEdsErr_MemoryFull = 7
kEdsErr_CommunicationError = 41
kEdsErr_BatteryLow = 49
kEdsErr_NotReady = 41
kEdsErr_UnsupportedCommand = 36110  # Command not supported

# EDSDK Event Codes
# Object Events (Examples, add more as needed)
kEdsObjectEvent_DirItemRequestTransfer = 0x00000208,
kEdsObjectEvent_DirItemCreated = 0x00000204,
kEdsObjectEvent_VolumeInfoChanged = 0x00000202,

# Property Events
kEdsPropertyEvent_PropertyChanged = 0x00000103,
kEdsPropertyEvent_PropertyDescChanged = 0x00000104,

# State Events (Examples, add more as needed)
kEdsStateEvent_Shutdown = 0x00000301,
kEdsStateEvent_JobStatusChanged = 0x00000302,
kEdsStateEvent_WillSoonShutDown = 0x00000303,
kEdsStateEvent_ShutDownTimerUpdate = 0x00000304,
kEdsStateEvent_CaptureError = 0x00000305,
kEdsStateEvent_InternalError = 0x00000306,

# EVF Recovery Delays (seconds)
RECOVERY_DELAY_SHORT = 0.1
RECOVERY_DELAY_MEDIUM = 0.2
RECOVERY_DELAY_LONG = 0.5

# Camera reference type
EdsCameraRef = ctypes.c_void_p

# Command Actions for camera worker
CMD_CONNECT = "connect"
CMD_DISCONNECT = "disconnect"
CMD_START_LIVE_VIEW = "start_live_view"
CMD_STOP_LIVE_VIEW = "stop_live_view"
CMD_CAPTURE_FRAME = "capture_frame" # Placeholder for now
CMD_GET_CAMERA_INFO = "get_camera_info"
CMD_GET_STATUS = "get_status"
CMD_SHUTDOWN = "shutdown" # Command to tell worker to clean up and exit

# Message Types for communication from camera worker to GUI
MSG_STATUS_UPDATE = "status_update"
MSG_ERROR = "error"
MSG_WARNING = "warning"
MSG_CAMERA_INFO = "camera_info"
MSG_LIVE_FRAME = "live_frame"
MSG_CONNECTION_STATUS = "connection_status" # e.g., connected, disconnected, sdk_loaded, sdk_initialized, shutdown_complete
MSG_LOG = "log" # For general logging messages from worker

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
    
    def to_dict(self) -> dict:
        """Convert camera status to a dictionary for message passing."""
        return {
            "mode": self.mode,
            "output_device": self.output_device,
            "histogram_status": self.histogram_status,
            "temperature_status": self.temperature_status,
            "zoom_position": self.zoom_position,
            "stream_position": self.stream_position,
            "stream_length": self.stream_length,
            "battery_level": self.battery_level,
            "record_status": self.record_status,
            "time_since_last_frame": self.time_since_last_frame,
            "frames_captured": self.frames_captured,
            "errors_since_start": self.errors_since_start,
            "last_error": self.last_error,
            # Add derived fields for UI convenience
            "live_view_status": "active" if self.output_device & kEdsEvfOutputDevice_PC else "inactive"
        }

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
