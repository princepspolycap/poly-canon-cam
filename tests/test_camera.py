"""
Camera Module Tests

This module contains tests for the Canon camera interface functionality,
including SDK loading, camera connection, and live view operations.
"""

import unittest
import os
import ctypes
from src.camera import CanonCamera, CameraError

class TestCanonCamera(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        self.camera = None

    def tearDown(self):
        """Clean up after each test"""
        if self.camera:
            self.camera.disconnect()

    def test_edsdk_loading(self):
        """Test EDSDK library loading"""
        expected_path = "./EDSDK 13.18.40 Macintosh/EDSDK.framework/Versions/A/EDSDK"
        self.assertTrue(os.path.exists(expected_path), 
                       "EDSDK library not found at expected path")
        
        try:
            edsdk = ctypes.CDLL(expected_path)
            self.assertIsNotNone(edsdk, "Failed to load EDSDK library")
        except Exception as e:
            self.fail(f"Failed to load EDSDK: {e}")

    def test_camera_initialization(self):
        """Test camera object initialization"""
        try:
            self.camera = CanonCamera()
            self.assertIsNotNone(self.camera.edsdk, "EDSDK not initialized")
        except Exception as e:
            self.fail(f"Camera initialization failed: {e}")

    def test_camera_context_manager(self):
        """Test camera context manager protocol"""
        try:
            with CanonCamera() as camera:
                self.assertIsNotNone(camera.edsdk, "EDSDK not initialized in context")
                self.assertFalse(camera.ui_locked, "UI should not be locked initially")
                self.assertFalse(camera.live_view_active, "Live view should not be active initially")
        except Exception as e:
            self.fail(f"Context manager failed: {e}")

    @unittest.skipIf(not os.environ.get('CAMERA_CONNECTED'), 
                    "Physical camera required for this test")
    def test_camera_connection(self):
        """Test camera connection (requires physical camera)"""
        self.camera = CanonCamera()
        try:
            self.camera.connect()
            self.assertIsNotNone(self.camera.camera, "Camera handle not created")
        except CameraError as e:
            self.fail(f"Camera connection failed: {e}")

    @unittest.skipIf(not os.environ.get('CAMERA_CONNECTED'), 
                    "Physical camera required for this test")
    def test_live_view(self):
        """Test live view operations (requires physical camera)"""
        self.camera = CanonCamera()
        try:
            self.camera.connect()
            success = self.camera.start_live_view()
            self.assertTrue(success, "Failed to start live view")
            self.assertTrue(self.camera.live_view_active, "Live view not marked as active")
            
            evf_image = self.camera.create_evf_image()
            self.assertIsNotNone(evf_image, "Failed to create EVF image")
            
            image_data = self.camera.download_evf_image(evf_image)
            self.assertIsNotNone(image_data, "Failed to download EVF image")
            
            self.camera.release_evf_image(evf_image)
            success = self.camera.stop_live_view()
            self.assertTrue(success, "Failed to stop live view")
            self.assertFalse(self.camera.live_view_active, "Live view still marked as active")
            
        except CameraError as e:
            self.fail(f"Live view test failed: {e}")

if __name__ == '__main__':
    unittest.main()
