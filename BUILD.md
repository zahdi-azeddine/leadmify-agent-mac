# LeaDMify Agent Build Process

This document describes the automated build process for both Mac and Windows agents using GitHub Actions.

## Overview

The build process is automated via GitHub Actions workflow located at `.github/workflows/build-agents.yml`. This workflow builds both Mac and Windows agents whenever changes are pushed to the `main` branch or when manually triggered.

## Build Targets

### Mac Agent
- **Intel (x86_64)**: Built on `macos-13`
- **Apple Silicon (arm64)**: Built on `macos-14`
- **Output**: DMG files and ZIP archives for each architecture

### Windows Agent
- **Architecture**: x64 (64-bit)
- **Output**: Windows executable (`.exe`) and ZIP archive

## Workflow Structure

The workflow consists of two parallel jobs:

1. **mac-build**: Builds Mac agents for both Intel and Apple Silicon
2. **windows-build**: Builds Windows agent

## Mac Build Process

1. **Setup**: Installs Firefox and Geckodriver via Homebrew
2. **Python**: Sets up Python 3.11
3. **Dependencies**: Installs Python packages from `requirements.txt`
4. **Build**: Uses PyInstaller to create a windowed macOS application
5. **Package**: Creates DMG and ZIP archives
6. **Artifacts**: Uploads build artifacts

## Windows Build Process

1. **Setup**: Installs Firefox and Geckodriver
2. **Python**: Sets up Python 3.11
3. **Dependencies**: Installs Python packages from `automation/Windows/requirements.txt`
4. **Build**: Uses PyInstaller with `LeaDMify.spec` to create Windows executable
5. **Package**: Creates ZIP archive
6. **Artifacts**: Uploads build artifacts

## Manual Build

### Mac (Local)

```bash
cd automation/leadmify-agent-mac
pip install -r requirements.txt pyinstaller
pyinstaller \
  --noconfirm \
  --windowed \
  --name "LeaDMify Agent" \
  --icon "assets/icon.icns" \
  --add-data "ibot_hub.py:." \
  LeaDMifyAgent_mac.py
```

### Windows (Local)

```bash
cd automation/Windows
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm LeaDMify.spec
```

## Artifacts

After a successful build, artifacts are available in the GitHub Actions workflow run:

- **Mac Intel**: `LeaDMifyAgent-Mac-macos-13.dmg` and `.app.zip`
- **Mac Apple Silicon**: `LeaDMifyAgent-Mac-macos-14.dmg` and `.app.zip`
- **Windows**: `LeaDMifyAgent-Windows.zip` and `LeaDMify.exe`

## Dependencies

### Mac Requirements
- `requests`
- `selenium`
- `pyperclip`
- `pyobjc` (for macOS clipboard support)
- `certifi`

### Windows Requirements
- `requests`
- `selenium`
- `pyperclip`
- `certifi`
- `customtkinter` (for GUI)
- `Pillow` (for image handling)
- `pystray` (for system tray)
- `pywin32` (Windows-specific)

## File Structure

```
automation/
├── leadmify-agent-mac/
│   ├── .github/
│   │   └── workflows/
│   │       └── build-agents.yml    # Unified build workflow
│   ├── assets/
│   │   └── icon.icns               # Mac icon
│   ├── ibot_hub.py                 # Core automation engine
│   ├── LeaDMifyAgent_mac.py        # Mac agent application
│   └── requirements.txt             # Mac dependencies
└── Windows/
    ├── ibot_hub.py                  # Core automation engine (same as Mac)
    ├── LeaDMifyHubApp.py            # Windows agent application
    ├── LeaDMify.spec                # PyInstaller spec file
    ├── icon.ico                     # Windows icon
    └── requirements.txt              # Windows dependencies
```

## Notes

- Both Mac and Windows agents use the same `ibot_hub.py` engine
- The workflow triggers on pushes to `main` branch or manual dispatch
- Build artifacts are automatically uploaded and available for download
- The Windows build requires PyInstaller to bundle all dependencies into a single executable

## Troubleshooting

### Build Failures

1. **Missing Dependencies**: Ensure all dependencies are listed in `requirements.txt`
2. **PyInstaller Issues**: Check that all hidden imports are specified in `LeaDMify.spec`
3. **Path Issues**: Verify that file paths in the workflow are correct relative to the repository root

### Local Build Issues

1. **Geckodriver**: Ensure Geckodriver is installed and in PATH
2. **Firefox**: Ensure Firefox is installed (required for Selenium)
3. **Python Version**: Use Python 3.11 for consistency with CI/CD

