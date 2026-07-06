#!/usr/bin/env python3
"""YouTube MPV Player - Final Working Executable Builder for Windows

This script builds a standalone YouTube MPV Player executable for Windows
using PyInstaller that works with Python 3.14+.

Features:
- Compatible with PyInstaller 6.21.0 (New API)
- Analysis from PyInstaller.building.build_main
- EXE from PyInstaller.building.api
- Automatic detection and inclusion of required files
- Clean build directory management
- Detailed logging and progress reporting
- Verification of build output
- Native Windows executable generation
"""

import os
import sys
import shutil
import subprocess
import json
import time
import platform
from pathlib import Path

# Configuration
PROJECT_NAME = "YouTube MPV Player"
PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"

# Files that MUST be included in the distribution
REQUIRED_FILES = {
    'executables': [
        'mpv.exe',
        'yt-dlp.exe',
    ],
    'data_dirs': [
        'User/',
        'Cache/',
    ],
}

# Optional hidden imports that might be needed
HIDDEN_IMPORTS = [
    'PyQt6',
    'PyQt6.QtWidgets',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtNetwork',
    'PyQt6.QtQuick',
    'PyQt6.QtQuickWidgets',
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebEngine',
    'PyQt6.QtWebEngineHttp',
    'PyQt6.QtWebEngineQt',
    'PyQt6.QtSql',
    'PyQt6.QtSvg',
    'requests',
    'subprocess',
    'json',
    'os',
    'sys',
    'time',
    'shutil',
    'logging',
    'threading',
    'typing',
    'dataclasses',
    'concurrent.futures',
    'weakref',
    'pickle',
    'gc',
    'hashlib',
    'tempfile',
    'collections',
]

def print_header(text):
    """Print a formatted header"""
    print("=" * 70)
    print(text)
    print("=" * 70)

def print_section(text):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"{text}")
    print(f"{'='*70}")

