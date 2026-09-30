# -*- coding: utf-8 -*-
"""Snippet Library viewer: tiny local web server (python stdlib only, no database).

    py -3 viewer/server.py [--port 8765] [--no-browser]

Environment: SNIPPETLIB_ROOT / SNIPPETLIB_USER / SNIPPETLIB_LINKS (see launch_viewer.bat)
"""

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snippetlib import __version__, bridge, core  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WRITE_LOCK = threading.Lock()


class ApiError(Exception):
    pass


def libraries():
    return core.get_libraries()


def lib_by_id(lib_id):
    for lib in libraries():
        if lib["id"] == int(lib_id):
            return lib
    raise ApiError("library not found")


# ------------------------------------------------------------------ API
def api_state(_q):
    libs = libraries()
    return {"version": __version__, "user": core.current_user(),
            "profile": core.get_profile(), "libraries": libs,
            "profiles": core.all_profiles([l["path"] for l in libs if not l.get("missing")]),
            "palette": core.PALETTE, "root": core.library_root().replace("\\", "/"),
            "root_source": core.root_source(),
            "default_root": core.default_root().replace("\\", "/"),
            "logos": app_logos()}


LOGO_EXTS = ("svg", "png", "webp", "jpg")
LOGO_CACHE = core.local_dir("logos")  # logos picked up from installed DCCs (this machine only)


def app_logos():
    """{app: file} served under /logos/. Order: a file the user put in
    viewer/static/logos/, then one found in an installed Houdini / Nuke (copied
    once to %LOCALAPPDATA%), else nothing (text badge). Not shipped with the
    repo: the marks are trademarks of SideFX / Foundry."""
    out = {}
    for app in core.APPS:
        for folder in (os.path.join(STATIC, "logos"), LOGO_CACHE):
            for ext in LOGO_EXTS:
                fn = "%s.%s" % (app, ext)
                if os.path.isfile(os.path.join(folder, fn)):
                    out.setdefault(app, fn)
        if app not in out:
            fn = _logo_from_install(app)
            if fn:
                out[app] = fn
    return out


def _newest(pattern):
    """Highest version among install folders matching the glob."""
    import glob
    import re

    def key(p):
        return [int(x) for x in re.findall(r"\d+", os.path.basename(os.path.dirname(p)) or p)]
    hits = glob.glob(pattern)
    return max(hits, key=key) if hits else None


def _logo_from_install(app):
    """Copy the application's own logo into LOGO_CACHE. Windows install layouts:
      Houdini: <HFS>/houdini/config/Icons/icons.zip -> MISC/logo.svg
      Nuke:    <Nuke>/plugins/icons/NukeApp128.png"""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    try:
        if app == "houdini":
            hfs = os.environ.get("HFS")
            zips = [os.path.join(hfs, "houdini", "config", "Icons", "icons.zip")] if hfs else []
            found = _newest(os.path.join(pf, "Side Effects Software", "Houdini *", "houdini",
                                         "config", "Icons", "icons.zip"))
            if found:
                zips.append(found)
            import zipfile
            for z in zips:
                if os.path.isfile(z):
                    with zipfile.ZipFile(z) as zf:
                        data = zf.read("MISC/logo.svg")
                    dest = os.path.join(LOGO_CACHE, "houdini.svg")
                    with open(dest, "wb") as f:
                        f.write(data)
                    return "houdini.svg"
        elif app == "nuke":
            found = _newest(os.path.join(pf, "Nuke*", "plugins", "icons", "NukeApp128.png"))
            if found:
                import shutil
                shutil.copyfile(found, os.path.join(LOGO_CACHE, "nuke.png"))
                return "nuke.png"
    except Exception:
        pass
    return None


def api_snippets(_q):
    out = []
    for lib in libraries():
        if lib.get("missing"):
            continue
        for meta in core.scan_library(lib["path"]):
            meta["lib"] = lib["id"]
            out.append(meta)
    return {"snippets": out}


def api_snippet(q):
    lib = lib_by_id(q["lib"])
    snip = core.read_snippet(lib["path"], q["rel"])
    return {"meta": snip["meta"], "description": snip["description"], "graph": snip["graph"],
            "dir": snip["dir"].replace("\\", "/"), "payload": snip["payload"].replace("\\", "/")}


def api_payload(q):
    lib = lib_by_id(q["lib"])
    snip = core.read_snippet(lib["path"], q["rel"])
    return {"text": core.read_text(snip["payload"])}


def api_sessions(q):
    return {"sessions": bridge.list_sessions(q.get("app") or None)}


def api_update(body):
    lib = lib_by_id(body["lib"])
    md = core.find_md(core.resolve_rel(lib["path"], body["rel"]))
    if not md:
        raise ApiError("snippet not found")
    with WRITE_LOCK:
        meta = core.update_snippet(md, title=body.get("title"),
                                   description=body.get("description"),
                                   tags=body.get("tags"), crown=body.get("crown"))
    return {"meta": meta}


def api_profile(body):
    return {"profile": core.save_profile(display=body.get("display"), color=body.get("color"))}


