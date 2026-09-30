# Snippet Library menu + viewer -> Nuke bridge
import os

import nuke


def _ensure_importable():
    """init.py normally does this; repeat it here in case that did not run
    (e.g. pluginAddPath() was called from menu.py instead of init.py)."""
    try:
        import snippetlib.core  # noqa: F401
        return True
    except ImportError:
        pass
    for folder in nuke.pluginPath():
        boot = os.path.join(folder, "_bootstrap.py")
        if os.path.isfile(boot):
            ns = {"__file__": boot}
            with open(boot, "r", encoding="utf-8") as f:
                exec(compile(f.read(), boot, "exec"), ns)
            return ns["find_repo"](report=True) is not None
    nuke.tprint("SnippetLibrary: _bootstrap.py not found on the plugin path: %s"
                % ", ".join(nuke.pluginPath()))
    return False


try:
    if _ensure_importable():
        import snippetlib.nuke_io as _snippetlib

        _menu = nuke.menu("Nuke").addMenu("SnippetLibrary")
        _menu.addCommand("Save Selection to Library...", _snippetlib.save_selected_dialog)
        _menu.addCommand("Load from Library...", _snippetlib.show_browser)
        _menu.addSeparator()
        _menu.addCommand("Open Viewer", _snippetlib.open_viewer)
        _snippetlib.start_bridge()
    else:
        nuke.tprint("SnippetLibrary: not loaded (see the paths above)")
except Exception as exc:
    import traceback
    nuke.tprint("SnippetLibrary: not loaded (%s)" % exc)
    nuke.tprint(traceback.format_exc())
    nuke.tprint("SnippetLibrary: plugin paths = %s" % ", ".join(nuke.pluginPath()))
