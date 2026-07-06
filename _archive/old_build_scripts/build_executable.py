#!/usr/bin/env python3
"""YouTube MPV Player - Single executable build script using PyInstaller"""

import PyInstaller.__main__
import os
import sys
import platform
from pathlib import Path

def run_pyinstaller():
    """Run PyInstaller to create executable"""
    
    # Prepare command line arguments
    spec_file = 'youtube_video_player.spec'
    
    # Check if spec file exists
    if not os.path.exists(spec_file):
        print(f"Error: {spec_file} not found!")
        return False
    
    # Common arguments
    args = [
        spec_file,
        '--clean',
        '--noconfirm',
        '--onefile',
        '--windowed'
    ]
    
    # Platform-specific adjustments
    if platform.system() == 'Windows':
        args.extend(['--clean', '--noconfirm'])
    
    print(f"Building executable with PyInstaller...")
    print(f"Arguments: {' '.join(args)}")
    
    try:
        PyInstaller.__main__.run(args)
        return True
    except Exception as e:
        print(f"Error during PyInstaller execution: {e}")
        return False

def main():
    """Main function"""
    print("=" * 60)
    print("YouTube MPV Player - Executable Builder")
    print("=" * 60)
    
    success = run_pyinstaller()
    
    print("\n" + "=" * 60)
    if success:
        print("Build completed successfully!")
        print("Executable location: dist/youtube_video_player.exe")
    else:
        print("Build failed. Please check the error messages above.")
    
    return success

if __name__ == '__main__':
    sys.exit(0 if main() else 1)