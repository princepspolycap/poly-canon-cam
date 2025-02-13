"""
Poly Canon Cam - Canon Camera Control Package

This package provides a comprehensive toolkit for controlling Canon cameras using the Canon EDSDK.
It offers multiple interfaces for camera control and live view streaming, from basic command-line
tools to a full GUI application.

Key Components:
- camera.py: Core camera control interface using EDSDK
- live_view.py: Simple live preview implementation
- gui_app.py: Full-featured GUI application
- viewer.py: Command-line live preview tool

Features:
- Live view streaming with FPS monitoring
- Camera connection and session management
- Resource cleanup and error handling
- Multiple user interface options
- Thread-safe operations

Usage:
    from src import CanonCamera
    
    # Basic usage
    with CanonCamera() as camera:
        camera.start_live_view()
        # Work with camera...
    
    # Run GUI application
    from src import run_gui_app
    run_gui_app()
    
    # Run simple live view
    from src import run_live_view
    run_live_view()

Developed by Princeps Polycap Productions as a free tool for the community.
Licensed under MIT License.
"""

from .camera import CanonCamera
from .live_view import main as run_live_view
from .gui_app import main as run_gui_app

__all__ = ['CanonCamera', 'run_live_view', 'run_gui_app']
