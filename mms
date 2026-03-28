#!/opt/homebrew/bin/python3
"""MMS — Multi-Model Switch 入口"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mms_core import main

if __name__ == "__main__":
    main()
