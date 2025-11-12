# Quick Start Guide - Canon Camera Live View

## Prerequisites

1. **Canon Camera**: Connected via USB and powered on
2. **Python 3.11**: Required for tkinter support
3. **Virtual Environment**: Activated (`.venv`)

## Running the Application

```bash
cd /Users/princeps/Projects/Poly186/poly-canon-cam
python3.11 app.py
```

## Using the Application

1. **Click "Connect & Start Live View"** 
   - This single button will:
     - Connect to the camera
     - Initialize EDSDK
     - Automatically start live view
     - Display the live camera feed

2. **Stop Live View** (if needed)
   - Click "Stop Live View" to stop streaming while staying connected

3. **Disconnect Camera**
   - Click "Disconnect Camera" to fully disconnect and clean up

## What Was Fixed

### Error 129 (Device Busy) - RESOLVED ✅

**Problem**: Camera would reject live view with Error 129  
**Cause**: We were explicitly setting `kEdsPropID_Evf_Mode` which caused conflicts  
**Solution**: Follow Canon SAMPLE10 - only set `kEdsPropID_Evf_OutputDevice` with PC bit

### Combined Button - IMPLEMENTED ✅

**Before**: Two separate buttons (Connect, then Start Live View)  
**After**: Single "Connect & Start Live View" button for better UX

## Expected Behavior

```
[21:26:30] Connecting to camera...
[21:26:30] No active camera worker, creating new one.
[21:26:33] Connection Status: sdk_loaded - EDSDK loaded successfully.
[21:26:36] Connection Status: sdk_initialized - SDK initialized.
[21:26:37] Connection Status: connected - Camera connected successfully.
[21:26:37] Starting live view...
[21:26:38] 🎬 Starting live view using canonical EDSDK pattern...
[21:26:38] 📷 Camera mode: Auto
[21:26:38] Preparing camera for live view...
[21:26:38] Processing events to prepare for live view...
[21:26:39] ✅ Live view started! Camera ready for frame downloads.
```

## Troubleshooting

### Camera Not Detected

```bash
# Run cleanup script
bash test_camera_with_cleanup.sh

# Check camera is in PTP mode
# Power cycle camera
# Try different USB cable/port
```

### Import Errors

```bash
# Ensure using Python 3.11
python3.11 --version

# Reinstall dependencies
pip install -r requirements.txt
```

### GUI Issues

- Use `Cmd+Tab` to bring window to front on macOS
- Check System Preferences > Security for EDSDK framework approval

## Key Technical Details

- **No explicit EVF mode setting**: Canon's SDK handles this automatically
- **Event processing**: Enhanced event loop processing for reliable camera detection
- **Auto-start**: Live view automatically starts after connection succeeds

## Files Modified

- `src/canon_camera_connection.py`: Removed EVF mode explicit setting
- `src/gui.py`: Combined connect and live view buttons
- `src/gui_style.py`: Added missing style functions
- `src/camera_constants.py`: Fixed message constant definitions
- `app.py`: Updated command references

See `LIVE_VIEW_FIX_SUMMARY.md` for complete technical details.

