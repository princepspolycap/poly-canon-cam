#!/usr/bin/env python3
"""
Poly Canon Cam - Main Application Entry Point

This script launches the Canon Camera Viewer application, providing
a graphical interface for camera control and live preview.

Usage:
    python app.py

Requirements:
    - Canon camera connected via USB
    - Camera in photo mode with live view enabled
    - Required Python packages installed (see requirements.txt)
"""

import sys
import os
from src.gui import create_app

def check_requirements():
    """
    Check if all required packages are installed and EDSDK is available.
    
    Returns:
        bool: True if all requirements are met, False otherwise
    """
    try:
        import tkinter
        import cv2
        import numpy
        from PIL import Image
    except ImportError as e:
        print(f"\nError: Missing required package - {e.name}")
        print("Please install required packages:")
        print("pip install -r requirements.txt")
        return False

    # Check for EDSDK
    edsdk_path = "./EDSDK 13.19.0 Macintosh/EDSDK.framework/Versions/A/EDSDK"
    if os.path.exists(edsdk_path):
        print(f"Found EDSDK: Version 13.19.0 (Macintosh) at {os.path.abspath(edsdk_path)}")
    else:
        print("\nError: EDSDK library not found")
        print(f"Expected path: {os.path.abspath(edsdk_path)}")
        print("\nPlease ensure Canon EDSDK is installed correctly")
        return False

    return True

def main():
    """
    Application entry point.
    
    1. Checks all requirements are met
    2. Creates and launches the GUI application
    3. Handles any startup errors
    """
    if not check_requirements():
        sys.exit(1)

    try:
        # Create the application window
        app = create_app()
        
        # Configure the window before showing
        app.root.update_idletasks()
        
        # Start the event loop
        app.root.mainloop()
    except Exception as e:
        print(f"\nError starting application: {e}")
        print("\nTroubleshooting steps:")
        print("1. Ensure camera is connected and powered on")
        print("2. Check camera is in photo mode (not video mode)")
        print("3. Verify USB connection is secure")
        print("4. Try disconnecting and reconnecting the camera")
        sys.exit(1)

if __name__ == "__main__":
    main()