def api_links(body):
    with WRITE_LOCK:
        if body.get("action") == "add":
            core.add_link(body["path"].strip().strip('"'), body.get("name", "").strip())
        elif body.get("action") == "remove":
            core.remove_link(body["path"])
        elif body.get("action") == "create":
            core.create_library(body.get("path", ""), body.get("name", "").strip())
        elif body.get("action") == "library":
            core.set_library_info(name=body.get("name"), color=body.get("color"))
    return {"libraries": libraries()}


def api_root(body):
    if core.root_source() == "env":
        raise ApiError("環境変数 SNIPPETLIB_ROOT で固定されています（起動 bat を編集してください）")
    with WRITE_LOCK:
        root = core.set_library_root(body.get("path", ""), create=bool(body.get("create")))
        os.makedirs(os.path.join(root, core.CONFIG_DIR), exist_ok=True)
    return api_state({})


def api_load(body):
    lib = lib_by_id(body["lib"])
    snip = core.read_snippet(lib["path"], body["rel"])
    if not os.path.isfile(snip["payload"]):
        raise ApiError("payload が見つかりません")
    return bridge.send_request(body["session"], {
        "action": "load", "payload": snip["payload"], "meta": snip["meta"]})


def api_copy(body):
    """Copy a snippet from library `lib` into library `to` (defaults to primary)."""
    lib = lib_by_id(body["lib"])
    dest = lib_by_id(body.get("to", 0))
    if dest["id"] == lib["id"]:
        raise ApiError("同じライブラリです")
    if dest.get("missing"):
        raise ApiError("コピー先のライブラリが見つかりません: %s" % dest["path"])
    rel = core.import_snippet(lib["path"], body["rel"], lib["name"], root=dest["path"])
    return {"lib": dest["id"], "rel": rel, "name": dest["name"]}


def api_delete(body):
    lib = lib_by_id(body["lib"])
    with WRITE_LOCK:
        dest = core.trash_snippet(lib["path"], body["rel"])
    return {"trash": dest.replace("\\", "/")}


def api_reveal(body):
    lib = lib_by_id(body["lib"])
    path = core.resolve_rel(lib["path"], body["rel"])
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", os.path.normpath(path)])
    return {}


GET = {"/api/state": api_state, "/api/snippets": api_snippets, "/api/snippet": api_snippet,
       "/api/payload": api_payload, "/api/sessions": api_sessions}
POST = {"/api/update": api_update, "/api/profile": api_profile, "/api/links": api_links,
        "/api/load": api_load, "/api/copy": api_copy, "/api/reveal": api_reveal,
        "/api/delete": api_delete, "/api/root": api_root}


class Handler(BaseHTTPRequestHandler):
    server_version = "SnippetLibrary/" + __version__

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _local_only(self):
        # The API writes files: refuse anything that is not our own page.
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _run(self, func, arg):
        try:
            self._send(200, func(arg))
        except (ApiError, ValueError, RuntimeError, KeyError, OSError) as exc:
            self._send(400, {"error": "%s" % exc})

    def do_GET(self):
        url = urlparse(self.path)
        if not self._local_only():
            return self._send(403, {"error": "forbidden"})
        if url.path == "/api/ping":
            return self._send(200, {"app": "snippetlibrary", "root": core.library_root()})
        if url.path in GET:
            return self._run(GET[url.path], {k: v[0] for k, v in parse_qs(url.query).items()})
        name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
        path = os.path.abspath(os.path.join(STATIC, name))
        if name.startswith("logos/") and not os.path.isfile(path):  # auto-detected DCC logo
            path = os.path.abspath(os.path.join(LOGO_CACHE, os.path.basename(name)))
            if not path.startswith(LOGO_CACHE) or not os.path.isfile(path):
                return self._send(404, {"error": "not found"})
        elif not path.startswith(STATIC) or not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        with open(path, "rb") as f:
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, f.read(), ctype)

    def do_POST(self):
        url = urlparse(self.path)
        # custom header => cross-site pages cannot POST here without a CORS preflight
        if not self._local_only() or self.headers.get("X-SnippetLib") != "1":
            return self._send(403, {"error": "forbidden"})
        if url.path not in POST:
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        self._run(POST[url.path], body)


class Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows "reuse" lets two servers share one port
    daemon_threads = True


def already_running(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=0.5) as r:
            info = json.loads(r.read().decode("utf-8"))
        return info.get("app") == "snippetlibrary" and \
            os.path.normcase(info.get("root", "")) == os.path.normcase(core.library_root())
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    os.makedirs(os.path.join(core.library_root(), core.CONFIG_DIR), exist_ok=True)
    port = args.port
    for port in range(args.port, args.port + 20):
        if already_running(port):  # same library already served: just show it
            if not args.no_browser:
                webbrowser.open("http://127.0.0.1:%d/" % port)
            return
        try:
            httpd = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit("no free port")
    url = "http://127.0.0.1:%d/" % port
    print("Snippet Library viewer  %s" % url)
    print("  library : %s" % core.library_root())
    print("  user    : %s" % core.current_user())
    print("(close this window to stop the viewer)")
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
