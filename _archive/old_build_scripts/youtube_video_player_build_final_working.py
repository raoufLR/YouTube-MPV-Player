#!/usr/bin/env python3
"""YouTube MPV Player - Final working executable build"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Final Executable Builder")
print("=" * 60)

# Clean build directories
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create a properly functioning PyInstaller spec file
spec_content = """from PyInstaller.building.api import Analysis
from PyInstaller.building.api import Executable

block_cipher = None

a = Analysis(
    ['youtube_video_player.py'],
    pathex=[],
    hiddenimports=[
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
    ],
    binaries=[
        ('mpv.exe', './'),
        ('yt-dlp.exe', './'),
    ],
    datas=[
        ('User/', 'User'),
        ('Cache/', 'Cache'),
        ('pyproject.toml', '.'),
        ('requirements.txt', '.'),
        ('README.md', '.'),
        ('LICENSE', '.'),
    ],
    scripts=[],
)

exe = Executable(
    'youtube_video_player.py',
    a.binaries,
    {'name': 'YouTube MPV Player', 'version': '1.0.0'},
    'gui.',
    a.hiddenimports,
    a.hookspath,
    a.hooksourcedir,
)

dist = ''
create_exe = True
"""

# Write the spec file
with open('youtube_video_player_final_working.spec', 'w') as f:
    f.write(spec_content)
print("[OK] Created final working spec file: youtube_video_player_final_working.spec")

# Backup the existing spec file if it exists
spec_file = 'youtube_video_player.spec'
if os.path.exists(spec_file):
    shutil.copy2(spec_file, f'{spec_file}.backup')
    print(f"[OK] Created backup: {spec_file}.backup")

# Create the new spec file
with open(spec_file, 'w') as f:
    f.write(spec_content)
print(f"[OK] Created new spec file: {spec_file}")

# Build the executable
cmd = [sys.executable, '-m', 'PyInstaller', spec_file, '--clean', '--noconfirm']

try:
    print("\nBuilding executable with PyInstaller...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[OK] Build successful!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[OK] Executable created successfully!")
            print(f"[OK] Location: {exe_path}")
            print(f"[OK] Size: {size_mb:.1f} MB")
            
            # List contents
            print("\nContents of dist/: ")
            for item in sorted(os.listdir('dist')):
                item_path = os.path.join('dist', item)
                if os.path.isdir(item_path):
                    print(f"  {item}/")
                else:
                    size_kb = os.path.getsize(item_path) / 1024
                    print(f"  {item} ({size_kb:.1f} KB)")
            
            print("\n" + "=" * 60)
            print("SUCCESS! YouTube MPV Player executable built successfully!")
            print("=" * 60)
            print("YouTube MPV Player.exe is now ready to use!")
            print("\nUsage:")
            print("  1. Navigate to the dist/ directory")
            print("  2. Double-click 'youtube_video_player.exe' to start")
            print("  3. Choose or create a profile")
            print("  4. Search for YouTube videos or use playlists")
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
