#!/usr/bin/env python3
"""YouTube MPV Player - Final executable build"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Final Executable Builder")
print("=" * 60)

# Clean previous builds
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create a properly working spec file
spec_content = '''block_cipher = None

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
)

dist = ''
create_exe = True
'''

# Create the spec file
spec_file = 'youtube_video_player.spec'
with open(spec_file, 'w') as f:
    f.write(spec_content)
print(f"[OK] Created spec file: {spec_file}")

# Try building with minimal arguments first
cmd = [
    sys.executable,
    '-m',
    'PyInstaller',
    spec_file,
    '--clean'
]

print("\nBuilding executable...")
print(f"Command: {' '.join(cmd)}")

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[SUCCESS] Build completed!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[SUCCESS] Executable created: {exe_path}")
            print(f"[SIZE] Size: {size_mb:.1f} MB")
            
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
            print("\nUsage Instructions:")
            print("  1. Navigate to the dist/ directory")
            print("  2. Double-click 'youtube_video_player.exe' to launch")
            print("  3. Sign in with your YouTube account or choose a profile")
            print("  4. Search for videos or browse your playlists")
            print("  5. Use the media control panel to play/pause, seek, volume")
            sys.exit(0)
        else:
            print("\n[ERROR] Executable not found in dist/ folder")
            print("Check if a different executable name was created")
            # List all files in dist
            if os.path.exists('dist'):
                print(f"\nContents of dist/: ")
                for item in os.listdir('dist'):
                    print(f"  {item}")
            sys.exit(1)
    else:
        print("\n[ERROR] Build failed:")
        print(result.stderr)
        sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Error building: {e}")
    sys.exit(1)
