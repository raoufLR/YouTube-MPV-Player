#!/usr/bin/env python3
"""YouTube MPV Player - Simple executable build"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Simple Executable Builder")
print("=" * 60)

# Clean previous builds
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create a properly working spec file
spec_content = """import PyInstaller
from PyInstaller.building import api
from PyInstaller.building.build_main import Analysis

# Use PyInstaller API directly
block_cipher = None

a = api.Analysis(
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

exe = api.Executable(
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

# Try to build using PyInstaller command
cmd = [
    sys.executable,
    '-m',
    'PyInstaller',
    spec_file,
    '--clean',
    '--noconfirm'
]

print("\nBuilding executable...")
print("Command:", ' '.join(cmd))

# Check if we can import what we need
try:
    from PyInstaller.building.api import Analysis, Executable
    print("[OK] Successfully imported Analysis and Executable from PyInstaller.building.api")
except ImportError as e:
    print(f"[ERROR] Failed to import from PyInstaller.building.api: {e}")
    
    try:
        from PyInstaller.building.build_main import Analysis as A, Executable as E
        print("[OK] Successfully imported Analysis and Executable from PyInstaller.building.build_main")
        
        # Update the spec file with correct imports
        spec_content = spec_content.replace(
            'from PyInstaller.building import api\nfrom PyInstaller.building.build_main import Analysis',
            'from PyInstaller.building.build_main import Analysis, Executable\nimport PyInstaller'
        )
        
        # Replace a = api.Analysis with a = Analysis
        spec_content = spec_content.replace(
            'a = api.Analysis(',
            'a = Analysis('
        )
        
        # Replace exe = api.Executable with exe = Executable
        spec_content = spec_content.replace(
            'exe = api.Executable(',
            'exe = Executable('
        )
        
        with open(spec_file, 'w') as f:
            f.write(spec_content)
        print("[OK] Updated spec file with correct imports")
        
    except ImportError as e2:
        print(f"[ERROR] Failed to import from both locations: {e2}")
        print("This indicates PyInstaller 6.21.0 has a different API structure")
        print("Please install PyInstaller v2024+ or use a different build approach")
        sys.exit(1)

# Try the build again
cmd2 = [
    sys.executable,
    '-m',
    'PyInstaller',
    spec_file,
    '--clean',
    '--noconfirm'
]

try:
    result = subprocess.run(cmd2, capture_output=True, text=True)
    
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
            print("YouTube MPV Player.exe is now available at: dist/youtube_video_player.exe")
            print("\nUsage Instructions:")
            print("  1. Navigate to the dist/ directory")
            print("  2. Double-click 'youtube_video_player.exe' to launch")
            print("  3. Sign in with your YouTube account or choose a profile")
            print("  4. Search for videos or browse your playlists")
            print("  5. Use the media control panel to play/pause, seek, volume")
            sys.exit(0)
        else:
            print("\n[ERROR] Executable not found in dist/ folder")
            print("The build may have succeeded but created the executable elsewhere")
            print("Checking for any .exe files...")
            for root, dirs, files in os.walk("."):
                for file in files:
                    if file.endswith('.exe'):
                        full_path = os.path.join(root, file)
                        print(f"[FOUND] Potential executable: {full_path}")
            sys.exit(1)
    else:
        print("\n[ERROR] Build failed:")
        print(result.stderr)
        sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] Error building: {e}")
    sys.exit(1)
