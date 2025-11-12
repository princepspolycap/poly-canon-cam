# Deep Analysis: Live View Error 129 (Device Busy)

## 📋 PROBLEM STATEMENT

The application successfully:
- ✅ Loads EDSDK library
- ✅ Initializes SDK
- ✅ Detects camera
- ✅ Opens camera session

But **FAILS at live view** with:
```
Error 129: Camera mode doesn't support live view
```

---

## 🔍 ROOT CAUSE ANALYSIS

### Error 129 = `kEdsErr_DeviceBusy`

**From EDSDK Documentation (5.2.55 kEdsPropID_Evf_Mode):**
```
Description: Gets/sets live view function settings.
Value: 0 = Disable, 1 = Enable
```

**From EDSDK Documentation (5.2.54 kEdsPropID_Evf_OutputDevice):**
```
Description: Starts/ends live view.
The camera TFT and PC to be used as the output device for live view can be specified.
Value:
  0x01 = kEdsEvfOutputDevice_TFT (camera LCD)
  0x02 = kEdsEvfOutputDevice_PC (PC screen)
  0x08 = kEdsEvfOutputDevice_PC_Small (small PC image)
```

---

## 📊 TEST OUTPUT ANALYSIS

**From test_camera_state.py with connected camera:**

```
[AE Mode Value]
  AE Mode Value: 1310479 (0x0013ff0f)
  AE Mode String: Unknown (1310479)
  ⚠️  Value seems abnormally high (>1000)

[EVF (Live View) Mode]
  EVF Mode Value: 2
  EVF Status: ❓ UNKNOWN (2)

[EVF Output Device]
  Output Device Value: 1 (0x01)
  Output Targets: Camera LCD (1)
  ❌ PC Screen disabled (Live view to computer NOT possible)
```

---

## 🎯 DISCOVERED ISSUES

### Issue #1: AE Mode Value is Abnormal (1310479)

**Valid AE Modes (from EDSDK documentation):**
```
0x00 = Program AE
0x01 = Shutter-Speed Priority AE
0x02 = Aperture Priority AE
0x03 = Manual Exposure
0x04 = Bulb
0x05 = Auto Depth-of-Field AE
0x06 = Depth-of-Field AE
0x07 = Camera settings registered
0x08 = Lock
0x09 = Auto
0x0A-0x3F = Various scene modes
0xFFFFFFFF = Not valid/no settings changes
```

**Problem:** 1310479 (0x0013ff0f) is **NOT a valid AE mode**
- Likely caused by: Uninitialized memory or property not available on camera
- Should be: 0-0x3F or 0xFFFFFFFF
- **This may be causing the mode check failure**

---

### Issue #2: EVF Mode Value is 2 (Invalid)

**Valid EVF Mode values (from documentation):**
```
0 = Disable
1 = Enable
```

**Problem:** Value is 2 (not 0 or 1)
- Indicates camera is in an unknown state
- May mean EVF was partially initialized before disconnect
- **This could be causing Error 129**

---

### Issue #3: EVF Output Device is 1 (Camera LCD Only)

**Current state:** 0x01 = Camera LCD only
**Expected state:** 0x02 = PC Screen OR 0x03 = Both (0x01 | 0x02)

**Problem:** PC output is NOT enabled
- Camera is NOT configured for live view to PC
- This explains Error 129 when trying to enable EVF
- **Camera needs to be explicitly switched to PC output**

---

## 🏗️ SEQUENCE DIAGRAM: Expected vs Actual

### Expected Flow (from EDSDK docs):

```
1. Open Session ✅
2. Set EVF Output Device to PC (0x02) ← MISSING/FAILING
   └─ Process Events (wait for property change confirmation)
3. Set EVF Mode to Enable (1) ← THIS FAILS WITH ERROR 129
   └─ Process Events
4. Create EVF Image Stream
5. Download EVF Image (EdsDownloadEvfImage)
```

### Actual Flow:

```
1. Open Session ✅
2. Set EVF Output Device to PC (0x02)
   └─ ❌ NOT waiting for property change events
   └─ ❌ Device is still at 0x01 (LCD only)
3. Set EVF Mode to Enable (1)
   └─ ❌ ERROR 129: Device rejects because:
       - Output device not properly set to PC
       - Camera is in unknown EVF state (value=2)
       - No event processing between property changes
```

---

## 🔧 ROOT CAUSES (Ordered by Likelihood)

### 1. **Missing Event Processing Between Property Changes** (90% confidence)

**Current code (canon_camera_connection.py, line 427-449):**
```python
# Set EVF output device
output_device = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, ...)
if err != EDS_ERR_OK:
    return  # ❌ No event processing!

# Immediately try to set EVF mode
evf_mode = ctypes.c_uint32(1)
err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_Mode, ...)
if err == 129:  # ❌ FAILS HERE
```

