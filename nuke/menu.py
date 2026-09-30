# Snippet Library menu + viewer -> Nuke bridge
import os
import sys

import nuke


def _ensure_importable():
    """init.py normally does this; repeat it here in case that did not run
    (e.g. pluginAddPath() was called from menu.py instead of init.py)."""
    try:
        import snippetlib  # noqa: F401
        return
    except ImportError:
        pass
    for folder in nuke.pluginPath():
        repo = os.path.dirname(os.path.normpath(folder))
        if os.path.isfile(os.path.join(repo, "snippetlib", "__init__.py")):
            if repo not in sys.path:
                sys.path.append(repo)
            return


try:
    _ensure_importable()
    import snippetlib.nuke_io as _snippetlib

    _menu = nuke.menu("Nuke").addMenu("SnippetLibrary")
    _menu.addCommand("Save Selection to Library...", _snippetlib.save_selected_dialog)
    _menu.addCommand("Load from Library...", _snippetlib.show_browser)
    _menu.addSeparator()
    _menu.addCommand("Open Viewer", _snippetlib.open_viewer)
    _snippetlib.start_bridge()
except Exception as exc:
    import traceback
    nuke.tprint("SnippetLibrary: not loaded (%s)" % exc)
    nuke.tprint(traceback.format_exc())
    nuke.tprint("SnippetLibrary: plugin paths = %s" % ", ".join(nuke.pluginPath()))
