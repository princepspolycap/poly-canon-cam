"""
Poly Canon Cam Package

This package provides functionality for controlling Canon cameras
and displaying live preview using the Canon EDSDK.
"""

from .camera import CanonCamera
from .live_view import LiveViewManager, FrameRateController

__all__ = ['CanonCamera', 'LiveViewManager', 'FrameRateController']
