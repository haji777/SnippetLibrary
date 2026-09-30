# -*- coding: utf-8 -*-
"""Register an existing payload (.json from hou.data / .nk) without opening the DCC.

    py -3 tools/register.py FILE --title "..." [--name ascii_name] [--context cop] [--desc "..."]
                                 [--tags a,b] [--app-version 22.0.429] [--user name]

The app is taken from the extension (.json = houdini, .nk = nuke). The network
for the viewer is rebuilt from the payload alone, so type labels / node colors
that only the live application knows are missing.
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snippetlib import core, graph  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--title", help="display title (any language)")
    ap.add_argument("--name", help="ASCII file-name part (default: derived from the title / file)")
    ap.add_argument("--context", default=None)
    ap.add_argument("--desc", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--app-version", default="")
    ap.add_argument("--user", default=None)
    args = ap.parse_args()

    ext = os.path.splitext(args.file)[1].lower()
    app = {".json": "houdini", ".nk": "nuke"}.get(ext)
    if not app:
        sys.exit("unsupported file type: %s" % ext)
    context = args.context or ("comp" if app == "nuke" else "sop")
    title = args.title or os.path.splitext(os.path.basename(args.file))[0]

    name = args.name or core.ascii_slug(title) or core.ascii_slug(os.path.splitext(os.path.basename(args.file))[0])
    info = core.new_snippet(app, context, title, user=args.user, name=name)
    try:
        shutil.copyfile(args.file, info["payload"])
        if app == "nuke":
            g = graph.from_nk(core.read_text(info["payload"]), context, args.app_version)
        else:
            g = graph.from_houdini_data(core.read_json(info["payload"], {}), context,
                                        args.app_version)
        core.finalize_snippet(info, args.desc, [t.strip() for t in args.tags.split(",") if t.strip()],
                              g, extra={"scene": os.path.basename(args.file)})
    except Exception:
        core.abort_snippet(info)
        raise
    print(info["dir"])


if __name__ == "__main__":
    main()
