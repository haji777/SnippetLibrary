# Snippet Library: make the "snippetlib" package importable inside Nuke.
#
# Install: in ~/.nuke/init.py add
#     nuke.pluginAddPath("C:/path/to/SnippetLibrary/nuke")
#
# Nuke runs this file with exec(), so __file__ may not exist here; the repo is
# located through nuke.pluginPath() (see _bootstrap.py, loaded the same way).
import os

import nuke

for _folder in nuke.pluginPath():
    _boot = os.path.join(_folder, "_bootstrap.py")
    if os.path.isfile(_boot):
        _ns = {"__file__": _boot}
        with open(_boot, "r", encoding="utf-8") as _f:
            exec(compile(_f.read(), _boot, "exec"), _ns)
        _ns["find_repo"](report=True)
        break
else:
    nuke.tprint("SnippetLibrary: _bootstrap.py not found on the plugin path")
