#!/usr/bin/env python3
"""YouTube MPV Player - Clean executable build"""

import os
import sys
import shutil
import subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def print_header(message):
    print("=" * 60)
    print(message)
    print("=" * 60)

def clean_build():
    for item in ['build', 'dist']:
        if os.path.exists(item):
            shutil.rmtree(item)
            print("[OK] Removed %s/" % item)

def create_pyqt6_runtime_hook():
    """Create runtime hook to fix PyQt6 path issues"""
    hook_content = """import os
import sys
import PyQt6.QtCore

def _fix_qt_paths():
    # Get the path to this hook's directory
    hook_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Fix Qt plugin paths
    qt_bin_dir = os.path.join(hook_dir, '..', 'PyQt6', 'Qt6', 'bin')
    if os.path.exists(qt_bin_dir):
        os.environ['QT_PLUGIN_PATH'] = qt_bin_dir
        os.environ['PATH'] = qt_bin_dir + ';' + os.environ.get('PATH', '')
    
    # Find Qt6 DLLs and add them to PATH
    qt6_bin = os.path.join(sys._MEIPASS, 'PyQt6', 'Qt6', 'bin')
    if os.path.exists(qt6_bin):
        os.environ['PATH'] = qt6_bin + ';' + os.environ.get('PATH', '')
        
    # Fix application path for Qt
    app_path = os.path.join(sys._MEIPASS, 'YouTube MPV Player')
    if os.path.exists(app_path) and app_path not in sys.path:
        sys.path.insert(0, app_path)

try:
    _fix_qt_paths()
except Exception as e:
    # Silent fail - better than crashing
    pass
"""
    
    hook_dir = os.path.join('PyInstaller', 'hooks', 'rthooks')
    os.makedirs(hook_dir, exist_ok=True)
    
    with open(os.path.join(hook_dir, 'pyi_rth_pyqt6_path_fix.py'), 'w') as f:
        f.write(hook_content)
    
    print("[OK] Created PyInstaller runtime hook for Qt path fixing")

def create_libs_directory():
    """Create libs directory for Qt binaries"""
    libs_dir = os.path.join('libs')
    os.makedirs(libs_dir, exist_ok=True)
    
    # Check if Qt6 directory exists in Python packages
    qt6_bin_dir = os.path.join(sys.prefix, 'Lib', 'site-packages', 'PyQt6', 'Qt6', 'bin')
    if os.path.exists(qt6_bin_dir):
        # Copy Qt6 DLLs to libs
        for dll in os.listdir(qt6_bin_dir):
            if dll.endswith('.dll'):
                src = os.path.join(qt6_bin_dir, dll)
                dst = os.path.join(libs_dir, dll)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
        print(f"[OK] Created {libs_dir}/ directory with Qt6 DLLs")
    else:
        print("[!] Qt6 directory not found: %s" % qt6_bin_dir)

def build_executable():
    """Build the executable using PyInstaller with path fixes"""
    print("[OK] Building executable with PyInstaller...")
    
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
        '--hidden-import=PyQt6.QtWebEngineWidgets',
        '--hidden-import=PyQt6.QtWebEngineCore',
        '--hidden-import=requests',
        '--hidden-import=subprocess',
        '--hidden-import=json',
        '--hidden-import=time',
        '--hidden-import=shutil',
        '--hidden-import=logging',
        '--runtime-hook=PyInstaller/hooks/rthooks/pyi_rth_pyqt6_path_fix.py',
        '--add-data=libs;.',
        '--add-data=User;User',
        '--add-data=Cache;Cache',
        '--add-data=mpv.exe;.',
        '--add-data=yt-dlp.exe;.',
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[OK] PyInstaller build completed successfully")
            return True
        else:
            print("[X] PyInstaller failed:")
            print(result.stderr[:2000])
            return False
    except Exception as e:
        print(f"[X] Error running PyInstaller: {e}")
        return False

def main():
    print_header("YouTube MPV Player - Clean Executable Builder")
    
    clean_build()
    create_pyqt6_runtime_hook()
    create_libs_directory()
    
    if build_executable():
        print_header("Build completed successfully!")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print("[OK] Executable created: %s" % exe_path)
            print("[OK] Size: %.1f MB" % size_mb)
            return True
        else:
            print("[X] Executable not found in dist/ folder")
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
