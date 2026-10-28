"""Resolve the writable application data root.

A packaged build must keep ``User/``, ``Cache/`` and ``Logs/`` beside the
executable.  Shortcuts and Explorer launches can start the process with a
working directory that is not writable (``C:\\Windows\\System32``), which
used to crash startup while creating the log directory.

Running from source keeps the historical working-directory behaviour so
tests and developer tools stay isolated.
"""

from __future__ import annotations

import os
import sys


def data_root() -> str:
    """Return the directory that holds ``User/``, ``Cache/`` and ``Logs/``."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.getcwd()
