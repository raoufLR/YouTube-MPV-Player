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

# Create a minimal, working spec file
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

# Write the spec file
with open('youtube_video_player_final_working.spec', 'w') as f:
    f.write(spec_content)
print("[OK] Created final working spec file")

# Build the executable
cmd = [sys.executable, '-m', 'PyInstaller', 'youtube_video_player_final_working.spec', '--clean', '--noconfirm']

try:
    print("\nBuilding executable...")
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
            print(f"You can now run: dist/youtube_video_player.exe")
            print("\nThe executable includes all necessary components:")
            print("  - Main application code")
            print("  - MPV player executable")
            print("  - yt-dlp downloader")
            print("  - User preferences and cache")
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
