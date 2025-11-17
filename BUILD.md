# 🚀 Quick Build Guide

## One-Command Build

```bash
chmod +x build_app.sh && ./build_app.sh
```

This creates: `dist/Poly Canon Cam.app`

## Launch It

```bash
open "dist/Poly Canon Cam.app"
```

Or just double-click it in Finder!

## What Gets Built

```
Poly Canon Cam.app
├── Your custom logo.png as the app icon ✅
├── All Python code bundled ✅
├── All dependencies (numpy, opencv, PIL, etc) ✅
├── EDSDK framework ✅
├── Virtual webcam support (Syphon + PyVirtualCam) ✅
└── Ready to drag to Applications folder! ✅
```

## Build Options

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `./build_app.sh` | Full standalone app | For final distribution |
| `./build_app.sh --dev` | Faster alias build | During development/testing |
| `./build_app.sh --dmg` | Create distributable DMG | For sharing with others |

## After Building

1. **Test it**: `open "dist/Poly Canon Cam.app"`
2. **Install it**: `cp -R "dist/Poly Canon Cam.app" /Applications/`
3. **Launch from Spotlight**: Just type "Poly Canon Cam"

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "App is damaged" error | Run: `xattr -cr "dist/Poly Canon Cam.app"` |
| Icon doesn't show | Run: `./create_icon.sh` first |
| EDSDK not found | Check that `EDSDK 13.19.10 Macintosh/` exists |
| Security warning | System Settings → Privacy & Security → Allow |

## Full Documentation

See [PACKAGING.md](PACKAGING.md) for complete details on:
- Icon creation
- Code signing
- DMG creation
- Distribution
- Advanced configuration

---

**That's it!** Just run `./build_app.sh` and you'll have a professional macOS app! 🎬
