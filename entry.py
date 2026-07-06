#!/usr/bin/env python3
"""YouTube MPV Player - Main executable entry point"""

import sys
import os

# Ensure the project directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the main application function
from main import main

if __name__ == "__main__":
    main()