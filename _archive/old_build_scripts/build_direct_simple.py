#!/usr/bin/env python3
"""YouTube MPV Player - Simple direct build"""

import os
import sys
import shutil
import subprocess
import stat

print("=" * 60)
print("YouTube MPV Player - Simple Direct Executable Builder")
print("=" * 60)

# Clean build directories
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# Make all .exe files executable on Windows
def make_executable(path):
    if path.endswith('.exe'):
        try:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IEXEC)
        except Exception as e:
            print(f"[!] Warning: Could not make {path} executable: {e}")

# Copy all .exe files to current directory
mpv_exe = 'mpv.exe'
yt_dlp_exe = 'yt-dlp.exe'

for exe in [mpv_exe, yt_dlp_exe]:
    if os.path.exists(exe):
        dst = os.path.join('.', exe)
        if exe != dst:
            shutil.copy2(exe, dst)
            make_executable(dst)
            print(f"[OK] Copied {exe} to current directory")

print("[OK] Prepared all required .exe files")

# Build the executable using PyInstaller command line
# Use a minimal approach with only essential dependencies
cmd = [
    sys.executable,
    '-m',
    'PyInstaller',
    'youtube_video_player.py',
    '--onefile',
    '--windowed',
    '--clean',
    '--noconfirm',
    '--hidden-import=PyQt6',
    '--hidden-import=PyQt6.QtWidgets',
    '--hidden-import=PyQt6.QtCore',
    '--hidden-import=PyQt6.QtGui',
    '--hidden-import=PyQt6.QtNetwork',
    '--hidden-import=PyQt6.QtQuick',
    '--hidden-import=PyQt6.QtQuickWidgets',
    '--hidden-import=requests',
    '--hidden-import=subprocess',
    '--hidden-import=json',
    '--hidden-import=time',
    '--hidden-import=shutil',
    '--hidden-import=logging',
    '--hidden-import=threading',
    '--hidden-import=typing',
    '--hidden-import=dataclasses',
    '--hidden-import=subprocess',
    '--hidden-import=hashlib',
    '--hidden-import=tempfile',
    '--hidden-import=collections',
    '--hidden-import=concurrent.futures',
    '--hidden-import=weakref',
    '--hidden-import=pickle',
    '--hidden-import=gc',
    '--add-data=mpv.exe;.',
    '--add-data=yt-dlp.exe;.',
    '--add-data=User;User',
    '--add-data=Cache;Cache',
    '--add-data=__pycache__;__pycache__',
]

# Determine the proper runtime hook for PyQt6
try:
    import site
    site_packages = site.getsitepackages()
    if site_packages:
        pyqt6_path = os.path.join(site_packages[0], 'PyQt6', 'Qt6', 'bin')
        if os.path.exists(pyqt6_path):
            # Add Qt DLL search directories
            cmd.extend(['--runtime-hook', f'--additional-dependency={pyqt6_path}'])
            print(f"[OK] Found Qt6 DLL path: {pyqt6_path}")
except Exception as e:
    print(f"[!] Warning: Could not check Qt6 path: {e}")

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n[OK] PyInstaller build successful!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[OK] Executable created: {exe_path}")
            print(f"[OK] Size: {size_mb:.1f} MB")
            
            # List dist contents
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
            sys.exit(0)
        else:
            print("\n[X] Executable not found in dist/ folder")
            sys.exit(1)
    else:
        print("\n[X] PyInstaller failed:")
        print(result.stderr[:3000])
        sys.exit(1)
except Exception as e:
    print(f"\n[X] Error: {e}")
    sys.exit(1)
