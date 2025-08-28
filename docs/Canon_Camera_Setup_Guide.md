# Canon Camera Setup Guide for EDSDK Connection

Based on Canon EDSDK 13.19.10 documentation and testing experience.

## Pre-Connection Camera Settings

### 1. **USB Connection Mode**

- Set camera to **"PC Remote"** mode or **"PTP"** mode
- This is usually found in the camera's communication settings menu
- Some cameras automatically detect this when connected via USB
- Look for: `Menu > Communication Settings > USB Connection` or similar

### 2. **Power Settings**

- Camera must be **powered ON**
- Ensure sufficient battery level (>50% recommended) or use AC adapter
- Disable auto power-off or set to maximum time to prevent disconnection during operation
- Set: `Menu > Power Management > Auto Power Off > Disable` or `30 min`

### 3. **Memory Card**

- Insert a **formatted memory card** if you plan to save images to camera
- Card should have sufficient free space (>1GB recommended)
- Some operations require a memory card even for PC-only transfers
- Format card in camera for best compatibility

### 4. **Live View Prerequisites** (if using Live View)

- Camera should be in a shooting mode that supports Live View
- Live View function should be enabled in camera menus
- Camera should not be in certain restricted modes (like some scene modes)
- Test Live View manually before connecting to ensure it works

### 5. **UI Lock Considerations**

- When EDSDK connects, it may put camera in UI Lock state
- This disables most camera controls and enables PC control
- This is **normal behavior** for remote operation
- Camera LCD may show "PC" or similar indicator when connected

### 6. **Mode Dial Position**

- Set to an appropriate shooting mode (P, Tv, Av, M, or Auto)
- Avoid proprietary scene modes that may restrict remote control
- Manual modes (M, Tv, Av) typically offer most remote control options
- **Recommended**: Start with Program (P) mode for testing

### 7. **Communication Settings**

- Ensure USB cable is properly connected
- Use a high-quality USB cable (preferably the one provided with camera)
- Connect directly to computer, avoid USB hubs when possible
- Cable should be USB 2.0 or higher specification

## Physical Connection Steps

1. **Power on camera** and set to appropriate mode
2. **Connect USB cable** to camera and computer
3. **Wait 5-10 seconds** for OS recognition
4. **Check camera display** for connection indicator
5. **Run connection test** to verify EDSDK can connect

## Troubleshooting Common Issues

### Camera Not Detected
- Check USB cable connection
- Try a different USB port
- Restart camera (power off/on)
- Check camera battery level
- Verify camera is in correct USB mode

### Connection Drops During Operation
- Check power settings (disable auto-off)
- Use AC adapter instead of battery
- Avoid moving camera/cable during operation
- Check for USB power management settings on computer

### Live View Not Working
- Verify Live View works manually on camera first
- Check camera mode (must support Live View)
- Ensure camera is not in playback mode
- Some cameras require specific settings for PC Live View

### macOS Specific Issues
- Check System Settings > Privacy & Security for camera permissions
- Ensure EDSDK framework is not quarantined
- Run: `python3 tests/test_edsdk.py` first to verify EDSDK loading

## Testing Sequence

1. **EDSDK Loading Test**: `python3 tests/test_edsdk.py`
2. **Camera Connection Test**: `python3 tests/test_camera_connection.py`
3. **Full Application**: `python3 app.py`

## Notes

- The camera will automatically enter the appropriate communication state when EDSDK establishes a session using `EdsOpenSession()`
- Connection establishment may take 10-30 seconds depending on camera model
- Some cameras may require multiple connection attempts
- Always test with a single camera first before attempting multiple camera setups

## Supported Camera Models

This application is designed for Canon EOS cameras that support:
- Canon EDSDK 13.19.10
- Live View functionality
- USB PTP/PC Remote connection
- Examples: EOS R series, EOS 5D series, EOS 90D, etc.

Refer to Canon's EDSDK documentation for complete camera compatibility list.
