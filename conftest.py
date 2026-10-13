"""Pytest root conftest: make the repository root importable.

`main.py` and `mcp_server.py` live at the repository root, so tests import
them directly (`import mcp_server`). Inserting the root here keeps that
working regardless of pytest's rootdir/import-mode behaviour.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
