#!/usr/bin/env python3
"""
py2app setup script for Poly Canon Cam

This script packages the application into a macOS .app bundle with all
dependencies, the Canon EDSDK framework, and custom icon.

Usage:
    python setup.py py2app
"""

from setuptools import setup

APP = ['app.py']
DATA_FILES = [
    ('', ['logo.png']),
    # Don't copy EDSDK here - we'll copy the whole directory to Resources after build
]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'logo.icns',  
    'plist': {
        'CFBundleName': 'Poly Canon Cam',
        'CFBundleDisplayName': 'Poly Canon Cam',
        'CFBundleIdentifier': 'com.princepspolycap.polycanoncam',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '13.0',
        'NSCameraUsageDescription': 'Poly Canon Cam needs camera access to control your Canon camera via USB.',
        'NSUSBDeviceUsageDescription': 'Poly Canon Cam needs USB access to communicate with your Canon camera.',
        # Allow app to run without macOS app translocation
        'LSApplicationCategoryType': 'public.app-category.photography',
        # Disable App Transport Security for local connections
        'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
        # Request permissions for USB device access
        'com.apple.security.device.usb': True,
    },
    
    # Just include our source package
    'packages': ['src', 'PIL'],
    
    # Include our modules explicitly
    'includes': [
        'tkinter',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL._imaging',
        'numpy',
        'cv2',
        'syphon',
        'pyvirtualcam',
        'pyvirtualcam._native_macos_obs_dal',
        'pyvirtualcam._native_macos_obs_cmioextension',
    ],
    
    # Exclude test and development packages + problematic modules
    'excludes': ['pytest', 'setuptools', 'pip', 'wheel', 'test', 'tkinter.test'],
    
    # Resources
    'resources': ['logo.png'],
    
    'semi_standalone': False,
    'site_packages': True,
    'strip': False,
    'optimize': 0,
}

setup(
    name='PolyCanonCam',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    install_requires=[
        'numpy>=1.21.0',
        'opencv-python>=4.5.0',
        'Pillow>=9.0.0',
        'syphon-python>=0.1.1',
        'pyvirtualcam>=0.9.1',
    ],
)
