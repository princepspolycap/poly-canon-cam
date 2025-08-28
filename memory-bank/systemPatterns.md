# System Patterns and Solutions

## Critical Runtime Information

### How to Run the Application
```bash
cd /Users/princeps/Projects/Poly186/poly-canon-cam
python3.11 app.py  # MUST use Python 3.11 specifically
```

**Why Python 3.11**: 
- ✅ Has tkinter support (required for GUI)
- ✅ Has all required dependencies installed
- ❌ Python 3.13: Missing tkinter, import failures

### Dependency Management
- **Required**: numpy, opencv-python, Pillow, pytest, pytest-cov
- **Optional**: syphon-python (gracefully disabled if missing)
- **Critical**: Use Python 3.11 environment

## Proven Working Patterns

### EDSDK Loading (RESOLVED)
```python
# Pattern: Remove macOS quarantine attributes
xattr -rd com.apple.quarantine "EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework"

# Pattern: Multiple loading strategies
try:
    edsdk = ctypes.CDLL(edsdk_path, mode=ctypes.RTLD_GLOBAL)
except:
    edsdk = ctypes.CDLL(edsdk_path, mode=ctypes.RTLD_LOCAL)
```

### Enhanced Event Processing (RESOLVED)
```python
# Pattern: Intensive event processing after SDK init
for _ in range(60):  # 3 seconds at 50ms intervals
    edsdk.EdsGetEvent()
    time.sleep(0.05)

# Pattern: Additional events after property changes
for _ in range(40):  # 2 seconds of additional processing
    edsdk.EdsGetEvent()
    time.sleep(0.05)
```

### Camera Detection (RESOLVED)
```python
# Pattern: Retry logic with enhanced event processing
for attempt in range(10):
    for _ in range(5):  # Process events before detection
        edsdk.EdsGetEvent()
        time.sleep(0.05)
    
    # Attempt detection
    if camera_found:
        break
    time.sleep(0.5)  # Delay between attempts
```

## Current Issue: Error 97 in Live View

### Problem Description
- **Error**: `EDS_ERR_OBJECT_NOTREADY` during `EdsDownloadEvfImage`
- **Context**: Camera connects successfully, EVF properties set correctly
- **Failure Point**: First attempt to download EVF image

### Working Flow Leading to Error
1. ✅ Camera detected and connected
2. ✅ EVF output device set to 3 (TFT | PC)
3. ✅ PC bit confirmed in EVF device property
4. ✅ Enhanced event processing completed (34 loops)
5. ❌ `EdsDownloadEvfImage` fails with Error 97

### Investigation Areas
- **Camera Mode**: Verify AE Mode 1310479 compatibility with live view
- **EVF State**: Camera EVF may not be ready despite property settings
- **Timing**: May need longer processing delays after property changes
- **Sequence**: Alternative EVF initialization approaches

## Application Architecture Status

```
Component                Status              Notes
─────────────────────────────────────────────────────────
EDSDK Loading           ✅ WORKING          Quarantine fix applied
SDK Initialization      ✅ WORKING          56 events over 3.0s
Camera Detection        ✅ WORKING          Found immediately
Camera Connection       ✅ WORKING          Session established
Property Management     ✅ WORKING          EVF device set correctly
Live View Initialization ❌ ERROR 97        EdsDownloadEvfImage fails
```

## Error Codes Reference

- **Error 97**: `EDS_ERR_OBJECT_NOTREADY` - Object/operation not ready
- **Error 129**: Related to property setting failures during revert
- **Return 0**: Success code for EDSDK operations

## Testing Strategy

### What Works (Keep Using)
- Connection test pattern: `python3 tests/test_camera_connection.py`
- Enhanced event processing with 50ms intervals
- Retry logic for camera operations
- Python 3.11 runtime environment

### Current Focus
- Debug Error 97 in live view download
- Verify camera mode requirements
- Test extended event processing timing
- Alternative EVF initialization sequences

## File Locations

### Core Implementation
- `src/canon_camera_connection.py`: Camera connection logic
- `src/live_view.py`: Live view manager (Error 97 location)
- `app.py`: Main application entry point

### Testing
- `tests/test_camera_connection.py`: Working detection patterns
- `tests/test_edsdk.py`: Basic EDSDK loading verification

### Documentation
- `memory-bank/`: Progress tracking and context
- `docs/`: Camera setup and connection guides

According to the EDSDK documentation, the proper sequence for starting live view is:

1. Read current EVF output device value
2. Set EVF output device with PC bit via bitwise OR: `device |= kEdsEvfOutputDevice_PC`
3. Wait for property change event
4. Enable EVF mode by setting `kEdsPropID_Evf_Mode` to 1
5. Wait for property change event
6. Download EVF image data

## Error Handling Pattern

The code implements a pattern of:
1. Attempt operation
2. Check for specific error codes
3. Revert settings on failure
4. Log detailed information about the failure

## Thread Safety

All EDSDK calls are protected with a lock (`self._event_lock`) to ensure thread safety when interacting with the SDK.
