import os
import ctypes
import sys

def test_edsdk():
    """Test EDSDK library loading with detailed debugging"""
    edsdk_path = "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"
    abs_path = os.path.abspath(edsdk_path)
    
    print(f"Current working directory: {os.getcwd()}")
    print(f"Python version: {sys.version}")
    print(f"Looking for EDSDK at: {abs_path}")
    print(f"Path exists: {os.path.exists(abs_path)}")
    
    if os.path.exists(abs_path):
        print(f"\nFile details:")
        print(f"Is file: {os.path.isfile(abs_path)}")
        print(f"Access rights:")
        print(f"- Readable: {os.access(abs_path, os.R_OK)}")
        print(f"- Executable: {os.access(abs_path, os.X_OK)}")
        
        try:
            print("\nAttempting to load EDSDK...")
            edsdk = ctypes.CDLL(abs_path)
            print("Successfully loaded EDSDK!")
            
            # Try to initialize SDK
            print("\nAttempting to initialize SDK...")
            result = edsdk.EdsInitializeSDK()
            print(f"SDK initialization result: {result}")
            
            return True
            
        except Exception as e:
            print(f"\nError loading EDSDK: {str(e)}")
            return False
    else:
        print("\nEDSDK library not found!")
        return False

if __name__ == "__main__":
    test_edsdk()
