# Snippet Library menu + viewer -> Nuke bridge
import nuke

try:
    import snippetlib.nuke_io as _snippetlib

    _menu = nuke.menu("Nuke").addMenu("SnippetLibrary")
    _menu.addCommand("Save Selection to Library...", _snippetlib.save_selected_dialog)
    _menu.addCommand("Load from Library...", _snippetlib.show_browser)
    _menu.addSeparator()
    _menu.addCommand("Open Viewer", _snippetlib.open_viewer)
    _snippetlib.start_bridge()
except Exception as exc:
    nuke.tprint("SnippetLibrary: not loaded (%s)" % exc)
