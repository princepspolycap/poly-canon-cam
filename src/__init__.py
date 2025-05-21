"""
Poly Canon Cam Package

This package provides functionality for controlling Canon cameras
and displaying live preview using the Canon EDSDK.
"""

from .canon_camera_connection import CanonCameraConnection
from .canon_camera_controller import CanonCameraController
from .live_view import LiveViewManager, FrameRateController
from .virtual_webcam import SyphonWebcamOutput

__all__ = ['CanonCameraConnection', 'CanonCameraController', 'LiveViewManager', 
           'FrameRateController', 'SyphonWebcamOutput']
