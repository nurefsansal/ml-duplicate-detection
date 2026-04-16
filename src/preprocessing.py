"""
Backwards-compatibility shim.

The project now uses `src/preprocess.py` (as requested in the graduation project spec).
This file remains to avoid import breakage in older notebooks/scripts.
"""

from src.preprocess import DataCleaner  # noqa: F401