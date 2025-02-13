import ctypes
import os

def test_sdk():
    print("Current working directory:", os.getcwd())
    print("\n1. Loading EDSDK...")
    try:
        path = "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"
        edsdk = ctypes.CDLL(path)
        print("✓ EDSDK loaded successfully")
        
        print("\n2. Initializing SDK...")
        result = edsdk.EdsInitializeSDK()
        if result == 0:  # EDS_ERR_OK
            print("✓ SDK initialized successfully")
        else:
            print(f"✗ SDK initialization failed with error: {result}")
            return
            
        print("\n3. Getting camera list...")
        camera_list = ctypes.c_void_p()
        result = edsdk.EdsGetCameraList(ctypes.byref(camera_list))
        if result == 0:
            print("✓ Got camera list")
        else:
            print(f"✗ Failed to get camera list, error: {result}")
            return
            
        print("\n4. Getting camera count...")
        count = ctypes.c_uint32()
        result = edsdk.EdsGetChildCount(camera_list, ctypes.byref(count))
        if result == 0:
            print(f"✓ Found {count.value} camera(s)")
        else:
            print(f"✗ Failed to get camera count, error: {result}")
            return
            
        print("\nChecking bundle paths:")
        bundles = [
            "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/CHHLLite.bundle",
            "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EdsImage.bundle"
        ]
        for bundle in bundles:
            print(f"\nChecking {bundle}")
            if os.path.exists(bundle):
                print(f"✓ Bundle exists")
                print(f"Permissions: {oct(os.stat(bundle).st_mode)[-3:]}")
                if os.path.exists(f"{bundle}/Contents/MacOS"):
                    binary = os.listdir(f"{bundle}/Contents/MacOS")[0]
                    print(f"Binary: {binary}")
                    print(f"Binary permissions: {oct(os.stat(f'{bundle}/Contents/MacOS/{binary}').st_mode)[-3:]}")
            else:
                print("✗ Bundle not found")
                
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        return False
    finally:
        if 'edsdk' in locals():
            print("\nTerminating SDK...")
            edsdk.EdsTerminateSDK()
    
    return True

if __name__ == "__main__":
    test_sdk()
