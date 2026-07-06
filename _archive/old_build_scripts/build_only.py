#!/usr/bin/env python3
"""YouTube MPV Player - Complete executable build"""

import os
import sys
import shutil
import subprocess
import tempfile

# Set working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def print_header(message):
    print("=" * 60)
    print(message)
    print("=" * 60)

def clean_build():
    """Clean previous builds"""
    for item in ['build', 'dist']:
        if os.path.exists(item):
            shutil.rmtree(item)
            print(f"[OK] Removed {item}/")

def create_simple_build():
    """Create a simple build using pyinstaller directly"""
    print("Building executable with PyInstaller...")
    
    # Create temporary spec file
    spec_content = """block_cipher = None

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
        ('mpv.exe', '.'),
        ('yt-dlp.exe', '.'),
    ],
    datas=[
        ('User/', 'User'),
        ('Cache/', 'Cache'),
        ('pyproject.toml', '.'),
        ('requirements.txt', '.'),
        ('README.md', '.'),
        ('LICENSE', '.'),
    ],
    scripts=[],
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
    
    with open('youtube_video_player_clean.spec', 'w') as f:
        f.write(spec_content)
    
    # Run PyInstaller with the spec file
    cmd = [sys.executable, '-m', 'PyInstaller', 'youtube_video_player_clean.spec']
    
try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[OK] PyInstaller build completed successfully")
            return True
        else:
            print("[X] PyInstaller failed:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"[X] Error running PyInstaller: {e}")
        return False
    except Exception as e:
        print(f"✗ Error running PyInstaller: {e}")
        return False

def main():
    """Main build process"""
    print_header("YouTube MPV Player - Executable Builder")
    
    clean_build()
    
    if create_simple_build():
        print_header("Build completed successfully!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"[OK] Executable created: {exe_path}")
            print(f"[OK] Size: {size_mb:.1f} MB")
            return True
        else:
            print("[X] Executable not found in dist/ folder")
            # List contents of dist/
            if os.path.exists('dist'):
                print("\nContents of dist/: ")
                for item in os.listdir('dist'):
                    print("  - %s" % item)
            return False
    else:
        print_header("Build failed!")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
