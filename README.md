# Poly Canon Cam

A Python application for controlling Canon cameras and displaying live preview using the Canon EDSDK.

## Features

- Live preview display with automatic resizing
- Professional GUI interface with camera controls
- Thread-safe implementation for smooth performance
- Proper resource management and error handling
- Comprehensive test suite
- Clean shutdown handling

## Requirements

- Python 3.7+
- Canon camera with live view support
- Canon EDSDK (included in repository)
- Required Python packages (see requirements.txt)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/poly-canon-cam.git
cd poly-canon-cam
```

2. Install required packages:

```bash
pip install -r requirements.txt
```

3. **macOS Security Setup** (Required on macOS):

   If you encounter "library load disallowed by system policy" errors, run:

   ```bash
   find "EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework" -exec xattr -d com.apple.quarantine {} \; 2>/dev/null
   ```

   Alternatively, if a security dialog appears:
   - Click "Done" (NOT "Move to Trash")
   - Go to System Settings > Privacy & Security
   - Find "EDSDK.framework" in the security section
   - Click "Allow Anyway"

4. Test EDSDK loading:

```bash
python3 tests/test_edsdk.py
```

5. Ensure your Canon camera is properly configured:

   **Quick Setup:**
   - Camera powered on with sufficient battery
   - Set to shooting mode (P, Tv, Av, M, or Auto)
   - USB connection mode set to "PC Remote" or "PTP"
   - Live View enabled in camera menus
   - Auto power-off disabled or set to maximum

   **📖 For detailed camera setup instructions, see:**
   `docs/Canon_Camera_Setup_Guide.md`

## Usage

Run the application:
```bash
python app.py
```

The application window will appear with:
- A preview area showing the camera feed
- Start/Stop camera controls
- Status information

## Development

### Project Structure
```
poly-canon-cam/
├── app.py                 # Main entry point
├── requirements.txt       # Project dependencies
├── src/
│   ├── camera.py         # Core camera functionality
│   └── gui/              # GUI-related code
│       ├── __init__.py
│       └── app.py        # GUI implementation
└── tests/                # Test suite
    ├── test_camera.py    # Camera tests
    └── test_gui.py       # GUI tests
```

### Testing

Run the test suite:

```bash
# Test EDSDK loading (run this first)
python3 tests/test_edsdk.py

# Test camera connection (requires camera connected)
python3 tests/test_camera_connection.py

# Run all tests
python -m pytest tests/
```

For tests requiring a physical camera, ensure:
- Camera is connected via USB
- Camera is powered on and in shooting mode
- Camera is set to PTP/PC connection mode

### Development Notes

- The application uses a thread-safe queue for frame transfer
- The GUI runs in the main thread while frame capture runs in a separate thread
- Camera operations are properly managed through the CanonCamera class
- Error handling includes recovery suggestions

## Troubleshooting

If you encounter issues:

1. Check camera connection and power
2. Ensure camera is in photo mode
3. Verify live view is enabled
4. Check USB connection
5. Try disconnecting and reconnecting the camera
6. Check the console output for specific error messages

## License

This project is licensed under the terms of the included LICENSE file.
