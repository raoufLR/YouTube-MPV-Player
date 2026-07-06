#!/usr/bin/env python3
"""YouTube MPV Player - Final working executable build"""

import os
import sys
import shutil
import subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("YouTube MPV Player - Final Executable Builder")
print("=" * 60)

# Clean build directories
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create spec file without scripts parameter
spec_content = """from PyInstaller.building.api import Analysis, Executable

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
    ],
    binaries=[
        ('mpv.exe', './'),
        ('yt-dlp.exe', './'),
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

with open('youtube_video_player_final.spec', 'w') as f:
    f.write(spec_content)

print("[OK] Created final spec file")

# Build the executable
cmd = [
    sys.executable,
    '-m',
    'PyInstaller',
    'youtube_video_player_final.spec',
    '--clean',
    '--noconfirm'
]

try:
    print("\nBuilding executable...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[OK] Build successful!")
        
        # Check if executable was created
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"[OK] Executable size: {size:.1f} MB")
            print(f"[OK] Executable location: {exe_path}")
            
            # List contents of dist to verify files are included
            print("\nContents of dist/: ")
            for item in os.listdir('dist'):
                if os.path.isdir(os.path.join('dist', item)):
                    print(f"  {item}/")
                else:
                    size_kb = os.path.getsize(os.path.join('dist', item)) / 1024
                    print(f"  {item} ({size_kb:.1f} KB)")
            
            print("\n" + "=" * 60)
            print("SUCCESS! Build completed!")
            print("=" * 60)
            print("You can now run: dist/youtube_video_player.exe")
            sys.exit(0)
        else:
            print("[X] Executable not found")
            sys.exit(1)
    else:
        print("\n[X] Build failed:")
        print(result.stderr)
        sys.exit(1)
except Exception as e:
    print(f"\n[X] Error: {e}")
    sys.exit(1)
