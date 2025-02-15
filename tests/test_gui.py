"""
GUI Tests Module

This module contains tests for the GUI application functionality,
focusing on window creation, widget initialization, and basic interactions.
"""

import unittest
import tkinter as tk
from src.gui.app import create_app, CameraApp

class TestGUIApp(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        self.root = tk.Tk()
        self.app = CameraApp(self.root)

    def tearDown(self):
        """Clean up after each test"""
        if self.app:
            self.app.stop_camera()  # Ensure camera is stopped
        self.root.destroy()

    def test_window_creation(self):
        """Test main window creation and configuration"""
        self.assertEqual(self.root.title(), 
                        "Canon Camera Viewer - Princeps Polycap Productions",
                        "Window title not set correctly")
        
        # Check main widgets exist
        self.assertIsNotNone(self.app.main_frame, "Main frame not created")
        self.assertIsNotNone(self.app.canvas, "Preview canvas not created")
        self.assertIsNotNone(self.app.btn_frame, "Button frame not created")
        self.assertIsNotNone(self.app.status_label, "Status label not created")

    def test_button_states(self):
        """Test initial button states and state changes"""
        # Initial states
        self.assertEqual(self.app.start_btn['state'], 'normal',
                        "Start button should be enabled initially")
        self.assertEqual(self.app.stop_btn['state'], 'disabled',
                        "Stop button should be disabled initially")
        
        # Test state change logic (without actual camera)
        self.app.is_running = True
        self.app.start_btn.configure(state=tk.DISABLED)
        self.app.stop_btn.configure(state=tk.NORMAL)
        
        self.assertEqual(self.app.start_btn['state'], 'disabled',
                        "Start button should be disabled when running")
        self.assertEqual(self.app.stop_btn['state'], 'normal',
                        "Stop button should be enabled when running")

    def test_canvas_configuration(self):
        """Test canvas setup and dimensions"""
        self.assertEqual(self.app.canvas['width'], 1280,
                        "Canvas width not set correctly")
        self.assertEqual(self.app.canvas['height'], 720,
                        "Canvas height not set correctly")
        self.assertEqual(self.app.canvas['bg'], 'black',
                        "Canvas background color not set correctly")

    def test_queue_initialization(self):
        """Test frame queue setup"""
        self.assertEqual(self.app.frame_queue.maxsize, 1,
                        "Frame queue size not set correctly")
        self.assertTrue(self.app.frame_queue.empty(),
                       "Frame queue should be empty initially")

    def test_create_app_function(self):
        """Test the create_app factory function"""
        app = create_app()
        self.assertIsInstance(app, CameraApp,
                            "create_app should return a CameraApp instance")
        self.assertIsInstance(app.root, tk.Tk,
                            "App root should be a Tk instance")
        app.root.destroy()

    def test_status_label(self):
        """Test status label initialization and updates"""
        initial_text = self.app.status_label['text']
        self.assertEqual(initial_text, "Camera: Disconnected",
                        "Initial status text incorrect")
        
        # Test status update
        new_status = "Camera: Connected"
        self.app.status_label.configure(text=new_status)
        self.assertEqual(self.app.status_label['text'], new_status,
                        "Status label not updating correctly")

if __name__ == '__main__':
    unittest.main()
