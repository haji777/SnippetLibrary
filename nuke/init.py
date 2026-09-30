# Snippet Library: add this folder to NUKE_PATH (or nuke.pluginAddPath() it from ~/.nuke/init.py)
import os
import sys

_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo not in sys.path:
    sys.path.append(_repo)
