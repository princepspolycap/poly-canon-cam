#!/usr/bin/env python3
"""
py2app setup script for Poly Canon Cam

This script packages the application into a macOS .app bundle with all
dependencies, the Canon EDSDK framework, and custom icon.

Usage:
    python setup.py py2app
"""

import os
from setuptools import setup

APP = ['app.py']
DATA_FILES = [
    ('', ['logo.png']),
    # Don't copy EDSDK here - we'll copy the whole directory to Resources after build
]

_include_syphon = os.environ.get("POLYCANON_INCLUDE_SYPHON", "").lower() in ("1", "true", "yes")

_base_packages = [
    'src',
    'numpy',
    'cv2',
    'pyvirtualcam',
    'PIL',
]

_base_includes = [
    'tkinter',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL._imaging',
    'numpy',
    'cv2',
    'pyvirtualcam',
    'pyvirtualcam._native_macos_obs_dal',
    'pyvirtualcam._native_macos_obs_cmioextension',
]

_base_excludes = [
    'pytest',
    'setuptools',
    'pip',
    'wheel',
    'test',
    'tkinter.test',
    'OpenGL',            # unused; pulls in thousands of modules and slows build
    'numpy.tests',
    'numpy.random.tests',
    'numpy.lib.tests',
]

if _include_syphon:
    # Syphon output for OBS. Disabled by default in packaged builds due to
    # frequent code-sign / framework relocation issues on macOS 13+.
    _base_packages += [
        'syphon',
        'objc',
        'Foundation',
        'AppKit',
        'Metal',
        'Cocoa',
        'CoreFoundation',
    ]
    _base_includes += [
        'syphon',
        'syphon.utils',
        'syphon.utils.numpy',
        'syphon.utils.raw',
        # pyobjc modules needed for syphon
        'objc',
        'objc._objc',
        'Foundation',
        'AppKit',
        'Metal',
        'Cocoa',
        'CoreFoundation',
        'Quartz',
    ]
else:
    # Ensure modulegraph doesn't pull Syphon in via conditional imports.
    _base_excludes += [
        'syphon',
        'syphon.utils',
        'syphon.utils.numpy',
        'syphon.utils.raw',
        'objc',
        'Foundation',
        'AppKit',
        'Metal',
        'Cocoa',
        'CoreFoundation',
        'Quartz',
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
    
    # Packages to include. Syphon/pyobjc are optional; see POLYCANON_INCLUDE_SYPHON.
    'packages': _base_packages,
    
    # Include our modules explicitly
    'includes': _base_includes,
    
    # Exclude test and development packages + problematic modules
    'excludes': _base_excludes,
    
    # Resources
    'resources': ['logo.png'],
    
    'semi_standalone': False,
    'site_packages': False,
    'strip': False,
    'optimize': 0,
}

setup(
    name='PolyCanonCam',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
