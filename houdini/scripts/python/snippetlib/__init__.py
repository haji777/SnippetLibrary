# Shim: Houdini puts <HOUDINI_PATH>/scripts/python on sys.path. The real package
# lives in <repo>/snippetlib (shared with Nuke and the viewer), so redirect there.
import os

_real = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "..", "..", "..", "snippetlib"))
__path__ = [_real]
with open(os.path.join(_real, "__init__.py"), encoding="utf-8") as _f:
    exec(compile(_f.read(), os.path.join(_real, "__init__.py"), "exec"))
