#!/bin/bash
# Camera Connection Testing & Cleanup Script
# This script performs pre-test cleanup and verification

set -e  # Exit on error

echo "🎯 Poly Canon Cam - Camera Connection Testing Script"
echo "=================================================="
echo ""

# Step 1: Kill macOS image services
echo "📋 Step 1: Killing macOS image services..."
echo "   Running: sudo killall PTPCamera"
sudo killall PTPCamera 2>/dev/null || echo "   ℹ️  PTPCamera not running"

echo "   Running: sudo killall 'Image Capture Extension'"
sudo killall "Image Capture Extension" 2>/dev/null || echo "   ℹ️  Image Capture Extension not running"

echo "   ✅ Image services cleanup complete"
echo ""

# Step 2: Verify USB state
echo "📋 Step 2: Verifying USB state..."
echo "   Checking for Canon device on USB bus..."

CANON_DEVICE=$(ioreg -p IOUSB -l 2>/dev/null | grep -i "Canon Digital Camera" || echo "")

if [ -z "$CANON_DEVICE" ]; then
    echo "   ❌ No Canon device found on USB bus"
    echo ""
    echo "🔧 Troubleshooting:"
    echo "   1. Connect Canon camera via USB-C"
    echo "   2. Power on camera"
    echo "   3. Set camera to PTP/PC connection mode"
    echo "   4. If using hub/dock, try direct connection to Mac"
    echo ""
    echo "📖 See: CAMERA_CLEANUP_GUIDE.md"
    exit 1
else
    echo "   ✅ Canon device found!"
    echo ""
    echo "   Device Details:"
    ioreg -p IOUSB -l 2>/dev/null | grep -i "Canon Digital Camera" -A 10 | head -15
fi

echo ""

# Step 3: Check device speed and configuration
echo "📋 Step 3: Verifying device speed and configuration..."

DEVICE_SPEED=$(ioreg -p IOUSB -l 2>/dev/null | grep -i "Device Speed" | head -1 || echo "")
CONFIG=$(ioreg -p IOUSB -l 2>/dev/null | grep "kUSBCurrentConfiguration" | head -1 || echo "")

if [[ "$DEVICE_SPEED" == *"3"* ]]; then
    echo "   ✅ Device Speed 3 (SuperSpeed) detected"
else
    echo "   ⚠️  Device Speed may not be optimal"
fi

if [[ "$CONFIG" == *"1"* ]]; then
    echo "   ✅ Configuration 1 active"
else
    echo "   ⚠️  Configuration state uncertain"
fi

echo ""

# Step 4: Run the comprehensive test
echo "📋 Step 4: Running comprehensive camera test..."
echo "   Path: tests/test_camera_connection.py"
echo ""

cd /Users/princeps/Projects/Poly186/poly-canon-cam

python3.11 tests/test_camera_connection.py

echo ""
echo "=================================================="
echo "✅ Testing complete!"
echo ""
echo "Next steps:"
echo "1. Review test output above"
echo "2. If camera detection failed, check USB connection"
echo "3. If successful, run: python3.11 app.py"
echo "4. Click 'Connect Camera' to test live view"
echo ""
