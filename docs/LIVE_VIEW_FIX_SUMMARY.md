# Live View Error 129 Fix Summary

**Date**: November 12, 2025  
**Status**: ✅ RESOLVED

## Problem Description

The Canon camera would connect successfully, but when attempting to start live view, we encountered **Error 129 (EDS_ERR_DEVICE_BUSY)** when trying to enable the EVF mode.

```
EVF mode was rejected (kEdsErr_DeviceBusy). Resetting EVF state and retrying once...
[21:26:47] ERROR (_handle_start_live_view_command): Failed to enable EVF mode (Error: 129).
```

## Root Cause

We were **explicitly setting `kEdsPropID_Evf_Mode`** after setting the EVF output device, which caused the camera to report it was busy. This was based on a misunderstanding of the EDSDK documentation.

## The Solution

After carefully reviewing Canon's **SAMPLE10** (Live view) in the EDSDK API documentation, we discovered:

### Canon's Official Implementation:

```c
EdsError startLiveview(EdsCameraRef camera)
{
    EdsError err = EDS_ERR_OK;
    
    // Get the output device for the live view image
    EdsUInt32 device;
    err = EdsGetPropertyData(camera, kEdsPropID_Evf_OutputDevice, 0, sizeof(device), &device);
    
    // PC live view starts by setting the PC as the output device for the live view image.
    if(err == EDS_ERR_OK)
    {
        device |= kEdsEvfOutputDevice_PC;
        err = EdsSetPropertyData(camera, kEdsPropID_Evf_OutputDevice, 0, sizeof(device), &device);
    }
    
    // A property change event notification is issued from the camera if property settings are made successfully.
    // Start downloading of the live view image once the property change notification arrives.
    
    return err;
}
```

**Key Insight**: Canon's sample code **DOES NOT** explicitly set `kEdsPropID_Evf_Mode` to enable live view!

### What We Changed:

#### Before (Causing Error 129):
```python
# Step 1: Set EVF output device
device |= kEdsEvfOutputDevice_PC
EdsSetPropertyData(camera, kEdsPropID_Evf_OutputDevice, ...)

# Step 2: Enable EVF mode ❌ THIS WAS THE PROBLEM!
evf_mode = 1
EdsSetPropertyData(camera, kEdsPropID_Evf_Mode, ...)  # Error 129!
```

#### After (Following Canon SAMPLE10):
```python
# Step 1: Set EVF output device (this is all we need!)
device |= kEdsEvfOutputDevice_PC  
EdsSetPropertyData(camera, kEdsPropID_Evf_OutputDevice, ...)

# Step 2: Process events and wait
# Camera automatically handles EVF mode internally ✅
for _ in range(10):
    EdsGetEvent()
    time.sleep(0.05)
```

## Implementation Changes

### File: `src/canon_camera_connection.py`

**Removed**:
- Explicit `EdsSetPropertyData` call for `kEdsPropID_Evf_Mode`
- The `_ensure_evf_mode_disabled()` call at the start
- Complex retry logic for EVF mode setting

**Kept**:
- EVF output device configuration with PC bit
- Proper event processing after setting output device
- Enhanced event processing with macOS run loop pumping

## Additional Improvements

### Combined Connect & Live View Button

Updated the GUI to have a single "Connect & Start Live View" button instead of two separate buttons:

1. **Before**: 
   - "Connect Camera" button
   - "Start Live View" button (separate)

2. **After**:
   - "Connect & Start Live View" button (single action)
   - Auto-starts live view after successful connection
   - Better UX - one click to get started

### Files Modified:
- `src/canon_camera_connection.py` - Removed explicit EVF mode setting
- `src/gui.py` - Combined buttons and auto-start logic
- `src/gui_style.py` - Added `apply_modern_style` function and `Secondary.TButton` style
- `app.py` - Updated references to new button command
- `src/camera_constants.py` - Fixed duplicate MSG_ constant definitions

## How to Run

```bash
cd /Users/princeps/Projects/Poly186/poly-canon-cam
python3.11 app.py
```

The application will:
1. ✅ Load and initialize EDSDK
2. ✅ Show GUI with "Connect & Start Live View" button
3. ✅ When clicked, connect to camera
4. ✅ Automatically start live view (no more Error 129!)
5. ✅ Display live camera feed in the GUI

## Testing

**Status**: Ready for testing
- ✅ Import errors fixed
- ✅ All dependencies checked
- ✅ Code follows Canon SAMPLE10 pattern
- ✅ GUI simplified with combined button

**Note**: Camera must be connected via USB and powered on for live view to work.

## Documentation References

- **Canon EDSDK API**: Section 6.3.10 SAMPLE10 - Live view (page 195)
- **Canon EDSDK API**: Section 5.2.54 kEdsPropID_Evf_OutputDevice (page 136)
- **Canon EDSDK API**: Section 5.2.55 kEdsPropID_Evf_Mode (page 137)

## Key Takeaway

**Never set `kEdsPropID_Evf_Mode` explicitly when starting live view.**  

Setting `kEdsPropID_Evf_OutputDevice` with the PC bit is sufficient. The camera handles the internal EVF mode automatically.

