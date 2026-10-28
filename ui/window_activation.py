"""Bring the window of an already running copy to the foreground.

Windows lets a freshly launched process take the foreground once, so the
second instance of the app uses that right to raise the existing window and
then exits.  Window lookup goes through the lock file's owner PID, which keeps
the behaviour correct even when the window title (profile name) changes.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

_SW_RESTORE = 9


def _windows_for_pid(pid: int) -> list[int]:
    if os.name != "nt":
        return []

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    handles: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if (
            owner.value == pid
            and user32.IsWindowVisible(hwnd)
            and user32.GetWindowTextLengthW(hwnd) > 0
        ):
            handles.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return handles


def focus_existing_instance(pid: int) -> bool:
    """Raise the main window of *pid*; return ``False`` when none was found."""
    if os.name != "nt" or pid <= 0:
        return False

    handles = _windows_for_pid(pid)
    if not handles:
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = handles[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)

    if user32.GetForegroundWindow() != hwnd:
        # Join the foreground thread's input queue for one call; shells often
        # deny SetForegroundWindow across processes without it.
        foreground = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        if (
            foreground_thread
            and target_thread
            and foreground_thread != target_thread
        ):
            user32.AttachThreadInput(foreground_thread, target_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(foreground_thread, target_thread, False)

    if user32.GetForegroundWindow() != hwnd:
        # Last resort: flash the taskbar button so the user notices it.
        user32.FlashWindow(hwnd, True)
    return True
