#!/usr/bin/env python3
"""YouTube MPV Player - Simple executable build"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Simple Executable Builder")
print("=" * 60)

# Create a basic, working PyInstaller spec file
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
        'requests',
        'subprocess',
        'json',
        'os',
        'sys',
        'time',
        'shutil',
        'logging',
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
spec_file = 'youtube_video_player_simple.spec'
with open(spec_file, 'w') as f:
    f.write(spec_content)
print(f"[OK] Created spec file: {spec_file}")

# Try using PyInstaller command line approach
cmd = [
    'pyinstaller',  # Try command line PyInstaller
    spec_file,
    '--clean',
    '--noconfirm'
]

print("\nTrying PyInstaller command line approach...")

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[OK] Build successful with command line!")
        
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
            sys.exit(0)
        else:
            print("\n[X] Executable not found in dist/ folder")
            sys.exit(1)
    else:
        print("\n[X] Build failed with command line PyInstaller:")
        print(result.stderr[:2000])
        
        # Fallback to trying python -m approach
        print("\nTrying python -m PyInstaller approach...")
        cmd2 = [
            sys.executable,
            '-m',
            'PyInstaller',
            spec_file,
            '--clean',
            '--noconfirm'
        ]
        
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        
        if result2.returncode == 0:
            print("\n[OK] Build successful with python -m approach!")
            
            exe_path = os.path.join('dist', 'youtube_video_player.exe')
            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"\n[SUCCESS] Executable created: {exe_path}")
                print(f"[SIZE] Size: {size_mb:.1f} MB")
                
                print("\n" + "=" * 60)
                print("SUCCESS! YouTube MPV Player executable built successfully!")
                print("=" * 60)
                print(f"YouTube MPV Player.exe is now available at: dist/youtube_video_player.exe")
                sys.exit(0)
            else:
                print("\n[X] Executable not found")
                sys.exit(1)
        else:
            print("\n[X] Build failed with both approaches:")
            print(result2.stderr)
            sys.exit(1)
except Exception as e:
    print(f"\n[X] Error: {e}")
    sys.exit(1)
