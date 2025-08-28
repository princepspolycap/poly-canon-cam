# Technical Context for New Chat Session

## Quick Start Guide

**How to Run**:
```bash
cd /Users/princeps/Projects/Poly186/poly-canon-cam
python3.11 app.py  # Use Python 3.11 specifically
```

**Current Status**: Camera connection ✅ WORKING, Live view ❌ ERROR 97

## What's Working ✅

1. **EDSDK Loading**: Framework loads without macOS security issues
2. **Camera Detection**: Finds camera immediately (enhanced event processing)
3. **Camera Connection**: Session establishment and property management
4. **GUI Application**: Launches and connects to camera reliably

## Current Issue 🎯

**Error 97 in Live View**: `EDS_ERR_OBJECT_NOTREADY` during `EdsDownloadEvfImage`

**Log Evidence** (from latest run):
```
Successfully set ORed EVF output device (Result: 0).
Confirmed EVF output device is: 3 (PC bit is 2)
Enhanced event processing after setting Evf_OutputDevice (up to 2.0s)...
Completed 34 event processing loops after setting Evf_OutputDevice.
ERROR: Priming: Failed to download EVF image (Error: 97) on attempt 1.
```

## Key Technical Details

**Working Patterns**:
- SDK initialization: 56 events over 3.0 seconds
- Camera detection: 1 camera found on first attempt
- EVF property setting: PC bit correctly set (value 3)
- Event processing: 34 additional loops after property change

**Failure Point**: 
- `EdsDownloadEvfImage` returns Error 97 on first attempt
- Property change event times out but setting succeeds
- Camera AE Mode: 1310479 (may need verification)

## Dependencies Status

- ✅ Python 3.11: All dependencies available (tkinter, etc.)
- ✅ Syphon-python: Optional import (gracefully disabled if missing)
- ❌ Python 3.13: Missing tkinter, not recommended

## Investigation Focus

1. **Camera Mode Requirements**: Verify camera mode for live view compatibility
2. **EVF Readiness**: Check if camera EVF is actually ready for downloads
3. **Extended Event Processing**: May need longer processing after property changes
4. **Alternative Sequences**: Test different EVF initialization approaches

## Architecture Overview

```
App (Python 3.11) → EDSDK Framework → Canon Camera
    ✅ GUI              ✅ Loaded         ✅ Connected
    ✅ Events           ✅ Properties     ❌ EVF Download
```

## Files of Interest

- `src/canon_camera_connection.py`: Main camera connection logic
- `src/live_view.py`: Live view manager (Error 97 location)
- `tests/test_camera_connection.py`: Working camera detection patterns
- `app.py`: Main application entry point

## Next Steps for New Chat

Focus on debugging Error 97 in `EdsDownloadEvfImage` - all foundational issues are resolved.