**The Fix:** Add event processing:
```python
# After setting output device
output_device = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, ...)
if err != EDS_ERR_OK:
    return

# MUST process events for property to take effect
self._process_events()  # ← CRITICAL
time.sleep(0.2)         # ← Allow camera to settle
self._process_events()  # ← Ensure all events processed

# NOW set EVF mode (will work because device is set to PC)
evf_mode = ctypes.c_uint32(1)
err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_Mode, ...)
```

### 2. **Camera in Bad EVF State (value=2)** (60% confidence)

The camera returned EVF Mode = 2 (invalid value) which suggests:
- Previous session didn't properly clean up
- EVF was partially initialized
- Camera needs reset/clean shutdown

**The Fix:** Add EVF reset before starting live view:
```python
# Reset EVF to known state
evf_mode_off = ctypes.c_uint32(0)
err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_Mode, 0,
                                   ctypes.sizeof(evf_mode_off), ctypes.byref(evf_mode_off))
self._process_events()
time.sleep(0.2)

# Reset output device to camera LCD
output_device_lcd = ctypes.c_uint32(0x01)
err = self.edsdk.EdsSetPropertyData(self.camera, kEdsPropID_Evf_OutputDevice, 0,
                                   ctypes.sizeof(output_device_lcd), ctypes.byref(output_device_lcd))
self._process_events()
time.sleep(0.2)

# NOW properly set up for PC live view
```

### 3. **AE Mode Validation Issue** (20% confidence)

The abnormal AE mode value (1310479) might be triggering camera-side validation:
```python
# Better mode checking
ae_mode = ctypes.c_uint32()
err = self.edsdk.EdsGetPropertyData(self.camera, kEdsPropID_AEModuleMode, ...)
if err == EDS_ERR_OK and ae_mode.value <= 0x3F:  # Valid range
    # Mode is valid
else:
    # Mode is invalid, may need to reset or ignore
```

---

## 📚 KEY EDSDK DOCUMENTATION REFERENCES

### EdsDownloadEvfImage (3.1.31):
```
"EDS_ERR_OBJECT_NOTREADY returns as an error when the image data set 
is not ready at the camera or when the image data set cannot be obtained. 
Be sure to retry if EDS_ERR_OBJECT_NOTREADY is returned."
```

### kEdsPropID_Evf_Mode (5.2.55):
```
Gets/sets live view function settings.
Value: 0 = Disable, 1 = Enable
```

### kEdsPropID_Evf_OutputDevice (5.2.54):
```
Starts/ends live view. The camera TFT and PC to be used as the 
output device for live view can be specified.
If a PC only is set for the output device, UILock status will be 
set for the camera except for the SET button.
```

---

## ✅ PROPOSED FIXES (In Order of Priority)

### Fix #1: Add Event Processing Between Property Changes (CRITICAL)
- **File:** `src/canon_camera_connection.py`
- **Method:** `_handle_start_live_view_command()`
- **Change:** Add `self._process_events()` and `time.sleep()` after each property set
- **Expected Result:** Camera state properly updated before next operation

### Fix #2: Add EVF Reset Before Initialization (HIGH)
- **File:** `src/canon_camera_connection.py`
- **Method:** `_handle_start_live_view_command()`
- **Change:** Reset EVF to known state (mode=0, device=0x01) before setting up PC live view
- **Expected Result:** Clean slate for live view initialization

### Fix #3: Improve Mode Validation (MEDIUM)
- **File:** `src/camera_constants.py`
- **Change:** Add helper function to validate AE mode value
- **File:** `src/canon_camera_connection.py`
- **Change:** Use validation before proceeding with live view
- **Expected Result:** Better error detection

---

## 🧪 VERIFICATION STEPS

1. **After Fix #1:** Run `python3.11 app.py` and attempt live view
   - Expected: Error 129 should be resolved
   
2. **After Fix #2:** If still failing, error will be different (progress!)
   
3. **After Fix #3:** More informative error messages if problem persists

---

## 📝 IMPLEMENTATION NOTES

- All changes should use existing `_process_events()` method
- Use `RECOVERY_DELAY_SHORT` (0.1s) and `RECOVERY_DELAY_MEDIUM` (0.2s) for delays
- Maintain existing logging/error patterns
- No new dependencies required
- Keep changes minimal and focused

---

## 🎯 SUCCESS CRITERIA

When fixed, the application should:
1. ✅ Set EVF output device to PC without error
2. ✅ Set EVF mode to enabled without error
3. ✅ Successfully call `EdsDownloadEvfImage()`
4. ✅ Display live view frames in GUI
5. ✅ No Error 129 in logs

---

**Analysis completed:** November 11, 2025
**Confidence level:** 85% (high)
**Difficulty:** Low-Medium (straightforward event processing fix)
