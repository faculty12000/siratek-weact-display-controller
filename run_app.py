#!/usr/bin/env python
"""Entrypoint for the WeAct 0.96" display controller app."""

import os
import sys

# Guarantee the repo root is on sys.path regardless of the directory this is
# launched from, so `import library...` / `import app...` always resolve.
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.gui import main

if __name__ == "__main__":
    main()
