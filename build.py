#!/usr/bin/env python3
"""YouTube MPV Player - Canonical executable build script

Builds a standalone Windows executable using PyInstaller.
Usage: python build.py
"""

import os
import sys
import shutil
import subprocess

print("=" * 60)
print("YouTube MPV Player - Build Script")
print("=" * 60)

# Change to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Clean previous build artifacts ──────────────────────────────────────
for item in ['build', 'dist']:
    if os.path.exists(item):
        shutil.rmtree(item)
        print(f"[OK] Removed {item}/")

# ── Verify required files exist ─────────────────────────────────────────
required = ['mpv.exe', 'yt-dlp.exe', 'youtube_video_player.spec']
for f in required:
    if os.path.exists(f):
        print(f"[OK] Found {f}")
    else:
        print(f"[WARN] {f} not found — build may fail")

# ── Build the executable ────────────────────────────────────────────────
spec_file = 'youtube_video_player.spec'
cmd = [sys.executable, '-m', 'PyInstaller', spec_file, '--clean', '--noconfirm']

print(f"\nBuilding with: {' '.join(cmd)}")
print("This may take several minutes...\n")

try:
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("\n[OK] PyInstaller build completed successfully!")

        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[OK] Executable: {exe_path}")
            print(f"[OK] Size: {size_mb:.1f} MB")
            print("\nContents of dist/:")
            for item in sorted(os.listdir('dist')):
                item_path = os.path.join('dist', item)
                if os.path.isdir(item_path):
                    print(f"  {item}/")
                else:
                    sz = os.path.getsize(item_path) / 1024
                    print(f"  {item} ({sz:.1f} KB)")

            print("\n" + "=" * 60)
            print("BUILD SUCCESSFUL!")
            print("=" * 60)
            print(f"Run: dist\\youtube_video_player.exe")
            sys.exit(0)
        else:
            print(f"\n[ERROR] Executable not found at {exe_path}")
            sys.exit(1)
    else:
        print("\n[ERROR] PyInstaller build failed:")
        stderr = result.stderr or ""
        print(stderr[:2000])
        sys.exit(1)

except Exception as e:
    print(f"\n[ERROR] {e}")
    sys.exit(1)
