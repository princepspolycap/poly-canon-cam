try:
    import syphon
    import numpy as np
    from syphon.utils.numpy import copy_image_to_mtl_texture
    SYPHON_AVAILABLE = True
    # It's possible create_mtl_texture might be needed from syphon.utils.raw depending on how texture is managed per frame
    # from syphon.utils.raw import create_mtl_texture
except ImportError:
    SYPHON_AVAILABLE = False
    syphon = None
    np = None
    print("Warning: Syphon not available. Virtual webcam functionality disabled.") 

class SyphonWebcamOutput:
    def __init__(self, server_name="CanonCamSyphon"):
        if not SYPHON_AVAILABLE:
            print(f"Warning: Syphon not available. {server_name} webcam output disabled.")
            
        self.server_name = server_name
        self.server = None
        self.texture = None
        self.is_running = False
        # Dimensions will be set on the first frame or explicitly
        self.width = 0
        self.height = 0

    def start(self, width, height):
        if not SYPHON_AVAILABLE:
            print("Syphon not available - virtual webcam start skipped")
            return
            
        if self.is_running:
            print("Syphon server already running.")
            return
        
        self.width = width
        self.height = height
        
        try:
            if not SYPHON_AVAILABLE:
                print("Syphon not available - cannot start server")
                return
                
            self.server = syphon.SyphonMetalServer(self.server_name)
            # Texture creation might be better here if size is fixed,
            # or it might be recreated if frame size can change.
            # For now, let's assume fixed size after start.
            # self.texture = create_mtl_texture(self.server.device, self.width, self.height) # Example from docs
            # Actual texture handling for dynamic frames will be refined.
            self.is_running = True
            print(f"Syphon server '{self.server_name}' started.")
        except Exception as e:
            print(f"Failed to start Syphon server: {e}")
            self.server = None
            self.is_running = False

    def send_frame(self, frame_rgb):
        if not SYPHON_AVAILABLE:
            return
            
        if not self.is_running or self.server is None:
            return

        if frame_rgb.shape[1] != self.width or frame_rgb.shape[0] != self.height:
            print("Frame dimensions do not match server configuration. Reconfiguring...")
            # Basic reconfiguration. More robust handling might be needed.
            # This might involve stopping and starting the server or recreating texture.
            # For now, let's just log and skip.
            # Ideally, texture should be managed to match frame_rgb dimensions.
            # self.stop()
            # self.start(frame_rgb.shape[1], frame_rgb.shape[0])
            # if not self.is_running: return
            print(f"Error: Frame size {frame_rgb.shape[1]}x{frame_rgb.shape[0]} does not match Syphon server {self.width}x{self.height}. Skipping frame.")
            return

        try:
            # Ensure frame is RGBA for Syphon Metal texture
            if frame_rgb.shape[2] == 3: # RGB
                frame_rgba = np.dstack((frame_rgb, np.full((self.height, self.width), 255, dtype=np.uint8)))
            elif frame_rgb.shape[2] == 4: # Already RGBA
                frame_rgba = frame_rgb
            else:
                print(f"Unsupported frame format with {frame_rgb.shape[2]} channels. Expected RGB or RGBA.")
                return

            # The syphon-python example creates one texture and updates it.
            # If self.texture is not created at start, it needs to be created here.
            if self.texture is None or \
               self.texture.width() != self.width or \
               self.texture.height() != self.height:
                # from syphon.metal import create_metal_texture # Correct import path if needed
                # This specific function might be slightly different, checking docs:
                # The example uses syphon.utils.raw.create_mtl_texture
                from syphon.utils.raw import create_mtl_texture as actual_create_mtl_texture
                self.texture = actual_create_mtl_texture(self.server.device, self.width, self.height)
                print(f"Syphon texture created: {self.width}x{self.height}")


            copy_image_to_mtl_texture(frame_rgba, self.texture)
            self.server.publish_frame_texture(self.texture)
        except Exception as e:
            print(f"Error sending frame to Syphon: {e}")

    def stop(self):
        if not SYPHON_AVAILABLE:
            return
            
        if self.server:
            try:
                self.server.stop()
                print(f"Syphon server '{self.server_name}' stopped.")
            except Exception as e:
                print(f"Error stopping Syphon server: {e}")
        self.is_running = False
        self.server = None
        self.texture = None # Release texture

if __name__ == '__main__':
    # Basic test usage
    if SYPHON_AVAILABLE:
        syphon_output = SyphonWebcamOutput("TestSyphon")
        syphon_output.start(640, 480)
        
        if syphon_output.is_running:
            # Create a dummy RGBA frame (e.g., red)
            import numpy as np
            dummy_frame_rgba = np.zeros((480, 640, 4), dtype=np.uint8)
            dummy_frame_rgba[:, :, 0] = 255  # Red channel
            dummy_frame_rgba[:, :, 3] = 255  # Alpha channel
            
            syphon_output.send_frame(dummy_frame_rgba)
            print("Sent dummy frame.")
            
            import time
            time.sleep(2)
            import time
            time.sleep(2)
            syphon_output.stop()
        else:
            print("Failed to start Syphon server.")
    else:
        print("Syphon not available - skipping test")
