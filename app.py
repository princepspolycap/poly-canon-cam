#!/usr/bin/env python3
"""
Poly Canon Cam - Main Application Entry Point

This script launches the Canon Camera Viewer application, providing
a graphical interface for camera control and live preview.

Usage:
    python app.py [--auto-connect] [--verbose]

Requirements:
    - Canon camera connected via USB
    - Camera in photo mode with live view enabled
    - Required Python packages installed (see requirements.txt)
"""

import sys
import os
import argparse
import subprocess
import time
from src.gui import create_app
from src.camera_utils import cleanup_macos_camera_connection

def kill_existing_processes(verbose=True):
    """
    Kill any existing Canon camera processes that might interfere with connection.
    
    Returns:
        bool: True if cleanup completed successfully
    """
    log_func = print if verbose else lambda x: None
    
    log_func("[Startup] Checking for existing Canon camera processes...")
    
    try:
        # Check for any existing Python processes running this app
        result = subprocess.run(
            ["pgrep", "-f", "poly-canon-cam"], 
            capture_output=True, text=True, check=False
        )
        
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            current_pid = str(os.getpid())
            other_pids = [pid for pid in pids if pid != current_pid]
            
            if other_pids:
                log_func(f"[Startup] Found {len(other_pids)} existing app processes, terminating...")
                for pid in other_pids:
                    try:
                        subprocess.run(["kill", "-TERM", pid], check=False)
                        time.sleep(0.5)
                    except Exception as e:
                        log_func(f"[Startup] Warning: Could not terminate PID {pid}: {e}")
                
                # Give processes time to clean up
                time.sleep(2)
                log_func("[Startup] Existing processes terminated.")
            else:
                log_func("[Startup] No other app instances found.")
        else:
            log_func("[Startup] No existing app processes found.")
            
    except Exception as e:
        log_func(f"[Startup] Warning during process cleanup: {e}")
    
    # Check for Canon EOS Webcam Utility processes
    try:
        result = subprocess.run(
            ["pgrep", "-f", "EOS"], 
            capture_output=True, text=True, check=False
        )
        
        if result.stdout.strip():
            log_func("[Startup] Found Canon EOS processes, will clean up via camera_utils...")
        else:
            log_func("[Startup] No Canon EOS Webcam processes detected.")
            
    except Exception as e:
        log_func(f"[Startup] Warning checking EOS processes: {e}")
    
    return True

def check_requirements(verbose=True):
    """
    Check if all required packages are installed and EDSDK is available.
    
    Args:
        verbose (bool): Whether to print detailed status messages
        
    Returns:
        bool: True if all requirements are met, False otherwise
    """
    log_func = print if verbose else lambda x: None
    
    log_func("[Startup] Checking Python dependencies...")
    
    try:
        import tkinter
        import cv2
        import numpy
        from PIL import Image
        import syphon
        log_func("[Startup] ✅ All Python dependencies available")
    except ImportError as e:
        print(f"\n❌ Error: Missing required package - {e.name}")
        print("Please install required packages:")
        print("pip install -r requirements.txt")
        return False

    # Check for EDSDK
    edsdk_path = "./EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework/Versions/A/EDSDK"
    if os.path.exists(edsdk_path):
        log_func(f"[Startup] ✅ Found EDSDK: Version 13.19.10 at {os.path.abspath(edsdk_path)}")
    else:
        print(f"\n❌ Error: EDSDK library not found")
        print(f"Expected path: {os.path.abspath(edsdk_path)}")
        print("\nPlease ensure Canon EDSDK is installed correctly")
        return False

    # Verify virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        log_func(f"[Startup] ✅ Running in virtual environment: {sys.prefix}")
    else:
        log_func("[Startup] ⚠️  Warning: Not running in virtual environment")
    
    log_func(f"[Startup] ✅ Python interpreter: {sys.executable}")
    
    return True

def perform_system_cleanup(verbose=True):
    """
    Perform comprehensive system-level cleanup before starting the app.
    
    Args:
        verbose (bool): Whether to print detailed status messages
        
    Returns:
        bool: True if cleanup completed successfully
    """
    log_func = print if verbose else lambda x: None
    
    log_func("[Startup] Performing system-level camera cleanup...")
    
    try:
        # Use our existing camera utils for macOS cleanup
        cleanup_macos_camera_connection(
            extra_kill_canon_processes=True,
            verbose=verbose,
            send_log_func=lambda msg: log_func(f"[CameraUtils] {msg}")
        )
        log_func("[Startup] ✅ System cleanup completed")
        return True
    except Exception as e:
        log_func(f"[Startup] ⚠️  Warning during system cleanup: {e}")
        return False

def main():
    """
    Application entry point with comprehensive startup process management.
    
    1. Parse command line arguments
    2. Kill any existing interfering processes  
    3. Check all requirements are met
    4. Perform system-level cleanup
    5. Create and launch the GUI application
    6. Handle any startup errors gracefully
    """
    parser = argparse.ArgumentParser(description='Canon Camera Live View Application')
    parser.add_argument('--auto-connect', action='store_true', 
                       help='Automatically connect to camera on startup')
    parser.add_argument('--verbose', action='store_true', default=True,
                       help='Enable verbose startup logging (default: enabled)')
    parser.add_argument('--quiet', action='store_true',
                       help='Disable startup logging')
    
    args = parser.parse_args()
    verbose = args.verbose and not args.quiet
    
    if verbose:
        print("=" * 60)
        print("🎬 Poly Canon Cam - Professional Camera Control")
        print("   Princeps Polycap Productions")
        print("=" * 60)
    
    # Step 1: Kill existing processes that might interfere
    if not kill_existing_processes(verbose=verbose):
        print("❌ Failed to clean up existing processes")
        sys.exit(1)
    
    # Step 2: Check requirements
    if not check_requirements(verbose=verbose):
        sys.exit(1)
    
    # Step 3: Perform system cleanup
    if not perform_system_cleanup(verbose=verbose):
        print("⚠️  System cleanup had warnings, but continuing...")
    
    if verbose:
        print("[Startup] 🚀 Starting GUI application...")
        print("[Startup] 💡 Tip: GUI window may appear behind other windows")
        print("[Startup] 📱 Use Cmd+Tab (macOS) to bring window to front if needed")
        print("=" * 60)

    try:
        # Create the application window
        app = create_app()
        
        # Auto-connect if requested
        if args.auto_connect:
            if verbose:
                print("[Startup] 🔗 Auto-connect enabled, will attempt connection after GUI loads...")
            # Schedule auto-connect after GUI is fully loaded
            app.root.after(1000, app.cmd_connect_camera)
        
        # Configure the window before showing
        app.root.update_idletasks()
        
        if verbose:
            print("[Startup] ✅ GUI loaded successfully")
            print("[Startup] 🎯 Click 'Connect Camera' to begin camera operations")
        
        # Start the event loop
        app.root.mainloop()
        
    except KeyboardInterrupt:
        print("\n[Startup] 🛑 Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting application: {e}")
        print("\n🔧 Troubleshooting steps:")
        print("1. Ensure camera is connected and powered on")
        print("2. Check camera is in photo mode (not video mode)")
        print("3. Verify USB connection is secure")
        print("4. Try disconnecting and reconnecting the camera")
        print("5. Run with --verbose for more detailed logs")
        sys.exit(1)

if __name__ == "__main__":
    main()
