# Reliable Canon Camera Connection for macOS & EDSDK 13.19

Canon’s documentation calls out Ventura/Sonoma runloop quirks: *“macOS 13 or
later may return zero cameras; perform runloop processing before enumerating.”*
Poly Canon Cam wraps that guidance with extra macOS hygiene so a GUI button can
connect, stream, disconnect, and reconnect without touching the cable.

---

## Recommended Workflow (Used by the App)

1. **Reset state**  
   Clear cached handles, live view flags, counters, and pending commands.

2. **Perform macOS cleanup**  
   `camera_utils.cleanup_macos_camera_connection(...)` kills PTPCamera,
   Image Capture Extension, Canon EOS Webcam Utility, and warms the `usbd`
   daemon. Failures (e.g., “No matching processes”) are harmless.

3. **Wait for USB stabilization (≈1 s)**  
   Gives IOUSBHost time to re-enumerate after usbd/PTPCamera churn.

4. **Load & initialize EDSDK once per app launch**  
   The worker thread keeps the SDK resident; reconnects skip the load step.

5. **Pump events aggressively**  
   After `EdsInitializeSDK` and again before/after `EdsGetCameraList`.
   Poly Canon Cam processes ~3 s worth of events (≈60 iterations) to mirror
   Canon’s SAMPLE10 samples.

6. **Retry enumeration**  
   Up to 10 attempts with `EdsGetChildCount`, event pumping, and incremental
   delays, logging each miss so the GUI shows progress.

7. **Open the session & configure**  
   - `EdsOpenSession`
   - Extend shutdown timer (`kEdsCameraCommand_ExtendShutDownTimer`)
   - Route save destination to host (`kEdsSaveTo_Host`)

8. **Start live view using the canonical pattern**  
   Only toggle `kEdsPropID_Evf_OutputDevice` (Camera LCD ↔ PC bits). Canon
   handles `kEdsPropID_Evf_Mode` internally, so we just wait for the property
   change confirmation and fall back to timeouts when macOS drops the event.

---

## Disconnect Strategy

1. **Stop live view**  
   Set EVF output device back to `0x01` (LCD only) and process events for ~500 ms.

2. **Unregister event handlers**  
   `EdsSetCameraStateEventHandler` / `EdsSetPropertyEventHandler` → `NULL`.

3. **Close session & release camera**  
   `EdsCloseSession` → event pump → `EdsRelease`.

4. **Keep the SDK alive**  
   Only call `EdsTerminateSDK` when the ENTIRE application is closing. Between
   GUI connect/disconnect cycles we re-use the worker + SDK to avoid camera
   firmware confusion and speed up reconnection.

5. **Do system cleanup AFTER session close**  
   Re-run `cleanup_macos_camera_connection` if you need to guarantee macOS
   dropped PTPCamera or Canon EOS Webcam Utility before the next session.

This is exactly what the GUI now does: disconnect is “light” (no SDK teardown),
while quitting the app issues a final disconnect followed by a worker shutdown.

---

## Reference Snippet (Pseudo-Python)

```python
def connect_worker():
    reset_connection_state()
    camera_utils.cleanup_macos_camera_connection(send_log)
    time.sleep(1.0)  # USB settle

    if not sdk_loaded:
        load_edsdk_framework()
        edsdk.EdsInitializeSDK()
        pump_events(duration=3.0)

    for attempt in range(10):
        pump_events()
        count = get_camera_count()
        if count:
            camera = get_camera_handle()
            break
        time.sleep(1 + attempt * 0.25)
    else:
        raise RuntimeError("No cameras detected")

    edsdk.EdsOpenSession(camera)
    edsdk.EdsSendCommand(camera, kEdsCameraCommand_ExtendShutDownTimer, 0)
    # Ready for live view / captures
```

```python
def disconnect_worker():
    if live_view_active:
        set_evf_output_device(EDS_EVF_OUTPUT_CAMERA_LCD)
        pump_events(duration=0.5)

    if session_open:
        unregister_handlers()
        edsdk.EdsCloseSession(camera)
        pump_events(duration=1.0)

    release_camera()
    # SDK stays loaded; ready for immediate reconnect.
```

---

## Cleanup Utility Recap

```python
from src import camera_utils

camera_utils.cleanup_macos_camera_connection(
    extra_kill_canon_processes=True,
    send_log_func=my_logger,
    verbose=True,
)
```

