import os
import ctypes
import sys
import threading
import time
import queue

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from camera_constants import EDS_ERR_OK
    from camera_utils import cleanup_macos_camera_connection
except ImportError as e:
    print(f"Warning: Could not import camera modules: {e}")
    EDS_ERR_OK = 0

def test_edsdk():
    """Test EDSDK library loading with proper macOS cleanup and threading pattern"""
    
    print("🔧 Poly Canon Cam - EDSDK Connection Test")
    print("=" * 60)
    
    # Step 1: Perform macOS cleanup first (like our app does)
    print("\n1️⃣ Performing macOS system cleanup...")
    try:
        if 'cleanup_macos_camera_connection' in globals():
            cleanup_macos_camera_connection(
                extra_kill_canon_processes=True,
                verbose=True,
                send_log_func=lambda msg: print(f"[Cleanup] {msg}")
            )
            print("✅ macOS cleanup completed")
        else:
            print("⚠️  Skipping cleanup - camera_utils not available")
    except Exception as e:
        print(f"⚠️  Warning during cleanup: {e}")
    
    # Step 1.5: Check and fix macOS security attributes
    print("\n1️⃣➕ Checking macOS security attributes...")
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
        else:
            print("✅ No quarantine attribute found")
    except Exception as e:
        print(f"⚠️  Could not check security attributes: {e}")
    
    # Step 2: Verify EDSDK path and basic file properties
    print("\n2️⃣ Verifying EDSDK library...")
    edsdk_path = "./EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework/Versions/A/EDSDK"
    abs_path = os.path.abspath(edsdk_path)
    
    print(f"Working directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    print(f"EDSDK path: {abs_path}")
    print(f"File exists: {os.path.exists(abs_path)}")
    
    if not os.path.exists(abs_path):
        print("❌ EDSDK library not found!")
        return False
    
    print(f"✅ EDSDK library found")
    print(f"   Is file: {os.path.isfile(abs_path)}")
    print(f"   Readable: {os.access(abs_path, os.R_OK)}")
    print(f"   Executable: {os.access(abs_path, os.X_OK)}")
    
    # Step 3: Test EDSDK loading in a separate thread (like our app)
    print("\n3️⃣ Testing EDSDK loading in worker thread...")
    
    result_queue = queue.Queue()
    test_complete = threading.Event()
    
    def edsdk_worker():
        """Worker thread to test EDSDK loading - matches our app pattern"""
        try:
            print("[Worker] Starting EDSDK test worker thread...")
            print("[Worker] Loading EDSDK library...")
            
            # Try multiple loading strategies for macOS compatibility
            edsdk = None
            loading_strategies = [
                ("Direct CDLL", lambda: ctypes.CDLL(abs_path)),
                ("CDLL with RTLD_LOCAL", lambda: ctypes.CDLL(abs_path, mode=ctypes.RTLD_LOCAL)),
                ("CDLL with RTLD_GLOBAL", lambda: ctypes.CDLL(abs_path, mode=ctypes.RTLD_GLOBAL)),
            ]
            
            for strategy_name, loader in loading_strategies:
                try:
                    print(f"[Worker] Trying {strategy_name}...")
                    edsdk = loader()
                    print(f"[Worker] ✅ EDSDK library loaded successfully using {strategy_name}")
                    result_queue.put(("load_success", f"EDSDK loaded with {strategy_name}"))
                    break
                except Exception as e:
                    print(f"[Worker] ❌ {strategy_name} failed: {e}")
                    continue
            
            if not edsdk:
                print("[Worker] ❌ All loading strategies failed")
                result_queue.put(("load_failed", "All loading strategies failed"))
                return
            
            print("[Worker] Initializing EDSDK...")
            init_result = edsdk.EdsInitializeSDK()
            print(f"[Worker] SDK initialization result: {init_result}")
            
            if init_result == EDS_ERR_OK:
                print("[Worker] ✅ EDSDK initialized successfully")
                result_queue.put(("init_success", f"SDK initialized: {init_result}"))
                
                # Test getting camera list (basic functionality test)
                print("[Worker] Testing camera list retrieval...")
                camera_list = ctypes.c_void_p()
                list_result = edsdk.EdsGetCameraList(ctypes.byref(camera_list))
                print(f"[Worker] Camera list result: {list_result}")
                
                if list_result == EDS_ERR_OK:
                    print("[Worker] ✅ Camera list retrieved successfully")
                    
                    # Get camera count
                    count_val = ctypes.c_uint32(0)
                    count_result = edsdk.EdsGetChildCount(camera_list, ctypes.byref(count_val))
                    if count_result == EDS_ERR_OK:
                        print(f"[Worker] Found {count_val.value} camera(s)")
                        result_queue.put(("camera_count", count_val.value))
                    else:
                        print(f"[Worker] Failed to get camera count: {count_result}")
                    
                    # Clean up camera list
                    edsdk.EdsRelease(camera_list)
                else:
                    print(f"[Worker] ⚠️  Camera list failed: {list_result} (normal if no camera connected)")
                    result_queue.put(("camera_list_failed", list_result))
                
                # Clean shutdown
                print("[Worker] Terminating EDSDK...")
                term_result = edsdk.EdsTerminateSDK()
                print(f"[Worker] SDK termination result: {term_result}")
                result_queue.put(("terminate_success", term_result))
                
            else:
                print(f"[Worker] ❌ EDSDK initialization failed: {init_result}")
                result_queue.put(("init_failed", init_result))
                
        except Exception as e:
            print(f"[Worker] ❌ Exception in worker thread: {e}")
            result_queue.put(("worker_exception", str(e)))
        finally:
            test_complete.set()
    
    # Start the worker thread
    worker_thread = threading.Thread(target=edsdk_worker, daemon=True)
    worker_thread.name = "EDSDKTestWorker"
    worker_thread.start()
    
    # Wait for completion with timeout
    print("Waiting for worker thread completion (max 30 seconds)...")
    test_complete.wait(timeout=30.0)
    
    # Process results
    print("\n4️⃣ Test Results Summary:")
    print("-" * 30)
    
    results = []
    while not result_queue.empty():
        try:
            result = result_queue.get_nowait()
            results.append(result)
        except queue.Empty:
            break
    
    success_count = 0
    total_tests = 0
    
    for result_type, result_data in results:
        total_tests += 1
        if result_type == "load_success":
            print("✅ EDSDK library loading: SUCCESS")
            success_count += 1
        elif result_type == "init_success":
            print("✅ EDSDK initialization: SUCCESS")
            success_count += 1
        elif result_type == "camera_count":
            print(f"📷 Cameras detected: {result_data}")
            if result_data >= 0:  # Count is valid
                success_count += 1
            total_tests += 1
        elif result_type == "camera_list_failed":
            print(f"⚠️  Camera list failed: {result_data} (normal if no camera)")
        elif result_type == "terminate_success":
            print("✅ EDSDK termination: SUCCESS")
            success_count += 1
        elif result_type == "init_failed":
            print(f"❌ EDSDK initialization: FAILED ({result_data})")
        elif result_type == "worker_exception":
            print(f"❌ Worker exception: {result_data}")
    
    # Check if worker is still alive (indicates hanging)
    if worker_thread.is_alive():
        print("⚠️  Worker thread is still running (may be hung)")
        return False
    
    print(f"📊 Test Summary: {success_count}/{total_tests} core tests passed")
    
    if success_count >= 2:  # At least load + init should work
        print("🎉 EDSDK test completed successfully!")
        print("\n💡 Next steps:")
        print("   1. Connect a Canon camera via USB")
        print("   2. Set camera to PTP/PC mode")
        print("   3. Run: python3 app.py --auto-connect")
        return True
    else:
        print("❌ EDSDK test failed - check camera connection and permissions")
        print("\n🔧 macOS Security Troubleshooting:")
        print("   If you see 'library load disallowed by system policy' errors:")
        print("   1. In the macOS dialog, click 'Done' (NOT 'Move to Trash')")
        print("   2. Go to System Settings > Privacy & Security")
        print("   3. Scroll down to find 'EDSDK.framework' in the security section")
        print("   4. Click 'Allow Anyway' next to it")
        print("   5. Run the test again")
        print("\n   Alternative command-line fix:")
        print("   sudo xattr -d com.apple.quarantine 'EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework'")
        return False

if __name__ == "__main__":
    success = test_edsdk()
    sys.exit(0 if success else 1)