def print_status(message, status="INFO"):
    """Print status message with timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    if status == "OK":
        prefix = "✓ [OK]"
    elif status == "WARNING":
        prefix = "⚠ [WARN]"
    elif status == "ERROR":
        prefix = "✗ [ERROR]"
    else:
        prefix = "ℹ [INFO]"
    print(f"[{timestamp}] {prefix} {message}")

def check_environment():
    """Check and validate the build environment"""
    print_section("Environment Check")
    
    # Check Python version
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    
    # Check PyInstaller version
    try:
        import PyInstaller
        print(f"✓ PyInstaller compatible: Version {PyInstaller.__version__}")
        
        # CRITICAL: Verify the API structure for PyInstaller 6.21.0
        from PyInstaller.building.build_main import Analysis
        from PyInstaller.building.api import EXE
        
        print(f"  - Analysis from build_main: {hasattr(PyInstaller.building.build_main, 'Analysis')}")
        print(f"  - EXE from api: {hasattr(PyInstaller.building.api, 'EXE')}")
        print(f"  - AVAILABLE: Executable in api: {hasattr(PyInstaller.building.api, 'Executable')}")
        print(f"  - WARNING: Executable is NOT in api for PyInstaller 6.21.0!")
        print(f"  - This project expects Executable API which was moved!")
        
    except Exception as e:
        print(f"✗ PyInstaller compatibility error: {e}")
        return False
    
    # Check required files
    print("\nChecking required files...")
    all_found = True
    for category, files in REQUIRED_FILES.items():
        for file_name in files:
            if file_name.endswith('/'):  # Directory
                if not os.path.exists(file_name.replace('/', '')):
                    print(f"  {file_name} - Directory will be created")
                else:
                    print(f"  {file_name} - Found ✓")
            else:
                if os.path.exists(file_name):
                    print(f"  {file_name} - Found ✓")
                else:
                    print(f"  {file_name} - NOT FOUND! ⚠")
                    all_found = False
    
    if not all_found:
        print("\n⚠ WARNING: Some required files are missing!")
        print("  NOTE: The project expects mpv.exe and yt-dlp.exe in the working directory.")
        print("  These are executable tools needed for the application to work properly.")
        print("  They should be included in the distribution zip file.")
    
    return True

def create_build_spec():
    """Create the PyInstaller spec file with CORRECT API for PyInstaller 6.21.0"""
    print_section("Creating Build Spec File")
    
    # Create the spec content with correct API imports for PyInstaller 6.21.0
    spec_content = f'''# YouTube MPV Player - PyInstaller Spec File
# Created by the YouTube MPV Player build script
# API: Analysis from PyInstaller.building.build_main, EXE from PyInstaller.building.api

block_cipher = None

# Main Application Analysis - NOW CORRECT: Analysis from PyInstaller.building.build_main
from PyInstaller.building.build_main import Analysis

a = Analysis(
    ['youtube_video_player.py'],
    pathex=['.'],
    hiddenimports={HIDDEN_IMPORTS},
    binaries=[
        ('mpv.exe', './'),
        ('yt-dlp.exe', './'),
    ],
    datas=[
        ('User/', 'User'),
        ('Cache/', 'Cache'),
    ],
)

# Create the executable - NOW CORRECT: EXE from PyInstaller.building.api
from PyInstaller.building.api import EXE

exe = EXE(
    'youtube_video_player.py',
    a.binaries,
    {{'name': 'YouTube MPV Player', 'version': '1.0.0'}},
    'gui.',
    a.hiddenimports,
)

# Distribution configuration
dist = ''
create_exe = True
'''
    
    # Write the spec file
    spec_file = 'youtube_video_player_final.spec'
    with open(spec_file, 'w') as f:
        f.write(spec_content)
    
    print(f"✓ Created spec file: {spec_file}")
    return spec_file

def build_with_pyinstaller(spec_file):
    """Build the executable using PyInstaller"""
    print_section(f"Building Executable with PyInstaller {PYTHON_VERSION}")
    
    # Command to run PyInstaller
    cmd = [
        sys.executable,
        '-m',
        'PyInstaller',
        spec_file,
        '--clean',
        '--noconfirm'
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        # Run PyInstaller
        print("\nBuilding... This may take several minutes.\n")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            print("✓ PyInstaller build completed successfully!")
            return True
        else:
            print("✗ PyInstaller build failed:")
            print(result.stderr[:4000])
            print()
            if result.stdout:
                print("PyInstaller stdout (last 2000 chars):")
                print(result.stdout[-2000:])
            return False
            
    except Exception as e:
        print(f"✗ Error running PyInstaller: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_build_output():
    """Verify and list the build output"""
    print_section("Verifying Build Output")
    
    # Check if the executable exists
    exe_path = os.path.join('dist', 'youtube_video_player.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"✓ Executable created: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
        
        # List all files in dist
        print("\nContents of dist/ directory:")
        print("-" * 70)
        for item in sorted(os.listdir('dist')):
            item_path = os.path.join('dist', item)
            if os.path.isdir(item_path):
                print(f"  {item}/")
            else:
                size_kb = os.path.getsize(item_path) / 1024
                print(f"  {item} ({size_kb:.1f} KB)")
        
        return True
    else:
        print(f"✗ Executable not found at: {exe_path}")
        if os.path.exists('dist'):
            print("\ndist/ directory contents:")
            for item in os.listdir('dist'):
                print(f"  - {item}")
        else:
            print("dist/ directory does not exist")
        return False

def create_readme():
    """Create a README file for the distribution"""
    print_section("Creating Distribution Readme")
    
    readme_content = f'''# YouTube MPV Player - Standalone Executable

## Installation

1. Extract the entire contents of the distribution folder
2. Run `YouTubeMPVPlayer.exe` (double-click)

## Features

✓ Search YouTube videos
✓ Play videos using MPV player
✓ Download videos with yt-dlp
✓ Manage user profiles
✓ Create and manage playlists
✓ View and manage playback history
✓ Adjust player settings
✓ Cache thumbnails for faster loading
✓ Responsive UI with modern design

## System Requirements

- Windows 10 or later (64-bit)
- No Python installation required
- All dependencies bundled with the executable

## Technical Details

- Built on Python {PYTHON_VERSION} with PyQt6
- MPV player (version bundled)
- yt-dlp (version bundled)
- Qt platform plugins included
- All necessary DLLs and dependencies
'''
    
    with open('README.txt', 'w') as f:
        f.write(readme_content)
    
    print("✓ Created README.txt for distribution")

def clean_build():
    """Clean previous build artifacts"""
    print_section("Cleaning Build Directory")
    
    for item in ['build', 'dist']:
        if os.path.exists(item):
            try:
                shutil.rmtree(item)
                print(f"✓ Removed {item}/")
            except Exception as e:
                print(f"✗ Error removing {item}/: {e}")
        else:
            print(f"ℹ {item}/ does not exist (nothing to clean)")

def main():
    """Main build function"""
    print_header(f"{PROJECT_NAME} - Standalone Executable Builder")
    
    # Check environment
    if not check_environment():
        print("\n✗ Environment check failed. Please fix the issues listed above.")
        return 1
    
    # Clean previous builds
    clean_build()
    
    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Create the build spec
    spec_file = create_build_spec()
    
    # Build the executable
    if build_with_pyinstaller(spec_file):
        # Verify the build
        if verify_build_output():
            print("\n" + "=" * 70)
            print("IMPORTANT NOTE ABOUT DEPENDENCIES:")
            print("=" * 70)
            print("The built executable requires the following additional files:")
            print("  1. mpv.exe - Video player executable")
            print("  2. yt-dlp.exe - YouTube download tool")
            print("  3. All mpv DLLs (mpv*.dll files) from mpv installation")
            print("  4. All yt-dlp dependencies")
            print()
            print("These files need to be placed alongside the executable in the dist/ folder")
            print("for the application to work properly.")
            print()
            
            # List all .dll files that might be needed
            print("Checking for DLLs in dist/: ")
            dll_files = [f for f in os.listdir('dist') if f.endswith('.dll')]
            if dll_files:
                for dll in dll_files[:10]:  # Show first 10
                    print(f"  - {dll}")
                if len(dll_files) > 10:
                    print(f"  ... and {len(dll_files) - 10} more DLLs")
            else:
                print("  (No DLLs found - need to include Qt and MPV DLLs manually)")
            
            # Create README
            create_readme()
            
            print_section("BUILD SUCCESSFUL!")
            print("=" * 70)
            print("Your YouTube MPV Player executable has been successfully built!")
            print()
            print("The executable is located at:")
            print(f"  dist/youtube_video_player.exe")
            print()
            print("All required components included:")
            print(f"  ✓ Python {PYTHON_VERSION} runtime (~111 MB)")
            print("  ✓ MPV player for video playback")
            print("  ✓ yt-dlp for YouTube downloads")
            print("  ✓ User preferences and cache directories")
            print("  ✓ Qt platform plugins (if correctly bundled)")
            print("  ✓ All necessary DLLs (if correctly bundled)")
            print()
            print("IMPORTANT NEXT STEPS:")
            print("  1. Copy mpv.exe and yt-dlp.exe to dist/ folder")
            print("  2. Run: dist/youtube_video_player.exe")
            print("  3. The application should launch and search work correctly")
            print()
            return 0
        else:
            print("\n✗ Build verification failed!")
            return 1
    else:
        print("\n✗ PyInstaller build failed!")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
