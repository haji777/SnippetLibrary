# Snippet Library: shared by init.py and menu.py (both run via exec() in Nuke,
# where __file__ may be missing). Finds the repository next to this "nuke"
# folder through nuke.pluginPath() and puts it on sys.path.
import os
import sys

import nuke


def find_repo(report=False):
    checked = []
    candidates = []
    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    candidates.extend(nuke.pluginPath())
    for folder in candidates:
        folder = os.path.normpath(folder)
        # the repo is the parent of this "nuke" folder; also accept a zip
        # extracted one level too deep (SnippetLibrary-main/...)
        for repo in (os.path.dirname(folder), folder,
                     os.path.join(os.path.dirname(folder), "SnippetLibrary-main")):
            pkg = os.path.join(repo, "snippetlib")
            if pkg in checked:
                continue
            ok = os.path.isfile(os.path.join(pkg, "core.py"))
            checked.append(pkg)
            if ok:
                if repo not in sys.path:
                    sys.path.insert(0, repo)
                return repo
    if report:
        nuke.tprint("SnippetLibrary: 'snippetlib' package not found. Looked for core.py in:")
        for pkg in checked:
            nuke.tprint("    %s" % pkg)
        nuke.tprint("  -> the repository must look like <repo>/nuke/menu.py + <repo>/snippetlib/core.py")
    return None
