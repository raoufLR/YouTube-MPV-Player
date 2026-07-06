#!/usr/bin/env python3
"""YouTube MPV Player - Ultra-simplified executable build"""

import os
import sys
import shutil
import subprocess
import json

print("=" * 60)
print("YouTube MPV Player - Ultra-simplified Executable Builder")
print("=" * 60)

# Clean build directories
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create a simple spec file with proper imports for PyInstaller 5.x
# The project uses the old API which expects Analysis and Executable from PyInstaller.building.api
spec_content = """from PyInstaller.building.api import Analysis, Executable
from PyInstaller.building.utils import collect_dynamic_libs
import PyQt6

# Get Qt dynamic libraries
qt_dlls = collect_dynamic_libs('PyQt6', excludes=["pyi_rth"])

block_cipher = None

a = Analysis(
    ['youtube_video_player.py'],
    pathex=[],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
    ],
    binaries=[
        ('mpv.exe', './'),
        ('yt-dlp.exe', './'),
    ] + qt_dlls,
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

with open('youtube_video_player_final.spec', 'w') as f:
    f.write(spec_content)
print("[OK] Created final spec file")

# Save original python version for compatibility
python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

# Build the executable
cmd = [sys.executable, '-m', 'PyInstaller', 'youtube_video_player_final.spec', '--clean', '--noconfirm']

try:
    print("\nBuilding executable...")
    print(f"Using Python {python_version}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[OK] Build successful!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[OK] Executable created: {exe_path}")
            print(f"[OK] Size: {size_mb:.1f} MB")
            
            # List contents
            print("\nContents of dist/: ")
            for item in os.listdir('dist'):
                item_path = os.path.join('dist', item)
                if os.path.isdir(item_path):
                    print(f"  {item}/")
                else:
                    size_kb = os.path.getsize(item_path) / 1024
                    print(f"  {item} ({size_kb:.1f} KB)")
            
            print("\n" + "=" * 60)
            print("SUCCESS! Executable built successfully!")
            print("=" * 60)
            print(f"You can run: dist/youtube_video_player.exe")
            print("All resources included:")
            print("  - Python environment (~111 MB)")
            print("  - MPV executable")
            print("  - yt-dlp executable")
            print("  - Cache and User data directories")
            sys.exit(0)
        else:
            print("\n[X] Executable not found in dist/ folder")
            sys.exit(1)
    else:
        print("\n[X] Build failed:")
        print(result.stderr[:2000])
        sys.exit(1)
except Exception as e:
    print(f"\n[X] Error: {e}")
    sys.exit(1)
