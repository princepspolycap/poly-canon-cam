#!/usr/bin/env python3
"""
Unified Canon Camera Connection Test

This comprehensive test combines EDSDK loading verification and camera connection testing.
It includes macOS security fixes, enhanced error handling, and step-by-step diagnostics.

Usage:
    python3 tests/test_camera_connection.py
    
Requirements:
    - Canon camera connected via USB
    - Camera in PTP/PC mode
    - Camera powered on and in shooting mode
"""

import os
import sys
import ctypes
import time
import threading
import queue
import platform
import subprocess

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from camera_constants import EDS_ERR_OK, kEdsPropID_SaveTo, kEdsSaveTo_Host, kEdsCameraCommand_ExtendShutDownTimer
    from camera_utils import cleanup_macos_camera_connection
    # Don't import the threaded classes for now, implement direct connection test
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")
    EDS_ERR_OK = 0
    kEdsPropID_SaveTo = 0x0000000b
    kEdsSaveTo_Host = 1
    kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
    IMPORTS_AVAILABLE = False


def check_macos_security():
    """Check and fix macOS security attributes on EDSDK framework"""
    print("\n🔒 Checking macOS security attributes...")
    edsdk_framework_path = "./EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework"
    
    try:
        # Check if quarantine attribute exists
        result = os.system(f'xattr -l "{edsdk_framework_path}" 2>/dev/null | grep -q quarantine')
        if result == 0:
            print("⚠️  Quarantine attribute detected. Attempting removal...")
            removal_result = os.system(f'find "{edsdk_framework_path}" -exec xattr -d com.apple.quarantine {{}} \\; 2>/dev/null')
            if removal_result == 0:
                print("✅ Quarantine attribute removed")
            else:
                print("⚠️  Could not remove quarantine attribute (may require manual intervention)")
                print("\n🔧 Manual fix:")
                print("   Go to System Settings > Privacy & Security")
                print("   Find 'EDSDK.framework' and click 'Allow Anyway'")
        else:
            print("✅ No quarantine attribute found")
            
        # Check code signature
        print("\n📝 Checking code signature...")
        result = os.system(f'codesign -dv "{edsdk_framework_path}" 2>/dev/null')
        if result == 0:
            print("✅ Framework is properly signed")
        else:
            print("⚠️  Code signature check failed")
            
    except Exception as e:
        print(f"⚠️  Could not check security attributes: {e}")


def check_system_usb_devices():
    """Check if Canon cameras are visible at OS level"""
    print("\n🔌 Checking USB devices...")
    
    if platform.system() != "Darwin":
        print("USB device check is macOS specific. Skipping.")
        return True
        
    try:
        result = subprocess.run(
            ['system_profiler', 'SPUSBDataType'], 
            capture_output=True, 
            text=True
        )
        output = result.stdout
        
        if 'Canon' in output:
            print("✅ Canon device found in system USB devices")
            # Extract Canon device details
            lines = output.split('\n')
            for i, line in enumerate(lines):
                if 'Canon' in line:
                    print(f"  📷 {line.strip()}")
                    # Show a few context lines
                    for j in range(i+1, min(len(lines), i+4)):
                        if lines[j].strip() and not lines[j].startswith(' ' * 8):
                            break
                        if 'Product ID' in lines[j] or 'Vendor ID' in lines[j]:
                            print(f"     {lines[j].strip()}")
                    break
            return True
        else:
            print("❌ No Canon devices found in system USB devices")
            return False
    except Exception as e:
        print(f"⚠️  Error checking USB devices: {e}")
        return False


def test_edsdk_loading():
    """Test EDSDK library loading with multiple strategies"""
    print("\n📚 Testing EDSDK Loading...")
    print("=" * 50)
    
    # Check security first
    if platform.system() == "Darwin":
        check_macos_security()
    
    # Verify EDSDK path
    edsdk_path = "./EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework/Versions/A/EDSDK"
    abs_path = os.path.abspath(edsdk_path)
    
    print(f"\n📂 EDSDK path: {abs_path}")
    print(f"   File exists: {os.path.exists(abs_path)}")
    print(f"   Readable: {os.access(abs_path, os.R_OK)}")
    print(f"   Executable: {os.access(abs_path, os.X_OK)}")
    
    if not os.path.exists(abs_path):
        print("❌ EDSDK library not found!")
        return False
    
    # Test loading strategies
    print("\n🔄 Testing loading strategies...")
    
    loading_strategies = [
        ("Direct CDLL", lambda: ctypes.CDLL(abs_path)),
        ("CDLL with RTLD_LOCAL", lambda: ctypes.CDLL(abs_path, mode=ctypes.RTLD_LOCAL)),
        ("CDLL with RTLD_GLOBAL", lambda: ctypes.CDLL(abs_path, mode=ctypes.RTLD_GLOBAL)),
    ]
    
    edsdk = None
    for strategy_name, loader in loading_strategies:
        try:
            print(f"   Trying {strategy_name}...")
            edsdk = loader()
            print(f"   ✅ Success with {strategy_name}")
            break
        except Exception as e:
            print(f"   ❌ {strategy_name} failed: {e}")
            continue
    
    if not edsdk:
        print("❌ All loading strategies failed")
        return False
    
    # Test SDK initialization
    print("\n⚙️  Testing SDK initialization...")
    try:
        init_result = edsdk.EdsInitializeSDK()
        if init_result == EDS_ERR_OK:
            print("✅ EDSDK initialized successfully")
            
            # Test basic functionality
            camera_list = ctypes.c_void_p()
            list_result = edsdk.EdsGetCameraList(ctypes.byref(camera_list))
            if list_result == EDS_ERR_OK:
                print("✅ Camera list functionality working")
                edsdk.EdsRelease(camera_list)
            
            # Clean shutdown
            term_result = edsdk.EdsTerminateSDK()
            if term_result == EDS_ERR_OK:
                print("✅ EDSDK terminated cleanly")
            
            return True
        else:
            print(f"❌ SDK initialization failed: {init_result}")
            return False
    except Exception as e:
        print(f"❌ SDK operation failed: {e}")
        return False


