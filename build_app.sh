#!/bin/bash
# Build Poly Canon Cam as a macOS .app bundle
#
# This script automates the full packaging process:
# 1. Creates the icon file from logo.png
# 2. Cleans previous builds
# 3. Runs py2app to create the bundle
# 4. Copies EDSDK framework into the bundle
# 5. Removes quarantine attributes (for local use)
# 6. Optionally signs the app (requires Apple Developer ID)

set -e

VENV_PATH=".venv"
APP_NAME="Poly Canon Cam"
BUILD_DIR="dist"
EDSDK_PATH="EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework"

echo "════════════════════════════════════════════════════════════"
echo "🎬 Building Poly Canon Cam for macOS"
echo "   Princeps Polycap Productions"
echo "════════════════════════════════════════════════════════════"

# Step 1: Check virtual environment
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Step 2: Install py2app if needed
echo "📦 Ensuring py2app is installed..."
pip install --quiet --upgrade py2app

# Step 3: Create icon
if [ -f "logo.png" ]; then
    echo "🎨 Creating application icon..."
    chmod +x create_icon.sh
    ./create_icon.sh
else
    echo "⚠️  Warning: logo.png not found, app will use default icon"
fi

# Step 4: Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/ "*.egg-info"

# Step 5: Run py2app in alias mode for development or standalone for distribution
echo "🔨 Building application bundle..."
if [ "$1" == "--dev" ]; then
    echo "   (Development mode: alias build)"
    python setup.py py2app -A
else
    echo "   (Production mode: standalone build)"
    python setup.py py2app
fi

# Step 6: Verify the app was created
APP_PATH="$BUILD_DIR/$APP_NAME.app"
if [ ! -d "$APP_PATH" ]; then
    echo "❌ Failed to create application bundle"
    exit 1
fi

echo "✅ Application bundle created at: $APP_PATH"

# Step 7: Copy EDSDK framework into the bundle
echo "📚 Copying EDSDK framework into bundle..."
RESOURCES_DIR="$APP_PATH/Contents/Resources"
FRAMEWORKS_DIR="$APP_PATH/Contents/Frameworks"
mkdir -p "$FRAMEWORKS_DIR"
mkdir -p "$RESOURCES_DIR"

if [ -d "$EDSDK_PATH" ]; then
    # Copy to Resources (where app.py looks for it)
    echo "   → Copying to Resources directory..."
    cp -R "EDSDK 13.19.10 Macintosh" "$RESOURCES_DIR/"
    
    # Also copy framework to Frameworks for proper linking
    echo "   → Copying framework to Frameworks directory..."
    rm -rf "$FRAMEWORKS_DIR/EDSDK.framework"
    cp -R "$EDSDK_PATH" "$FRAMEWORKS_DIR/"
    
    echo "✅ EDSDK copied successfully"
else
    echo "⚠️  Warning: EDSDK not found at $EDSDK_PATH"
    echo "   You may need to manually copy it"
fi

# Step 8: Remove quarantine attributes (for local testing)
echo "🔓 Removing quarantine attributes..."
xattr -cr "$APP_PATH" 2>/dev/null || true
xattr -cr "$FRAMEWORKS_DIR/EDSDK.framework" 2>/dev/null || true

# Step 9: Update framework paths in the binary
echo "🔗 Updating framework load paths..."
BINARY_PATH="$APP_PATH/Contents/MacOS/$APP_NAME"
if [ -f "$BINARY_PATH" ]; then
    # Update the EDSDK framework path to be relative to the app bundle
    install_name_tool -change \
        "@executable_path/../Frameworks/EDSDK.framework/Versions/A/EDSDK" \
        "@executable_path/../Frameworks/EDSDK.framework/Versions/A/EDSDK" \
        "$BINARY_PATH" 2>/dev/null || true
    
    echo "✅ Framework paths updated"
fi

# Step 10: Optional code signing (requires Apple Developer ID)
if [ -n "$APPLE_DEVELOPER_ID" ]; then
    echo "🔏 Signing application with Apple Developer ID..."
    codesign --force --deep --sign "$APPLE_DEVELOPER_ID" "$APP_PATH"
    echo "✅ Application signed successfully"
else
    echo "ℹ️  Skipping code signing (set APPLE_DEVELOPER_ID to sign)"
fi

# Step 11: Create a DMG for distribution (optional)
if [ "$1" == "--dmg" ] || [ "$2" == "--dmg" ]; then
    echo "💿 Creating disk image..."
    DMG_NAME="PolyCanonCam-v1.0.0.dmg"
    
    # Remove old DMG if exists
    rm -f "$DMG_NAME"
    
    # Create DMG
    hdiutil create -volname "Poly Canon Cam" \
        -srcfolder "$APP_PATH" \
        -ov -format UDZO \
        "$DMG_NAME"
    
    echo "✅ Disk image created: $DMG_NAME"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ BUILD COMPLETE!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📦 Application: $APP_PATH"
echo ""
echo "🚀 To run the app:"
echo "   open \"$APP_PATH\""
echo ""
echo "📋 To test:"
echo "   1. Double-click the app in Finder"
echo "   2. Or run: open \"$APP_PATH\""
echo ""
echo "💡 Build options:"
echo "   ./build_app.sh          - Production build (standalone)"
echo "   ./build_app.sh --dev    - Development build (faster, uses source)"
echo "   ./build_app.sh --dmg    - Create distributable DMG"
echo ""
echo "🔧 Troubleshooting:"
echo "   - If security warnings appear, go to:"
echo "     System Settings → Privacy & Security → Allow"
echo "   - Check Console.app for crash logs if app won't start"
echo ""
