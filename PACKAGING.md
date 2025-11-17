# macOS Application Packaging

This directory contains everything needed to package Poly Canon Cam as a standalone macOS application.

## Quick Start

```bash
# Make scripts executable
chmod +x create_icon.sh build_app.sh

# Build the app (production mode)
./build_app.sh

# The app will be in: dist/Poly Canon Cam.app
# Launch it:
open "dist/Poly Canon Cam.app"
```

## Build Options

### Production Build (Standalone)
```bash
./build_app.sh
```
Creates a fully self-contained `.app` bundle with all dependencies. This is what you'd distribute to others.

### Development Build (Faster)
```bash
./build_app.sh --dev
```
Creates an alias build that links to your source code. Much faster for testing, but requires the source directory.

### Create DMG for Distribution
```bash
./build_app.sh --dmg
```
Builds the app and packages it into a `.dmg` disk image for easy distribution.

## What Gets Packaged

```
Poly Canon Cam.app/
├── Contents/
│   ├── Info.plist                    # App metadata (name, version, icon, permissions)
│   ├── MacOS/
│   │   └── Poly Canon Cam            # Python executable
│   ├── Resources/
│   │   ├── logo.icns                 # App icon (all resolutions)
│   │   ├── logo.png                  # Original logo
│   │   └── lib/python3.11/           # All Python dependencies
│   │       ├── numpy/
│   │       ├── cv2/
│   │       ├── PIL/
│   │       ├── syphon/
│   │       ├── pyvirtualcam/
│   │       └── ... (all other packages)
│   └── Frameworks/
│       ├── Python.framework          # Python 3.11 runtime
│       └── EDSDK.framework           # Canon SDK
```

## Files Created

| File | Purpose |
|------|---------|
| `setup.py` | py2app configuration (dependencies, icon, permissions) |
| `create_icon.sh` | Converts `logo.png` → `logo.icns` (macOS icon format) |
| `build_app.sh` | Automates the entire build process |
| `logo.icns` | Generated multi-resolution icon file |

## Build Process

The `build_app.sh` script does the following:

1. ✅ **Activates virtual environment**
2. 🎨 **Creates icon** from `logo.png` using `create_icon.sh`
3. 🧹 **Cleans** previous builds
4. 🔨 **Runs py2app** to create the bundle
5. 📚 **Copies EDSDK** framework into `Contents/Frameworks/`
6. 🔓 **Removes quarantine** attributes (for local testing)
7. 🔗 **Updates framework paths** in the binary
8. 🔏 **Signs app** (optional, if `APPLE_DEVELOPER_ID` is set)
9. 💿 **Creates DMG** (optional, if `--dmg` flag used)

## Testing the App

After building:

```bash
# Method 1: Command line
open "dist/Poly Canon Cam.app"

# Method 2: Finder
# Double-click "dist/Poly Canon Cam.app" in Finder
```

### Expected Behavior

1. ✅ App icon appears in Dock
2. ✅ Window opens with GUI
3. ✅ Camera connects when "Connect & Start Live View" clicked
4. ✅ Virtual webcam starts (OBS + Syphon)
5. ✅ Frames stream smoothly

### Verification Checklist

After running `./build_app.sh` we verify the bundle by:

1. Ensuring `dist/Poly Canon Cam.app` exists and contains `Contents/Frameworks/EDSDK.framework`.
2. Running `dist/Poly Canon Cam.app/Contents/MacOS/Poly Canon Cam` once from Terminal to confirm all Python modules import correctly.
3. Launching the GUI via `open "dist/Poly Canon Cam.app"` and watching the startup log for Syphon / PyVirtualCam availability.
4. Connecting a camera and confirming live view + virtual webcam start without restarting (look for `Started outputs: Syphon, Virtual Camera` and frame-delivery stats).

If all four checks pass, the build is production-ready.

## Troubleshooting

### "App is damaged and can't be opened"

This is macOS Gatekeeper security. Fix:

