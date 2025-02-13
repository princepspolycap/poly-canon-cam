# Canon Camera Control

A Princeps Polycap Productions Project for using Canon cameras as webcams.

## Quick Start

1. Connect your Canon camera via USB
2. Ensure the camera is:
   - Turned on
   - In photo mode
   - Any lens covers are removed
3. Run the viewer:
```bash
python viewer.py
```
4. Press 'q' to quit the live view window

## Prerequisites

- macOS (tested on macOS 14.0)
- Python 3.11+
- Canon camera with USB connection
- Canon EDSDK 13.18.40

## Setup

1. Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Project Structure

```
.
├── README.md               # This file
├── requirements.txt        # Python dependencies
├── viewer.py              # Main application
├── src/
│   ├── camera.py         # Camera control module
│   └── live_view.py      # Live view implementation
└── EDSDK 13.18.40 Macintosh/
    └── EDSDK.framework/  # Canon EDSDK library
```

## Features

- Camera connection and basic control
- Live view streaming
- Error handling and recovery
- Clean session management

## Development

The project uses:
- Canon EDSDK for camera control
- OpenCV for image display
- NumPy for image processing

## Contributing

Contributions are welcome! Here's how you can help:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure your PR includes:
- Clear description of changes
- Any updates to documentation
- Test results if applicable

## License and Disclaimer

This project is released under the MIT License by Princeps Polycap Productions. However, please note:
- The Canon EDSDK is proprietary software owned by Canon Inc.
- You must be a member of the Canon Developer Community to use the EDSDK
- This project is a community tool and is not affiliated with, endorsed by, or supported by Canon Inc.
- For support, please use GitHub issues rather than contacting Canon

## About Princeps Polycap Productions

This tool is maintained by Princeps Polycap Productions as part of our commitment to the open-source community. We develop free tools that empower creators and developers.
