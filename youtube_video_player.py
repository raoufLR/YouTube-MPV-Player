#!/usr/bin/env python3
"""YouTube MPV Player - Main entry point for the application"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main

if __name__ == "__main__":
    main()