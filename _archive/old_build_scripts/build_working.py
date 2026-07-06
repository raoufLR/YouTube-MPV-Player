#!/usr/bin/env python3
"""YouTube MPV Player - Simple working executable build"""

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

def create_working_spec():
    """Create a minimal spec file that focuses on core files"""
    spec_content = """block_cipher = None

a = Analysis(
    ['youtube_video_player.py'],
    pathex=[],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'requests',
        'subprocess',
        'json',
        'os',
        'sys',
        'time',
        'shutil',
        'logging',
        'typing',
    ],
    binaries=[
        ('mpv.exe', '.'),
        ('yt-dlp.exe', '.'),
    ],
    datas=[
        ('User/', 'User'),
        ('Cache/', 'Cache'),
    ],
)

exe = Executable(
    'youtube_video_player.py',
    a.binaries,
    {'name': 'YouTube MPV Player', 'version': '1.0.0'},
    'gui.',
    a.hiddenimports,
)

dist = ''
create_exe = True
"""
    
    with open('youtube_video_player_working.spec', 'w') as f:
        f.write(spec_content)
    
    print("[OK] Created spec file: youtube_video_player_working.spec")

def build_executable():
    """Build the executable using PyInstaller"""
    cmd = [sys.executable, '-m', 'PyInstaller', 'youtube_video_player_working.spec', '--clean', '--noconfirm']
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[OK] PyInstaller build completed successfully")
            return True
        else:
            print("[X] PyInstaller failed:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"[X] Error running PyInstaller: {e}")
        return False

def main():
    print_header("YouTube MPV Player - Executable Builder")
    
    clean_build()
    create_working_spec()
    
    if build_executable():
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
