#!/bin/bash
# Create macOS .icns icon file from logo.png
#
# This script converts logo.png into a multi-resolution .icns file
# that macOS uses for application icons.

set -e

LOGO_PNG="logo.png"
ICONSET_DIR="logo.iconset"
ICNS_FILE="logo.icns"

echo "🎨 Creating macOS icon from logo.png..."

# Check if logo.png exists
if [ ! -f "$LOGO_PNG" ]; then
    echo "❌ Error: logo.png not found in current directory"
    exit 1
fi

# Create iconset directory
mkdir -p "$ICONSET_DIR"

# Generate all required icon sizes using sips (built-in macOS tool)
echo "📐 Generating icon sizes..."

sips -z 16 16     "$LOGO_PNG" --out "$ICONSET_DIR/icon_16x16.png" > /dev/null 2>&1
sips -z 32 32     "$LOGO_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" > /dev/null 2>&1
sips -z 32 32     "$LOGO_PNG" --out "$ICONSET_DIR/icon_32x32.png" > /dev/null 2>&1
sips -z 64 64     "$LOGO_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" > /dev/null 2>&1
sips -z 128 128   "$LOGO_PNG" --out "$ICONSET_DIR/icon_128x128.png" > /dev/null 2>&1
sips -z 256 256   "$LOGO_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" > /dev/null 2>&1
sips -z 256 256   "$LOGO_PNG" --out "$ICONSET_DIR/icon_256x256.png" > /dev/null 2>&1
sips -z 512 512   "$LOGO_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" > /dev/null 2>&1
sips -z 512 512   "$LOGO_PNG" --out "$ICONSET_DIR/icon_512x512.png" > /dev/null 2>&1
sips -z 1024 1024 "$LOGO_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" > /dev/null 2>&1

# Convert iconset to icns file
echo "🔨 Converting to .icns format..."
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"

# Clean up temporary iconset directory
rm -rf "$ICONSET_DIR"

echo "✅ Created $ICNS_FILE successfully!"
echo "📦 Ready for py2app packaging"
