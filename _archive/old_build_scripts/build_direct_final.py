#!/usr/bin/env python3
"""YouTube MPV Player - Direct PyInstaller executable build"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Direct Executable Builder")
print("=" * 60)

# Clean previous builds
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create a working spec file for PyInstaller
spec_content = """block_cipher = None

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
spec_file = 'youtube_video_player_direct.spec'
with open(spec_file, 'w') as f:
    f.write(spec_content)
print(f"[OK] Created spec file: {spec_file}")

# Try to build using PyInstaller command directly
cmd = [
    'C:\Python314\python.exe',
    '-m',
    'PyInstaller',
    spec_file,
    '--clean',
    '--noconfirm'
]

print("\nBuilding executable...")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("\n[OK] Build successful!")
    
    exe_path = os.path.join('dist', 'youtube_video_player.exe')
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n[OK] Executable created: {exe_path}")
        print(f"[OK] Size: {size_mb:.1f} MB")
        
        # List dist contents
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
        print(f"YouTube MPV Player.exe is now available at: dist/youtube_video_player.exe")
        sys.exit(0)
    else:
        print("\n[X] Executable not found in dist/ folder")
        sys.exit(1)
else:
    print("\n[X] Build failed:")
    print(result.stderr[:3000])
    sys.exit(1)
