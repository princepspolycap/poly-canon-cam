# Poly Canon Cam

Professional macOS tooling for Canon EOS live view capture, built on EDSDK 13.19.10.  
The app wraps Canon's low-level APIs in a resilient worker that handles USB cleanup,
automatic reconnection, GUI control, and testing utilities.

---

## Highlights

- 🔁 **Reliable connect/disconnect loop** – worker thread stays alive, SDK remains loaded, and every connection attempt performs a full macOS camera cleanup + stabilization delay.
- 🎥 **Low-latency live view** – EVF output routing follows Canon’s SAMPLE10 pattern (PC bit only) with event-driven confirmation.
- 🧹 **Built-in system hygiene** – PTPCamera/Image Capture Extension kills, usbd warm reset, and Canon EOS Webcam Utility teardown before every connection.
- 🧪 **Diagnostics & tests** – scripts mirror the production cleanup flow, plus integration tests for SDK loading and camera sessions.
- 🖥️ **GUI-first workflow** – single “Connect & Start Live View” button, status feed, and graceful disconnect that keeps the SDK ready.
- 📡 **Virtual webcam outputs** – simultaneous Syphon feed for OBS and PyVirtualCam bridge to the macOS-wide “OBS Virtual Camera,” so Google Meet/Zoom/Teams see the Canon feed without extra hardware.

---

## Requirements

- macOS 13+ with Gatekeeper permissions to load unsigned frameworks
- Python 3.11 (repository ships with `.venv` for consistency)
- Canon EOS camera with PC Remote/PTP + Live View support
- Bundled **EDSDK 13.19.10** (no external download required)

See `docs/Canon_Camera_Setup_Guide.md` for the camera-side menu checklist.

---

## Quick Start

```bash
git clone https://github.com/yourusername/poly-canon-cam.git
cd poly-canon-cam

# Recommended: use the existing virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **macOS security prompt?**  
> If you get “library load disallowed by system policy”, clear the quarantine flag:
> ```bash
> find "EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework" \
>   -exec xattr -d com.apple.quarantine {} \; 2>/dev/null
> ```
> or allow the binary from **System Settings ▸ Privacy & Security**.


### Verify the SDK

```bash
source .venv/bin/activate
python tests/test_edsdk.py
```

### Launch the App

```bash
source .venv/bin/activate
python app.py
```

1. Click **“Connect & Start Live View.”**
2. The worker:
   - Resets all internal state
   - Performs macOS cleanup (PTPCamera, Image Capture Extension, usbd, Canon EOS Webcam Utility)
   - Waits 1s for USB stabilization
   - Loads EDSDK and connects to the first detected camera
3. Live view starts after EVF output device switches to PC (0x01 → 0x03).

### Disconnecting

Use **“Disconnect Camera”** in the GUI:

- Stops live view (reverts EVF output to camera LCD only)
- Closes the session and releases handles
- Keeps the SDK + worker alive so you can reconnect immediately
- App-wide shutdown (window close) is the only time we terminate the SDK

This mirrors the manual `test_camera_with_cleanup.sh` flow without leaving orphaned USB state.

---

## Virtual Webcam Outputs (OBS + Google Meet)

Once live view starts, `src/virtual_webcam.py` spins up two outputs automatically:

- **Syphon server** (`PolyCanonCam_Syphon`) – add a *Syphon Client* source in OBS to ingest the feed directly with minimal latency.
- **PyVirtualCam** – publishes the same frames to the system-wide **OBS Virtual Camera** device so browsers and conferencing apps recognize it as a regular webcam.

### Requirements

1. `syphon-python` and `pyvirtualcam` (already listed in `requirements.txt`).
2. OBS Studio ≥ 28 with the built-in *Virtual Camera* feature (macOS versions bundle it by default).

### Typical Workflow

1. Launch OBS and go to **Tools ▸ Start Virtual Camera** (or press the Virtual Camera button).
2. Start `python app.py`, click **“Connect & Start Live View.”**
3. Poly Canon Cam logs `Started outputs: Syphon, Virtual Camera` and begins streaming frames to both endpoints.
4. In OBS, add **Sources ▸ Syphon Client ▸ PolyCanonCam_Syphon** if you want to composite/record.
5. In Google Meet / Zoom / Teams / FaceTime, choose **OBS Virtual Camera** as the video source — the Canon live view will appear instantly.

> **Tip:** The manager adapts to whatever EVF resolution your camera emits (e.g., 1024×576 on EOS R). OBS can upscale/letterbox as needed, while the browser sees the same format coming from OBS Virtual Camera.

Stopping live view (or disconnecting) tears down both outputs so OBS/browsers immediately fall back to their previous sources.

---

## Project Layout

```
poly-canon-cam/
├── app.py                       # GUI bootstrap + orchestration
├── src/
│   ├── canon_camera_connection.py   # Worker thread, SDK orchestration, EVF logic
│   ├── camera_utils.py              # macOS cleanup helpers & diagnostics
│   ├── gui.py / gui_style.py        # Tkinter UI
│   ├── virtual_webcam.py            # Syphon / virtual webcam bridge
│   └── camera_constants.py          # EDSDK enums + helpers
├── tests/
│   ├── test_edsdk.py                # Framework load + basic init
│   ├── test_camera_connection.py    # Full connection pipeline (requires camera)
│   └── test_live_view_stream.py     # Live view regressions
├── docs/
│   ├── CAMERA_CLEANUP_GUIDE.md      # Manual cleanup + troubleshooting
│   ├── Camera_Connections.md        # EDSDK/macOS connection patterns
│   └── Canon_Camera_Setup_Guide.md  # Body configuration
└── test_camera_with_cleanup.sh      # CLI harness that mimics the GUI workflow
```

---

## Testing & Diagnostics

```bash
# Ensure framework loads
python tests/test_edsdk.py

# Full connection test (performs cleanup + connects + inspects state)
python tests/test_camera_connection.py

# Live view stress test (streams frames, detects stalls)
python tests/test_live_view_stream.py
```

`test_camera_with_cleanup.sh` is the canonical shell workflow.  
It mirrors what the GUI does: kill macOS services → verify USB → run the
connection test. Use it when onboarding new machines or after a camera crash.

---

## Troubleshooting Checklist

| Symptom | What to Try |
| --- | --- |
| `No cameras detected after multiple attempts` | Ensure the GUI disconnect finished (look for “SDK ready for reconnection”), wait 2–3 s, then connect. If still failing, run `test_camera_with_cleanup.sh` to fully reset macOS services. |
| `Failed to set EVF output device` | Confirm camera is in a stills mode (P/Tv/Av/M) with Live View enabled. Power cycle the body and reconnect directly (no hub). |
| SDK refuses to load with security error | Re-run the quarantine removal command and re-open System Settings ▸ Privacy & Security to “Allow Anyway”. |
| App freezes on quit | Make sure you updated submodules/dependencies; the GUI waits for worker shutdown, so give it a second to terminate the SDK cleanly. |

More deep-dive scenarios (USB controller quirks, Error 129 analysis, etc.) live in:
- `docs/CAMERA_CLEANUP_GUIDE.md`
- `docs/Camera_Connections.md`
- `docs/ANALYSIS_LIVE_VIEW_ERROR_129.md`

---

## License

See the bundled `LICENSE` file.
