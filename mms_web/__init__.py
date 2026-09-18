"""Additive local Web surface; importing this package never loads MMS config."""

from pathlib import Path
import sys

_LIB = Path(__file__).resolve().parent.parent / "lib"
if _LIB.is_dir():
    _lib = str(_LIB)
    if _lib not in sys.path:
        sys.path.insert(0, _lib)
