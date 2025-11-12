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
    from camera_constants import (
        EDS_ERR_OK, kEdsPropID_SaveTo, kEdsSaveTo_Host, kEdsCameraCommand_ExtendShutDownTimer,
        kEdsPropID_AEModuleMode, kEdsPropID_Evf_Mode, kEdsPropID_Evf_OutputDevice,
        kEdsEvfOutputDevice_PC, kEdsPropID_ProductName, kEdsPropID_BodyIDEx
    )
    from camera_utils import cleanup_macos_camera_connection, pump_macos_runloop
    # Don't import the threaded classes for now, implement direct connection test
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")
    EDS_ERR_OK = 0
    kEdsPropID_SaveTo = 0x0000000b
    kEdsSaveTo_Host = 1
    kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
    kEdsPropID_AEModuleMode = 0x00000100
    kEdsPropID_Evf_Mode = 0x00000501
    kEdsPropID_Evf_OutputDevice = 0x00000500
    kEdsEvfOutputDevice_PC = 0x02
    kEdsPropID_ProductName = 0x00000004
    kEdsPropID_BodyIDEx = 0x00000101
    IMPORTS_AVAILABLE = False


def process_camera_events(edsdk, iterations=10, delay=0.05, label=None):
    """Run EdsGetEvent multiple times to let the SDK deliver camera notifications."""
    for _ in range(iterations):
        try:
            edsdk.EdsGetEvent()
        except Exception as exc:
            prefix = f"[{label}] " if label else ""
            print(f"{prefix}⚠️  Event processing error: {exc}")
            break
        if platform.system() == "Darwin":
            pump_macos_runloop(duration_sec=max(delay, 0.02))
        else:
            time.sleep(delay)


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


