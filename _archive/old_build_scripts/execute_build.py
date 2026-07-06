#!/usr/bin/env python3
"""YouTube MPV Player - Working executable build"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Working Executable Builder")
print("=" * 60)

# Clean build directories
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create spec file without scripts parameter to avoid the error
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
    ],
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

with open('youtube_video_player_working.spec', 'w') as f:
    f.write(spec_content)
print("[OK] Created working spec file")

# Build the executable
cmd = [sys.executable, '-m', 'PyInstaller', 'youtube_video_player_working.spec', '--clean', '--noconfirm']

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
            print("\n" + "=" * 60)
            print("SUCCESS! Build completed!")
            print("=" * 60)
            print("You can now run: dist/youtube_video_player.exe")
            sys.exit(0)
        else:
            print("")
            sys.exit(1)
    else:
        print("\n[X] Build failed:")
        print(result.stderr)
        sys.exit(1)
except Exception as e:
    print(f"\n[X] Error: {e}")
    sys.exit(1)
