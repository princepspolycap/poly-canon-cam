# Camera Connection Cleanup & Troubleshooting Guide

This guide documents how Poly Canon Cam keeps the Canon EOS USB stack healthy,
and outlines the manual flows to fall back on if the automated cleanup ever
needs a helping hand.

---

## 1. Built-in Cleanup Pipeline

Every time the GUI worker receives a **connect** command it performs:

1. **State reset** – clears prior session handles, frame counters, worker flags.
2. **macOS hygiene** (via `camera_utils.cleanup_macos_camera_connection`):
   - `PTPCamera` kill
   - `Image Capture Extension` kill
   - `usbd` warm reset (`killall -HUP usbd`, ignored if not owned)
   - Canon EOS Webcam Utility background process sweep
3. **USB stabilization wait (1 s)** – allows the macOS runloop to re-enumerate.
4. **EDSDK load & initialization** – followed by a 3 s intensive event pump.
5. **Camera detection with retries** – up to 10 loops with event processing.

Disconnecting from the GUI stops live view, closes the session, and releases the
camera **without terminating the SDK**. That means you can reconnect
immediately as soon as the camera finishes USB teardown.

The SDK/worker are only shut down when the app exits, keeping reconnection fast
and reliable.

---

## 2. Manual Cleanup Script

Use the provided harness whenever you want to reproduce the GUI pipeline from
the terminal or when onboarding a fresh machine.

```bash
cd /Users/princeps/Projects/Poly186/poly-canon-cam
source .venv/bin/activate
bash test_camera_with_cleanup.sh
```

The script performs:

1. `sudo killall PTPCamera && sudo killall "Image Capture Extension"`
2. USB verification (`ioreg -p IOUSB -l | grep -A 20 "Canon"`)
3. Optional reminders about hubs/docks
4. Comprehensive `tests/test_camera_connection.py` run (loads SDK, connects,
   inspects live view readiness)

When it finishes, the GUI can usually connect immediately since the system
state mirrors what the worker expects.

---

## 3. Manual Steps (If You Need to Do It Yourself)

### Kill image services
```bash
sudo killall PTPCamera
sudo killall "Image Capture Extension"
```

### Reset Canon EOS Webcam Utility (optional)
```bash
ps aux | grep -i "Canon EOS Webcam"   # identify lingering helper
sudo killall "Canon EOS Webcam Utility"
```

### Reset USB daemon (ignore error if not owned)
```bash
sudo killall -HUP usbd
```

### Verify USB descriptor
```bash
ioreg -p IOUSB -l | grep -A 12 "Canon Digital Camera"
# Expect:
#   "USB Product Name" = "Canon Digital Camera"
#   "USBSpeed" = 4   (SuperSpeed)
#   "kUSBCurrentConfiguration" = 1
```

### Power cycle checklist
1. Turn the camera off
2. Unplug USB-C
3. Wait ~10 s
4. Power on, reconnect directly to Mac (avoid hubs/docks if possible)
5. Rerun the `ioreg` command above

---

## 4. Healthy Log Markers

Look for the following messages when things are working:

```
Resetting connection state...
Performing system-level cleanup before connection...
Waiting for USB/camera stabilization...
Detecting cameras with enhanced retry logic...
Found 1 camera(s) on attempt 1
🎬 Starting live view using canonical EDSDK pattern...
Processing events after EVF output device change...
✅ Live view started! Camera ready for frame downloads.
```

### If Detection Fails

```
ERROR: No cameras detected after multiple attempts.
```

Actions:

1. Confirm the disconnect finished (log shows “SDK ready for reconnection”).
2. Wait 2–3 s before clicking connect again (camera firmware needs a beat).
3. Run `test_camera_with_cleanup.sh` to double-check system-level cleanup.
4. Inspect USB state with `ioreg` – should show `USBSpeed = 4` and configuration 1.
5. Power cycle the camera if still stuck.

---

## 5. Live View Notes

- We no longer manipulate `kEdsPropID_Evf_Mode` directly. Only the EVF output
  device (PC bit) is toggled, matching Canon SAMPLE10 guidance.
- After stopping live view the output device is returned to `0x01` (camera LCD)
  and events are processed for ~0.5 s to guarantee the camera acknowledges the
  change.
- If you still see Error 129 (mode not ready) it usually means the camera was
  switched to a video/scene preset. Flip the mode dial back to P/Tv/Av/M and
  retry the connect sequence.

---

## 6. Reference Material

- `docs/Camera_Connections.md` – deep dive into macOS runloop processing,
  EDSDK retry loops, and why we keep the SDK alive between sessions.
- `docs/ANALYSIS_LIVE_VIEW_ERROR_129.md` – historic investigation notes.
- `tests/test_camera_connection.py` – runnable proof of the cleanup + connect
  pipeline.

Keep this guide handy whenever USB state gets weird, or when adding new cleanup
steps to `camera_utils.py`.

**Status**: Implementation complete, awaiting camera connection for full testing
**Confidence**: 85% (high) that event processing fix resolves Error 129
**Next Step**: Connect camera and run cleanup procedure, then test