def check_usb_devices():
    """Check if Canon camera is visible in USB devices"""
    print("\n🔌 Checking USB devices...")
    try:
        if platform.system() == "Darwin":
            # Use ioreg which is more reliable than system_profiler for real-time USB detection
            result = subprocess.run(
                ["ioreg", "-p", "IOUSB", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )
        else:
            result = subprocess.run(
                ["lsusb"],
                capture_output=True,
                text=True,
                timeout=10
            )
        
        output = result.stdout
        
        if 'Canon' in output and 'Digital Camera' in output:
            print("✅ Canon device found on USB bus")
            # Extract Canon device details from ioreg output
            lines = output.split('\n')
            for i, line in enumerate(lines):
                if 'Canon Digital Camera' in line:
                    print(f"  📷 {line.strip()}")
                    # Show relevant properties
                    for j in range(i+1, min(len(lines), i+15)):
                        if 'USBSpeed' in lines[j] or 'locationID' in lines[j] or 'USB Product Name' in lines[j]:
                            print(f"     {lines[j].strip()}")
                    break
            return True
        else:
            print("❌ No Canon devices found on USB bus")
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


def attempt_live_view_initialization(edsdk, camera):
    """
    Try to enable EVF output following Canon sample guidance.
    Returns True if both EVF output device and mode were set successfully.
    """
    print("\n🎥 Testing Live View property sequence...")
    success = False
    original_output = ctypes.c_uint32()
    original_mode = ctypes.c_uint32()
    have_original_output = False

    try:
        err = edsdk.EdsGetPropertyData(
            camera, kEdsPropID_Evf_OutputDevice, 0,
            ctypes.sizeof(original_output), ctypes.byref(original_output)
        )
        if err == EDS_ERR_OK:
            have_original_output = True
            print(f"   Current EVF output device: {original_output.value} (0x{original_output.value:02x})")
        else:
            print(f"   ⚠️  Could not read EVF output device (Error {err}). Assuming LCD only.")

        target_value = original_output.value if have_original_output else 0x01
        if not (target_value & kEdsEvfOutputDevice_PC):
            target_value |= kEdsEvfOutputDevice_PC

        print("   → Setting EVF output device to include PC...")
        new_output = ctypes.c_uint32(target_value)
        err = edsdk.EdsSetPropertyData(
            camera, kEdsPropID_Evf_OutputDevice, 0,
            ctypes.sizeof(new_output), ctypes.byref(new_output)
        )
        if err != EDS_ERR_OK:
            print(f"   ❌ Failed to set EVF output device (Error {err})")
            return False

        process_camera_events(edsdk, iterations=12, label="EVF Output Set")

        print("   → Enabling EVF mode...")
        evf_mode_on = ctypes.c_uint32(1)
        err = edsdk.EdsSetPropertyData(
            camera, kEdsPropID_Evf_Mode, 0,
            ctypes.sizeof(evf_mode_on), ctypes.byref(evf_mode_on)
        )
        if err != EDS_ERR_OK:
            print(f"   ❌ Camera rejected EVF mode enable (Error {err})")
            return False

        process_camera_events(edsdk, iterations=12, label="EVF Mode Enable")

        print("   ✅ Live view properties applied successfully (ready for frame downloads).")
        success = True
        return True
    finally:
        print("   ↩️  Restoring EVF settings...")
        try:
            evf_mode_off = ctypes.c_uint32(0)
            edsdk.EdsSetPropertyData(
                camera, kEdsPropID_Evf_Mode, 0,
                ctypes.sizeof(evf_mode_off), ctypes.byref(evf_mode_off)
            )
            process_camera_events(edsdk, iterations=6, label="EVF Mode Disable")
        except Exception as exc:
            print(f"   ⚠️  Error while disabling EVF mode during cleanup: {exc}")

        if have_original_output:
            try:
                edsdk.EdsSetPropertyData(
                    camera, kEdsPropID_Evf_OutputDevice, 0,
                    ctypes.sizeof(original_output), ctypes.byref(original_output)
                )
                process_camera_events(edsdk, iterations=6, label="EVF Output Restore")
            except Exception as exc:
                print(f"   ⚠️  Error while restoring EVF output device: {exc}")
        else:
            # If we never read the original value, at least revert to camera LCD.
            try:
                lcd_only = ctypes.c_uint32(0x01)
                edsdk.EdsSetPropertyData(
                    camera, kEdsPropID_Evf_OutputDevice, 0,
                    ctypes.sizeof(lcd_only), ctypes.byref(lcd_only)
                )
                process_camera_events(edsdk, iterations=6, label="EVF Output Default")
            except Exception as exc:
                print(f"   ⚠️  Error while reverting EVF output to LCD: {exc}")

        if success:
            print("   ✅ EVF settings restored.")
        else:
            print("   ℹ️  Cleanup completed after failed live view attempt.")


def test_camera_connection():
    """Test actual camera connection using direct EDSDK calls"""
    print("\n📷 Testing Camera Connection...")
    print("=" * 50)

    live_view_success = False
    
    # Check for USB devices first
    if not check_usb_devices():
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
        return False, False

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
            return False, False
        
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
        if platform.system() == "Darwin":
            print("   🔁 macOS runloop warm-up before enumerating cameras...")
            pump_macos_runloop(duration_sec=0.05, iterations=20)
        list_result = edsdk.EdsGetCameraList(ctypes.byref(camera_list))
        
        if list_result != EDS_ERR_OK:
            print(f"   ❌ Failed to get camera list: {list_result}")
            edsdk.EdsTerminateSDK()
            return False, False
        
        # Try multiple times to get camera count (Canon documentation requirement)
        max_attempts = 20
        camera_count = 0
        
        for attempt in range(max_attempts):
            # Process events before each attempt
            for _ in range(5):
                edsdk.EdsGetEvent()
            if platform.system() == "Darwin":
                pump_macos_runloop(duration_sec=0.05, iterations=6)
            
            count_val = ctypes.c_uint32(0)
            count_result = edsdk.EdsGetChildCount(camera_list, ctypes.byref(count_val))
            
            if count_result == EDS_ERR_OK and count_val.value > 0:
                camera_count = count_val.value
                print(f"   ✅ Found {camera_count} camera(s) on attempt {attempt + 1}")
                
                # Get the first camera for detailed inspection
                if camera_count > 0:
                    camera = ctypes.c_void_p()
                    cam_result = edsdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera))
                    if cam_result == EDS_ERR_OK:
                        # Open session to inspect camera state
                        session_result = edsdk.EdsOpenSession(camera)
                        if session_result == EDS_ERR_OK:
                            print("\n   Opening camera session for detailed inspection...")
                            inspect_camera_state(edsdk, camera)
                            live_view_success = attempt_live_view_initialization(edsdk, camera)
                            edsdk.EdsCloseSession(camera)
                            edsdk.EdsRelease(camera)
                        else:
                            print(f"   ⚠️  Could not open session for inspection: {session_result}")
                            edsdk.EdsRelease(camera)
                
                break
            
            if attempt < max_attempts - 1:
                print(f"   � Attempt {attempt + 1}/{max_attempts}: No cameras yet, retrying...")
                pump_macos_runloop(duration_sec=0.05, iterations=10)
                time.sleep(0.5)
        
        # Clean up
        edsdk.EdsRelease(camera_list)
        edsdk.EdsTerminateSDK()
        
        camera_success = camera_count > 0
        if camera_success:
            print("   🎉 Camera detection successful!")
            if live_view_success:
                print("   🎥 Live view property test passed.")
            else:
                print("   ⚠️  Live view property sequence is still failing. Check logs above.")
            print("\n💡 Next steps:")
            print("   1. Camera is properly connected and detected")
            print("   2. Run: python3 app.py to test full application")
        else:
            print("   ❌ No cameras detected by EDSDK after all attempts")
            print("\n🔧 Troubleshooting:")
            print("   1. Camera is detected at USB level but not by EDSDK")
            print("   2. Check camera is set to 'PC Remote' or 'PTP' mode")
            print("   3. Ensure camera is in shooting mode (not playback)")
            print("   4. Try power cycling camera while connected")
            print("   5. Check camera display shows 'PC' connection icon")
        
        return camera_success, live_view_success
    
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False, False


