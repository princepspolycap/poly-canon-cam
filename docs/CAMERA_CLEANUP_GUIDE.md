# Camera Connection Cleanup & Troubleshooting Guide

## Current USB State (November 11, 2025)

### Camera Detection
- **Device**: Canon Digital Camera (vendor 1193, Canon Inc.)
- **Connection**: USB-C (SuperSpeed, Device Speed 3)
- **LocationID**: 0x01200000
- **Configuration**: 1 active
- **PTP Interface**: Available
- **PC Output Status**: Currently disabled by macOS

### System Issues Identified

1. **macOS Image Services Lock**
   - `PTPCamera` process captures Canon devices
   - `Image Capture Extension` maintains camera lock
   - These must be killed before SDK can access camera
   - They respawn automatically after reconnection

2. **USB Hub/Dock Interference**
   - Realtek BillBoard Device detected on same controller
   - May cause delays in re-enumeration
   - Can interfere with camera state transitions

3. **Generic Serial String**
   - Camera identifies as generic "Canon Digital Camera"
   - No unique identifier if multiple cameras connected
   - Can cause reconnection logic confusion

## Pre-Test Cleanup Steps

### Step 1: Kill macOS Image Services
```bash
# Run these commands just before launching app/tests
sudo killall PTPCamera
sudo killall "Image Capture Extension"
```

### Step 2: Verify USB State
```bash
# Check camera is visible and properly configured
ioreg -p IOUSB -l | grep -A 20 "Canon Digital Camera"

# Expected output should show:
# - "kUSBProductString" = "Canon Digital Camera"
# - "Device Speed" = 3 (SuperSpeed)
# - "kUSBCurrentConfiguration" = 1
# - Location under AppleT8122USBXHCI (or similar controller)
```

### Step 3: Optional - Direct Connection
If using USB hub/dock:
- Disconnect camera from hub
- Connect directly to Mac USB-C port
- This removes Realtek billboard device interference
- Gives SDK exclusive controller access

### Step 4: Power Cycle If Stuck
```bash
# Full reset procedure:
1. Power off camera completely
2. Unplug USB-C cable
3. Wait 10 seconds
4. Power on camera
5. Reconnect USB-C cable
6. Verify with: ioreg -p IOUSB -l | grep -A 5 "Canon"
7. Wait for "Device Speed 3" and "kUSBCurrentConfiguration" = 1
8. Then run test
```

## Testing Procedure

### Quick Test After Cleanup
```bash
cd /Users/princeps/Projects/Poly186/poly-canon-cam

# Kill image services
sudo killall PTPCamera
sudo killall "Image Capture Extension"

# Verify USB state
ioreg -p IOUSB -l | sed -n '320,360p'

# Run comprehensive test
python3.11 tests/test_camera_connection.py

# Run application
python3.11 app.py
```

### What to Look For in Logs

**Success Indicators:**
- ✅ Camera detected by EDSDK (not just USB level)
- ✅ Session opens successfully
- ✅ Camera state inspection shows valid values
- ✅ EVF Mode: 0 or 1 (not 2)
- ✅ EVF Output Device: has PC bit (0x02) or can be set
- ✅ AE Mode: 0x00-0x3F or 0xFFFFFFFF (not abnormal values)

**Failure Indicators:**
- ❌ `EdsProcessEvent` symbol not found → Framework build issue
- ❌ EVF Mode = 2 → Camera in bad state, needs power cycle
- ❌ AE Mode > 0x3F (except 0xFFFFFFFF) → Uninitialized memory
- ❌ Error 129 persists → Event processing still needed

## Implementation Changes Made

### File: `src/canon_camera_connection.py`

**Changes:**
1. Added recovery timing imports: `RECOVERY_DELAY_SHORT`, `RECOVERY_DELAY_MEDIUM`
2. Enhanced `_handle_start_live_view_command()`:
   - Added event processing after setting EVF output device
   - Added event processing after enabling EVF mode
   - Improved error messages and recovery hints
3. Enhanced `_handle_stop_live_view_command()`:
   - Added proper event processing between steps
   - Added delays for state transitions
   - Better error handling for cleanup

**Key Addition:**
```python
# CRITICAL: Process events between property changes
self._process_events()
time.sleep(RECOVERY_DELAY_MEDIUM)
self._process_events()
```

## Expected Results After Fix

### With Proper Cleanup & Fix
```
[Startup] Checking for existing Canon camera processes...
[Startup] ✅ All Python dependencies available
[Startup] ✅ Found EDSDK
[Startup] ✅ System cleanup completed
[Startup] 🚀 Starting GUI application...

[When clicking Connect Camera]
✅ Camera session opened successfully
✅ Extended camera shutdown timer
✅ Set camera to save images to host

[When clicking Start Live View]
🎬 Starting live view using canonical EDSDK pattern...
📷 Camera mode: Auto
Setting EVF output device to PC...
Processing events after EVF output device change...
Enabling EVF mode...
Processing events after EVF mode enable...
✅ Live view started! Camera ready for frame downloads.
```

### Error 129 Resolution
**Before Fix:**
```
[20:05:43] ERROR: Camera mode doesn't support live view (Error: 129)
```

**After Fix with Cleanup:**
```
Processing events after EVF output device change...
Enabling EVF mode...
Processing events after EVF mode enable...
✅ Live view started!
```

## If Error 129 Still Occurs

**Diagnostic Steps:**
1. Verify cleanup killed image services:
   ```bash
   ps aux | grep -i "PTPCamera\|Image Capture"
   ```
2. Check camera USB state is stable:
   ```bash
   ioreg -p IOUSB -l | grep "Canon" -A 10
   ```
3. Enable verbose logging in app.py:
   ```bash
   python3.11 app.py --verbose
   ```
4. Check if EdsProcessEvent symbol is available:
   ```bash
   nm /path/to/EDSDK | grep EdsProcessEvent
   ```

## Files Modified

- `src/canon_camera_connection.py` - Added event processing + timing
- `tests/test_camera_connection.py` - Integrated camera state inspection
- `ANALYSIS_LIVE_VIEW_ERROR_129.md` - Root cause analysis (documentation)

## Files Removed

- `test_camera_state.py` - Consolidated into test_camera_connection.py

---

**Status**: Implementation complete, awaiting camera connection for full testing
**Confidence**: 85% (high) that event processing fix resolves Error 129
**Next Step**: Connect camera and run cleanup procedure, then test
