#!/usr/bin/env python3
"""YouTube MPV Player - Working executable build for PyInstaller 6.21.0"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Final Executable Builder")
print("PyInstaller version: 6.21.0")
print("=" * 60)

# Clean previous builds
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Create an ultra-simple spec file that PyInstaller 6.21.0 can understand
spec_content = """block_cipher = None

a = Analysis(
    ['youtube_video_player.py'],
    [],
    [],
    [],
    [],
    [],
    []
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
spec_file = 'youtube_video_player.spec'
with open(spec_file, 'w') as f:
    f.write(spec_content)
print(f"[OK] Created spec file: {spec_file}")

# Try building with PyInstaller using the command line
cmd = [
    'pyinstaller.exe',  # Try executable
    '--clean',
    spec_file,
    '--noconfirm'
]

print("\nTrying PyInstaller executable...")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("\n[OK] Build successful!")
else:
    print("\n[WARNING] pyinstaller.exe not found, trying python -m approach...")
    
    # Try python -m PyInstaller
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
        print("\n[OK] Build successful!")
    else:
        print("\n[ERROR] Build failed:")
        print(result2.stderr)
        sys.exit(1)

# Check if executable was created
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
    print("  3. Sign in with your YouTube account or create a profile")
    print("  4. Search for videos or use playlists")
    print("  5. Use media controls to play/pause, seek, adjust volume")
else:
    print("\n[X] Executable not found")
    print("The executable should be at: dist/youtube_video_player.exe")
    
    # Check if it has a different name
    exe_files = [f for f in os.listdir('dist') if f.endswith('.exe')]
    if exe_files:
        print(f"\nFound executable(s): {exe_files}")
    else:
        print(f"\nNo .exe files found in dist/ directory")
    
    sys.exit(1)