```bash
# Remove quarantine attribute
xattr -cr "dist/Poly Canon Cam.app"

# Or run the build script again (it does this automatically)
```

### "Python cannot open EDSDK framework"

The framework path might not be set correctly. Verify:

```bash
# Check if EDSDK is in the bundle
ls -la "dist/Poly Canon Cam.app/Contents/Frameworks/EDSDK.framework"

# Check binary load paths
otool -L "dist/Poly Canon Cam.app/Contents/MacOS/Poly Canon Cam"
```

If missing, manually copy:

```bash
cp -R "EDSDK 13.19.10 Macintosh/Framework/EDSDK.framework" \
      "dist/Poly Canon Cam.app/Contents/Frameworks/"
```

### Security Prompts

First launch will trigger:

1. **"System Extension Blocked"** → Go to System Settings → Privacy & Security → Allow
2. **Camera Access** → Allow in the prompt
3. **USB Access** → Allow in the prompt

### App Won't Start (Silent Crash)

Check Console.app for crash logs:

1. Open **Console.app**
2. Filter for "Poly Canon Cam"
3. Look for Python tracebacks or framework load errors

## Code Signing (Optional)

For distribution outside your machine:

```bash
# Set your Apple Developer ID
export APPLE_DEVELOPER_ID="Developer ID Application: Your Name (TEAM_ID)"

# Build with signing
./build_app.sh

# Verify signature
codesign -vvv --deep --strict "dist/Poly Canon Cam.app"
```

### Notarization (For Public Distribution)

If you want to distribute the app publicly:

```bash
# Create signed DMG
./build_app.sh --dmg

# Notarize with Apple
xcrun notarytool submit PolyCanonCam-v1.0.0.dmg \
    --apple-id your@email.com \
    --team-id TEAM_ID \
    --password app-specific-password \
    --wait

# Staple the notarization ticket
xcrun stapler staple PolyCanonCam-v1.0.0.dmg
```

## Distribution

### For Personal Use
Just copy the `.app` to your Applications folder:

```bash
cp -R "dist/Poly Canon Cam.app" /Applications/
```

### For Sharing (Casual)
Share the `.app` file directly. Recipients will need to:
1. Drag to Applications
2. Right-click → Open (first time only)
3. Allow security prompts

### For Public Distribution
Create a signed and notarized DMG (see Code Signing section above).

## Updating the App

To rebuild after code changes:

```bash
# Quick rebuild (dev mode)
./build_app.sh --dev

# Full rebuild (production)
./build_app.sh
```

## Icon Updates

If you change `logo.png`:

```bash
# Regenerate icon
./create_icon.sh

# Rebuild app
./build_app.sh
```

## Advanced Configuration

Edit `setup.py` to customize:

- **App name/version**: Change `CFBundleName`, `CFBundleVersion`
- **Bundle ID**: Change `CFBundleIdentifier`
- **Minimum macOS version**: Change `LSMinimumSystemVersion`
- **Included packages**: Add to `packages` list
- **Extra resources**: Add to `DATA_FILES`

## Dependencies

The build process requires:

- ✅ Python 3.11 (already in your venv)
- ✅ py2app (installed by build script)
- ✅ iconutil (built into macOS)
- ✅ sips (built into macOS)
- ✅ All packages from `requirements.txt`

No external tools needed!

## File Sizes

Expect the `.app` bundle to be:
- **~150-250 MB** (includes Python runtime, all dependencies, EDSDK)
- **~100 MB** when compressed to DMG

## Performance

The packaged app performs identically to running `python app.py`:
- ✅ Same frame rates
- ✅ Same EDSDK performance
- ✅ Same virtual webcam quality
- ✅ Slightly faster startup (no interpreter initialization)

## Maintenance

When updating dependencies:

```bash
# Update requirements
pip install --upgrade package_name
pip freeze > requirements.txt

# Rebuild app with new dependencies
./build_app.sh
```

---

**Ready to build?** Just run `./build_app.sh` and you'll have a launchable macOS app! 🚀
