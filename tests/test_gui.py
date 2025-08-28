"""
GUI Tests Module

This module contains tests for the GUI application functionality,
focusing on window creation, widget initialization, and basic interactions.
"""

import unittest
import tkinter as tk
import queue
from src.gui import create_app, CameraApp
from src import gui_style

class TestGUIApp(unittest.TestCase):
    def setUp(self):
        """Set up test environment before each test"""
        self.root = tk.Tk()
        self.app = CameraApp(self.root)

    def tearDown(self):
        """Clean up after each test"""
        if self.app:
            # Ensure worker threads and resources are stopped
            try:
                self.app.cleanup_resources()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_window_creation(self):
        """Test main window creation and configuration"""
        self.assertEqual(self.root.title(), 
                        "Canon Camera Viewer - Princeps Polycap Productions",
                        "Window title not set correctly")
        
        # Check main widgets exist (updated names)
        self.assertIsNotNone(self.app.main_container, "Main container not created")
        self.assertIsNotNone(self.app.canvas, "Preview canvas not created")
        self.assertIsNotNone(self.app.connection_buttons_frame, "Connection button frame not created")
        self.assertIsNotNone(self.app.connection_label, "Connection label not created")

    def test_button_states(self):
        """Test initial button states and state changes"""
        # Initial states (updated to match current UI logic)
        self.assertEqual(self.app.connect_button['state'], 'normal',
                         "Connect button should be enabled initially")
        self.assertEqual(self.app.disconnect_button['state'], 'disabled',
                         "Disconnect button should be disabled initially")
        self.assertEqual(self.app.start_lv_button['state'], 'disabled',
                         "Start Live View should be disabled until connected")
        self.assertEqual(self.app.stop_lv_button['state'], 'disabled',
                         "Stop Live View should be disabled initially")

    def test_canvas_configuration(self):
        """Test canvas setup and dimensions"""
        # Validate canvas visual configuration (colors)
        self.assertEqual(str(self.app.canvas['bg']).lower(), gui_style.COLORS['bg_dark'].lower(),
                         "Canvas background color not set correctly")
        self.assertEqual(str(self.app.canvas['highlightbackground']).lower(), gui_style.COLORS['border'].lower(),
                         "Canvas border color not set correctly")

    def test_queue_initialization(self):
        """Test frame queue setup"""
        # Updated: verify command and data queues are initialized and empty
        self.assertIsInstance(self.app.camera_command_queue, queue.Queue,
                              "camera_command_queue should be a Queue")
        self.assertIsInstance(self.app.camera_data_queue, queue.Queue,
                              "camera_data_queue should be a Queue")
        self.assertTrue(self.app.camera_command_queue.empty(),
                        "camera_command_queue should be empty initially")
        self.assertTrue(self.app.camera_data_queue.empty(),
                        "camera_data_queue should be empty initially")

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
        # Initial connection status via StringVar
        initial_text = self.app.connection_var.get()
        self.assertEqual(initial_text, "Disconnected",
                         "Initial connection status text incorrect")

        # Test status update via StringVar
        new_status = "Connected"
        self.app.connection_var.set(new_status)
        self.assertEqual(self.app.connection_var.get(), new_status,
                         "Connection status not updating correctly")

if __name__ == '__main__':
    unittest.main()
