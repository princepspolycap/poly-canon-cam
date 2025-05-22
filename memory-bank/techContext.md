# Technical Context for Canon Camera SDK Implementation

## Development Environment

- macOS-based system
- Python application using ctypes for EDSDK interfacing
- Canon EDSDK 13.19.0 Macintosh version

## External Dependencies

- Canon EDSDK: The primary SDK for camera interaction
- ctypes: Python library for interfacing with C-based SDKs

## Key Constants from SDK

- `kEdsEvfOutputDevice_PC` = 2 (bit value for PC output)
- `kEdsEvfOutputDevice_TFT` = 1 (bit value for camera LCD)
- `kEdsEvfMode_Enable` = 1 (value to enable EVF mode)
- Error codes:
  - `EDS_ERR_OK` = 0 (success)
  - `EDS_ERR_INVALID_FN_CALL` = 129 (function called in an invalid state)
  - `EDS_ERR_OBJECT_NOTREADY` = 0x00008D04 (object not ready for operation)

## Implementation Notes

- EDSDK requires calling `EdsSetPropertyData` with `kEdsPropID_Evf_OutputDevice` before enabling EVF mode
- The EDSDK documentation specifically states to use bitwise OR when setting the output device to preserve existing flags
- Events must be processed after property changes to ensure the camera's state is updated
- Camera state transitions can take time and require waiting for property change events
