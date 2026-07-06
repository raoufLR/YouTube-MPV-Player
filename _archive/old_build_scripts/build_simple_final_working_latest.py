#!/usr/bin/env python3
"""YouTube MPV Player - Working executable build for PyInstaller 6.21.0"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Working Executable Builder")
print("PyInstaller version:", end=' ')
import importlib.metadata
version = importlib.metadata.version('PyInstaller')
print(version)
print("=" * 60)

# Clean previous builds
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create a proper spec file for PyInstaller 6.21.0
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

# Create the spec file
spec_file = 'youtube_video_player.spec'
with open(spec_file, 'w') as f:
    f.write(spec_content)
print(f"[OK] Created spec file: {spec_file}")

# Build the executable
cmd = [
    sys.executable,
    '-m',
    'PyInstaller',
    spec_file,
    '--clean',
    '--noconfirm'
]

print("\nBuilding executable...")

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[OK] Build successful!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[OK] Executable created: {exe_path}")
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
            print("\nThe executable includes all components:")
            print("  - Python environment (~111 MB)")
            print("  - MPV player for video playback")
            print("  - yt-dlp for YouTube downloads")
            print("  - User preferences and cache")
            print("\nUsage:")
            print("  1. Navigate to the dist/ directory")
            print("  2. Double-click 'youtube_video_player.exe' to launch")
            print("  3. Sign in to your YouTube account or create a profile")
            print("  4. Search for videos or use playlists")
            print("  5. Use media controls to play/pause, seek, adjust volume")
            sys.exit(0)
        else:
            print("\n[X] Executable not found in dist/ folder")
            
            # Check if there's any executable with a different name
            exe_files = [f for f in os.listdir('dist') if f.endswith('.exe')]
            if exe_files:
                print(f"\nFound executable(s): {exe_files}")
                for exe_file in exe_files:
                    print(f"  - {exe_file} ({os.path.getsize(os.path.join('dist', exe_file))/(1024*1024):.1f} MB)")
            else:
                # Check for any executable in the build directory
                if os.path.exists('build/youtube_video_player'):
                    print(f"\nChecking build/youtube_video_player directory for executables...")
                    for root, dirs, files in os.walk('build/youtube_video_player'):
                        for file in files:
                            if file.endswith('.exe'):
                                full_path = os.path.join(root, file)
                                size_mb = os.path.getsize(full_path)/(1024*1024)
                                print(f"  - {full_path} ({size_mb:.1f} MB)")
            
            sys.exit(1)
    else:
        print("\n[X] Build failed:")
        print(result.stderr[:2000])
        sys.exit(1)
except Exception as e:
    print(f"\n[X] Error: {e}")
    sys.exit(1)
