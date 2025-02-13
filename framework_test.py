import ctypes
import os

def test_load():
    print("Current working directory:", os.getcwd())
    print("Attempting to load EDSDK...")
    try:
        # First try direct path
        path = "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"
        print(f"Trying path: {path}")
        print(f"File exists: {os.path.exists(path)}")
        if os.path.exists(path):
            print(f"File permissions: {oct(os.stat(path).st_mode)[-3:]}")
        edsdk = ctypes.CDLL(path)
        print("Successfully loaded EDSDK!")
        return True
    except Exception as e:
        print(f"Error loading EDSDK: {e}")
        return False

if __name__ == "__main__":
    test_load()