def inspect_camera_state(edsdk, camera):
    """Inspect detailed camera state for diagnostics."""
    print("\n📸 Camera State Inspection:")
    print("-" * 50)
    
    try:
        # Get AE Mode
        ae_mode = ctypes.c_uint32()
        err = edsdk.EdsGetPropertyData(camera, kEdsPropID_AEModuleMode, 0, 
                                      ctypes.sizeof(ae_mode), ctypes.byref(ae_mode))
        if err == EDS_ERR_OK:
            ae_mode_value = ae_mode.value
            print(f"  AE Mode: {ae_mode_value} (0x{ae_mode_value:08x})")
            if ae_mode_value <= 0x3F or ae_mode_value == 0xFFFFFFFF:
                print("  ✅ Valid AE mode value")
            else:
                print("  ⚠️  Abnormal AE mode value (may indicate camera state issue)")
        
        # Get EVF Mode
        evf_mode = ctypes.c_uint32()
        err = edsdk.EdsGetPropertyData(camera, kEdsPropID_Evf_Mode, 0,
                                      ctypes.sizeof(evf_mode), ctypes.byref(evf_mode))
        if err == EDS_ERR_OK:
            evf_mode_value = evf_mode.value
            print(f"  EVF Mode: {evf_mode_value}")
            if evf_mode_value == 0:
                print("  ✅ EVF Disabled")
            elif evf_mode_value == 1:
                print("  ✅ EVF Enabled")
            else:
                print("  ⚠️  Unexpected EVF mode value (may indicate bad state)")
        
        # Get EVF Output Device
        output_device = ctypes.c_uint32()
        err = edsdk.EdsGetPropertyData(camera, kEdsPropID_Evf_OutputDevice, 0,
                                      ctypes.sizeof(output_device), ctypes.byref(output_device))
        if err == EDS_ERR_OK:
            output_device_value = output_device.value
            print(f"  EVF Output Device: {output_device_value} (0x{output_device_value:02x})")
            
            devices = []
            if output_device_value & 0x01:
                devices.append("Camera LCD")
            if output_device_value & 0x02:
                devices.append("PC Screen")
            if output_device_value & 0x08:
                devices.append("PC Small")
            
            if devices:
                print(f"  Output targets: {', '.join(devices)}")
            
            if output_device_value & kEdsEvfOutputDevice_PC:
                print("  ✅ PC live view possible")
            else:
                print("  ⚠️  PC live view NOT enabled")
        
    except Exception as e:
        print(f"  ⚠️  Error inspecting camera state: {e}")


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
    
    # Step 2: Test camera connection (and live view preparation)
    camera_success, live_view_success = test_camera_connection()
    
    # Summary
    print("\n📊 Test Summary:")
    print(f"   EDSDK Loading: {'✅ PASS' if edsdk_success else '❌ FAIL'}")
    print(f"   Camera Connection: {'✅ PASS' if camera_success else '❌ FAIL'}")
    print(f"   Live View Prep: {'✅ PASS' if live_view_success else '❌ FAIL'}")
    
    if edsdk_success and camera_success and live_view_success:
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
