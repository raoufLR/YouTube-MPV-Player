#!/usr/bin/env python3
"""YouTube MPV Player - Simple executable build using PyInstaller directly"""

import os
import sys
import shutil
import subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def print_header(message):
    print("=" * 60)
    print(message)
    print("=" * 60)

def clean_build():
    for item in ['build', 'dist']:
        if os.path.exists(item):
            shutil.rmtree(item)
            print("[OK] Removed %s/" % item)

def create_simple_build():
    """Build executable using PyInstaller on the source file directly"""
    print("[OK] Building executable with PyInstaller...")
    
    cmd = [
        sys.executable,
        '-m',
        'PyInstaller',
        'youtube_video_player.py',
        '--onefile',
        '--windowed',
        '--clean',
        '--noconfirm',
        '--hidden-import=PyQt6',
        '--hidden-import=PyQt6.QtWidgets',
        '--hidden-import=PyQt6.QtCore',
        '--hidden-import=PyQt6.QtGui',
        '--hidden-import=PyQt6.QtNetwork',
        '--hidden-import=PyQt6.QtQuick',
        '--hidden-import=PyQt6.QtQuickWidgets',
        '--hidden-import=PyQt6.QtWebEngineWidgets',
        '--hidden-import=PyQt6.QtWebEngineCore',
        '--hidden-import=requests',
        '--hidden-import=subprocess',
        '--hidden-import=json',
        '--hidden-import=time',
        '--hidden-import=shutil',
        '--hidden-import=logging',
        '--add-data=mpv.exe:.',
        '--add-data=yt-dlp.exe:.',
        '--add-data=User:User',
        '--add-data=Cache:Cache',
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[OK] PyInstaller build completed successfully")
            return True
        else:
            print("[X] PyInstaller failed:")
            print(result.stderr[:2000])
            return False
    except Exception as e:
        print(f"[X] Error running PyInstaller: {e}")
        return False

def main():
    print_header("YouTube MPV Player - Executable Builder")
    
    clean_build()
    
    if create_simple_build():
        print_header("Build completed successfully!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print("[OK] Executable created: %s" % exe_path)
            print("[OK] Size: %.1f MB" % size_mb)
            return True
        else:
            print("[X] Executable not found in dist/ folder")
            if os.path.exists('dist'):
                print("\nContents of dist/: ")
                for item in os.listdir('dist'):
                    print("  - %s" % item)
            return False
    else:
        print_header("Build failed!")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