Performs:
- `killall PTPCamera`
- `killall "Image Capture Extension"`
- `killall -HUP usbd` (ignored if not owned)
- Canon EOS Webcam Utility sweeps
- Optional waits between steps

This is automatically invoked before every GUI connection attempt and can be
called manually from scripts/tests.

---

## When Things Still Break

| Symptom | Likely Cause | Next Steps |
| --- | --- | --- |
| `EdsGetChildCount` always returns 0 | Camera still locked by macOS services | Run `test_camera_with_cleanup.sh`, verify `ioreg` shows SuperSpeed + configuration 1 |
| Error 129 (live view) | Camera in video/scene mode or EVF output not confirmed | Switch to P/Tv/Av/M, look for log “Confirmed EVF output device now 0x03” |
| `EdsTerminateSDK` error 2 on shutdown | macOS race after cleanup | Harmless on quit; ensure we only terminate during app exit |

See `docs/CAMERA_CLEANUP_GUIDE.md` for a deeper troubleshooting checklist and
USB inspection commands.

## macOS-Specific Connection Troubleshooting

If you're still experiencing issues, try these specific steps:

1. **Camera Mode**: Ensure the camera is in shooting mode, not playback mode.

2. **USB Connection Mode**: Many Canon cameras have a "Communication" or "Connection mode" setting. Set it to "PTP" or "Computer" mode.

3. **Physical Connection**: Try unplugging and replugging the camera, waiting 5-10 seconds before attempting to connect in software.

4. **Camera Power**: Ensure the camera has sufficient battery charge or is connected to AC power.

5. **Camera Recognition**: Before running your Python code, check if the camera appears in macOS System Information (Apple menu → About This Mac → System Report → USB).

6. **Library Path**: Ensure the path to the EDSDK library is correct for your installation.

7. **Framework Location**: For macOS applications, the EDSDK.framework should be placed in:

   ```bash
   ${AppFolder}/Contents/frameworks/
   ```

   As stated in the documentation:
   > "Be sure to copy EDSDK.framework into the application folder."

8. **Avoid SDK Termination**: The documentation specifies releasing resources with `EdsTerminateSDK()`, but this causes segmentation faults on macOS. Instead, just release individual resources in the proper order.

By following this macOS-specific approach with proper runloop processing, retry logic, and safe resource handling, you should achieve much more reliable camera connections.

## USB Snapshot Diagnostics

- Run `ioreg -p IOUSB -l` (or a trimmed `ioreg -p IOUSB -l | sed -n '320,360p'`) to confirm the camera enumerates as `Canon Digital Camera` (vendor 1193) with `Device Speed = 3`, `USBPortType = 5`, and `kUSBCurrentConfiguration = 1`. This reflects macOS exposing only the still-image/PTP interface, which aligns with the SDK reporting that PC-screen EVF streaming is disabled until we explicitly switch it on.
- Note that the body reports the generic serial string `"Canon Digital Camera"`. If multiple Canon bodies are connected simultaneously they appear identical to macOS, so always connect a single camera when debugging reconnect issues to avoid handle collisions.
- Watch for extra child devices (for example, a Realtek “BillBoard Device” from a USB‑C dock). These can keep the `AppleT8122USBXHCI` controller busy and delay re-enumeration; connecting the camera directly to the Mac removes that contention point.

## Clearing Stale macOS Attachments

1. **Kill Apple imaging daemons**: `sudo killall PTPCamera` and `sudo killall "Image Capture Extension"` just before launching your SDK-based tooling. They respawn automatically later, but this releases any stale locks on the camera.
2. **Bypass hubs when testing**: Plug the USB‑C cable straight into the Mac so the Canon node is the only active child under `AppleT8122USBXHCI`. This eliminates billboard/dock devices that can hijack bandwidth or power budgets.
3. **Power-cycle the body**: Turn the camera off, unplug USB for 5–10 seconds, then reconnect and power on. Validate the fresh attachment with `ioreg -p IOUSB -l | sed -n '320,360p'` before rerunning `app.py` or `tests/test_camera_state.py`.
4. **Re-run diagnostics after cleanup**: Once the hardware view looks correct, retry `python3.11 tests/test_camera_state.py`. If `EdsProcessEvent` still fails, inspect how the framework is loaded next (missing symbols often hint at a mismatched EDSDK build).

Capturing the current USB state and clearing these background services before every test run keeps reconnection behavior predictable and prevents macOS from holding onto the camera behind the scenes.
