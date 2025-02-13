"""
Canon Camera Control Package

This package provides functionality for controlling Canon cameras using the Canon EDSDK.
It includes camera connection, live view streaming, GUI application, and basic camera control features.

Developed by Princeps Polycap Productions as a free tool for the community.
"""

from .camera import CanonCamera
from .live_view import main as run_live_view
from .gui_app import main as run_gui_app

__all__ = ['CanonCamera', 'run_live_view', 'run_gui_app']