def test_camera_connection():
    """Test actual camera connection using direct EDSDK calls"""
    print("\n📷 Testing Camera Connection...")
    print("=" * 50)
    
    # Check for USB devices first
    if not check_system_usb_devices():
        print("\n⚠️  No Canon devices detected at USB level")
        print("\n📋 Camera Setup Checklist:")
        print("   1. Camera is powered on with sufficient battery (>50%)")
        print("   2. Camera is in shooting mode (P, Tv, Av, M, or Auto)")
        print("   3. USB cable is properly connected (use camera's original cable)")
        print("   4. Camera is set to 'PC Remote' or 'PTP' mode in communication settings")
        print("   5. Live View is enabled and working manually on camera")
        print("   6. Memory card is inserted and formatted")
        print("   7. Auto power-off is disabled or set to maximum time")
        print("\n📖 For detailed setup instructions, see:")
        print("   docs/Canon_Camera_Setup_Guide.md")
        print("\n🔄 After checking settings, disconnect and reconnect camera, then retry")
        return False

    try:
        print("\n🔗 Testing direct EDSDK camera detection...")
        
        # Load EDSDK directly
        edsdk_path = "./EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework/Versions/A/EDSDK"
        edsdk = ctypes.CDLL(edsdk_path, mode=ctypes.RTLD_GLOBAL)
        
        # Initialize SDK
        print("   🔧 Initializing EDSDK...")
        init_result = edsdk.EdsInitializeSDK()
        if init_result != EDS_ERR_OK:
            print(f"   ❌ SDK initialization failed: {init_result}")
            return False
        
        print("   ✅ EDSDK initialized")
        
        # Enhanced event processing (critical for camera detection)
        print("   🔄 Processing events for camera detection...")
        for i in range(100):  # More thorough event processing
            edsdk.EdsGetEvent()
            if i % 20 == 0:
                print(f"      Event processing: {i}%...")
            time.sleep(0.05)
        
        # Get camera list with retry logic
        print("   📷 Detecting cameras with retry logic...")
        camera_list = ctypes.c_void_p()
        list_result = edsdk.EdsGetCameraList(ctypes.byref(camera_list))
        
        if list_result != EDS_ERR_OK:
            print(f"   ❌ Failed to get camera list: {list_result}")
            edsdk.EdsTerminateSDK()
            return False
        
        # Try multiple times to get camera count (Canon documentation requirement)
        max_attempts = 20
        camera_count = 0
        
        for attempt in range(max_attempts):
            # Process events before each attempt
            for _ in range(5):
                edsdk.EdsGetEvent()
            
            count_val = ctypes.c_uint32(0)
            count_result = edsdk.EdsGetChildCount(camera_list, ctypes.byref(count_val))
            
            if count_result == EDS_ERR_OK and count_val.value > 0:
                camera_count = count_val.value
                print(f"   ✅ Found {camera_count} camera(s) on attempt {attempt + 1}")
                break
            
            if attempt < max_attempts - 1:
                print(f"   � Attempt {attempt + 1}/{max_attempts}: No cameras yet, retrying...")
                time.sleep(0.5)
        
        # Clean up
        edsdk.EdsRelease(camera_list)
        edsdk.EdsTerminateSDK()
        
        if camera_count > 0:
            print("   🎉 Camera detection successful!")
            print("\n💡 Next steps:")
            print("   1. Camera is properly connected and detected")
            print("   2. Run: python3 app.py to test full application")
            return True
        else:
            print("   ❌ No cameras detected by EDSDK after all attempts")
            print("\n🔧 Troubleshooting:")
            print("   1. Camera is detected at USB level but not by EDSDK")
            print("   2. Check camera is set to 'PC Remote' or 'PTP' mode")
            print("   3. Ensure camera is in shooting mode (not playback)")
            print("   4. Try power cycling camera while connected")
            print("   5. Check camera display shows 'PC' connection icon")
            return False
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False


def main():
    """Run comprehensive camera connection tests"""
    print("🎯 Poly Canon Cam - Comprehensive Connection Test")
    print("=" * 60)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    
    # Step 1: Test EDSDK loading
    edsdk_success = test_edsdk_loading()
    
    if not edsdk_success:
        print("\n❌ EDSDK loading failed - cannot proceed with camera tests")
        print("\n🔧 Troubleshooting:")
        print("   1. Check macOS security settings")
        print("   2. Ensure EDSDK framework is not quarantined")
        print("   3. Run: python3 tests/test_edsdk.py for detailed diagnostics")
        return False
    
    # Step 2: Test camera connection
    camera_success = test_camera_connection()
    
    # Summary
    print("\n📊 Test Summary:")
    print(f"   EDSDK Loading: {'✅ PASS' if edsdk_success else '❌ FAIL'}")
    print(f"   Camera Connection: {'✅ PASS' if camera_success else '❌ FAIL'}")
    
    if edsdk_success and camera_success:
        print("\n🎉 All tests passed! Camera system is ready.")
        print("\n💡 Next steps:")
        print("   1. Run: python3 app.py")
        print("   2. Click 'Connect Camera' in the GUI")
        print("   3. Test live view functionality")
        return True
    else:
        print("\n⚠️  Some tests failed. Check output above for details.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
