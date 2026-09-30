# Snippet Library: make the "snippetlib" package importable inside Nuke.
#
# Install: in ~/.nuke/init.py add
#     nuke.pluginAddPath("C:/path/to/SnippetLibrary/nuke")
#
# Nuke runs this file with exec(), so __file__ may not exist here: the repo is
# located through nuke.pluginPath() instead (this folder is on it).
import os
import sys

import nuke


def _snippetlib_setup():
    candidates = []
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    candidates.extend(nuke.pluginPath())
    for folder in candidates:
        repo = os.path.dirname(os.path.normpath(folder))
        if os.path.isfile(os.path.join(repo, "snippetlib", "__init__.py")):
            if repo not in sys.path:
                sys.path.append(repo)
            return repo
    return None


if _snippetlib_setup() is None:
    nuke.tprint("SnippetLibrary: repository not found next to any plugin path: %s"
                % ", ".join(nuke.pluginPath()))
