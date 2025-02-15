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

3. Ensure your Canon camera is:
   - Connected via USB
   - Powered on
   - In photo mode (not video mode)
   - Has live view capability enabled

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
python -m pytest tests/
```

For tests requiring a physical camera, set the environment variable:
```bash
CAMERA_CONNECTED=1 python -m pytest tests/test_camera.py
```

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
