# Poly Canon Cam

A Python-based live preview application for Canon cameras using the Canon EDSDK.

## Features

- Live camera preview with FPS counter
- Automatic camera detection and connection
- Error handling and reconnection support
- Clean shutdown and resource management
- Support for Photo mode live view

## Requirements

- Python 3.8+
- Canon EDSDK 13.18.40
- Compatible Canon camera in Photo mode
- OpenCV (`cv2`)
- NumPy

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd poly-canon-cam
```

2. Create a virtual environment and activate it:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Canon EDSDK:
   - Place the EDSDK files in the `EDSDK 13.18.40 Macintosh` directory
   - Ensure the EDSDK framework is properly installed and accessible

## Usage

1. Connect your Canon camera via USB
2. Put your camera in Photo mode (not Movie mode)
3. Enable Live View on your camera if available
4. Run the viewer:
```bash
python viewer.py
```

5. Press 'q' to quit the viewer

## Troubleshooting

If you encounter issues:

1. Ensure camera is in Photo mode (not Movie mode)
2. Turn camera off
3. Disconnect USB cable
4. Wait 5 seconds
5. Connect USB cable
6. Turn camera on
7. Enable live view
8. Try running viewer again

## Project Structure

```
poly-canon-cam/
├── src/
│   ├── __init__.py
│   ├── camera.py      # Core camera interface
│   ├── gui_app.py     # GUI application components
│   └── live_view.py   # Live view handling
├── viewer.py          # Main application entry
├── requirements.txt   # Python dependencies
└── README.md         # This file
```

## Development

The project uses the Canon EDSDK to interface with Canon cameras. Key components:

- `camera.py`: Core camera interface implementing EDSDK functionality
- `viewer.py`: Main application with OpenCV-based preview window
- `live_view.py`: Live view image processing and display
- `gui_app.py`: GUI components for future development

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to your branch
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Canon for providing the EDSDK
- OpenCV community for image processing capabilities
- Python ctypes for enabling EDSDK integration
