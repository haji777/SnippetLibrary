# -*- coding: utf-8 -*-
"""Library layout, users, profiles, snippet files. No database: plain files only.

Layout::

    <root>/_config/library.json            library name / color / linked libraries
    <root>/_config/profiles/<user>.json    one file per user (no write conflicts)
    <root>/_trash/<app>/<user>/<context>/  deleted snippets (moved, never erased)
    <root>/<app>/<user>/<context>/<YYYYMMDD.NNN>/<user>_<context>_<title>.json|.nk
                                                 ....md          meta + readable network info
                                                 ....graph.json  network for the viewer

Concurrency: every snippet lives in its own directory which is allocated with
an atomic os.mkdir(), all files are written to a temp file and os.replace()d,
and .md updates re-check the mtime before replacing.
"""

import datetime
import getpass
import hashlib
import json
import os
import re
import shutil
import time

APPS = ("houdini", "nuke")
CONFIG_DIR = "_config"
TRASH_DIR = "_trash"  # "_" folders are never scanned
ENV_ROOT = "SNIPPETLIB_ROOT"
ENV_USER = "SNIPPETLIB_USER"
ENV_LINKS = "SNIPPETLIB_LINKS"

PAYLOAD_EXT = {"houdini": ".json", "nuke": ".nk"}
GRAPH_EXT = ".graph.json"

PALETTE = [
    "#ff5c5c", "#ff8a3d", "#ffc53d", "#b8e04a", "#4ade80", "#2dd4bf",
    "#38bdf8", "#6e8bff", "#a78bfa", "#e879f9", "#fb7185", "#c9a27a",
]

DESCRIPTION_HEADING = "## Description"


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------
def repo_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_root():
    return os.path.join(repo_dir(), "snippetLibrary")


def _settings_path():
    return os.path.join(local_dir(), "settings.json")


def local_settings():
    """Per machine settings (%LOCALAPPDATA%/SnippetLibrary/settings.json)."""
    return read_json(_settings_path(), {}) or {}


def library_root():
    """Primary library, in order: SNIPPETLIB_ROOT (project launcher / DCC env),
    the machine setting chosen in the viewer, or <repo>/snippetLibrary."""
    root = os.environ.get(ENV_ROOT) or local_settings().get("root") or default_root()
    return os.path.abspath(root)


def root_source():
    if os.environ.get(ENV_ROOT):
        return "env"
    return "settings" if local_settings().get("root") else "default"


def set_library_root(path, create=False):
    """Save the machine setting. Returns the new root."""
    raw = (path or "").strip().strip('"')
    if not raw or not os.path.isabs(raw):  # "" would resolve to the cwd (= the code folder)
        raise ValueError("絶対パスを入力してください")
    path = os.path.abspath(raw)
    drive, tail = os.path.splitdrive(path)
    if tail in ("", os.sep, "/") or os.path.normcase(path) == os.path.normcase(repo_dir()):
        raise ValueError("そのフォルダはライブラリにできません: %s" % path)
    if not os.path.isdir(path):
        if not create:
            raise ValueError("フォルダが見つかりません: %s" % path)
        os.makedirs(path)
    settings = local_settings()
    settings["root"] = path.replace("\\", "/")
    write_json_atomic(_settings_path(), settings, indent=2)
    return path


def current_user():
    """Windows login name; SNIPPETLIB_USER overrides it."""
    name = os.environ.get(ENV_USER) or getpass.getuser() or "unknown"
    return safe_name(name).lower() or "unknown"


def local_dir(*parts):
    """Per machine scratch dir (index cache, DCC sessions). Never shared."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "SnippetLibrary", *parts)
    os.makedirs(path, exist_ok=True)
    return path


def safe_name(text):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", text or "").strip().strip(".")
    return re.sub(r"\s+", "_", text)[:80]


def ascii_slug(text):
    """File-name part: ASCII letters, digits, '_' '-' '.' only (DCCs such as Nuke
    cannot handle non-ASCII paths). Anything else is dropped, so a Japanese
    title yields "" and the caller must ask for a name."""
    text = re.sub(r"[^A-Za-z0-9_\-. ]", "", text or "").strip().strip(".")
    return re.sub(r"\s+", "_", text)[:60]


def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------------------
# file helpers
# --------------------------------------------------------------------------
def write_text_atomic(path, text):
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), int(time.time() * 1000) % 100000)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # someone is reading it right now (SMB / AV)
            time.sleep(0.1 * (attempt + 1))
    os.replace(tmp, path)


def write_json_atomic(path, data, indent=1):
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=indent))


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def read_json(path, default=None):
    try:
        return json.loads(read_text(path))
    except (OSError, ValueError):
        return default


# --------------------------------------------------------------------------
# markdown + frontmatter (JSON flavoured YAML so Obsidian reads it as properties)
# --------------------------------------------------------------------------
def _parse_scalar(raw):
    raw = raw.strip()
    if raw == "":
        return ""
    try:
        return json.loads(raw)
    except ValueError:
        pass
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        return [_parse_scalar(x) for x in raw[1:-1].split(",") if x.strip()]
    return raw


def parse_md(text):
    """-> (meta dict, body). Tolerates frontmatter rewritten by Obsidian."""
    meta = {}
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return meta, text
    end = text.find("\n---", 4)
    if end < 0:
        return meta, text
    key = None
    for line in text[4:end].split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s+-\s*(.*)$", line) or re.match(r"^-\s+(.*)$", line)
        if m and key is not None:  # yaml block list item
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_parse_scalar(m.group(1)))
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            key = m.group(1)
            meta[key] = _parse_scalar(m.group(2))
    body = text[end + 4:]
    return meta, body.lstrip("\n")


def dump_md(meta, body):
    lines = ["---"]
    for k, v in meta.items():
        lines.append("%s: %s" % (k, json.dumps(v, ensure_ascii=False)))
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.lstrip("\n")


def get_description(body):
    lines = body.replace("\r\n", "\n").split("\n")
    out, inside = [], False
    for line in lines:
        if line.strip() == DESCRIPTION_HEADING:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def set_description(body, description):
    lines = body.replace("\r\n", "\n").split("\n")
    start = end = None
    for i, line in enumerate(lines):
        if start is None and line.strip() == DESCRIPTION_HEADING:
            start = i
        elif start is not None and line.startswith("## "):
            end = i
            break
    block = [DESCRIPTION_HEADING, "", _escape_desc(description), ""]
    if start is None:
        # after the H1 title if there is one
        pos = 1 if lines and lines[0].startswith("# ") else 0
        return "\n".join(lines[:pos] + [""] + block + lines[pos:])
    if end is None:
        end = len(lines)
    return "\n".join(lines[:start] + block + lines[end:])


def _escape_desc(text):
    # a line starting with "## " would terminate the description section
    return re.sub(r"(?m)^## ", "### ", (text or "").strip())


# --------------------------------------------------------------------------
# libraries (primary + linked)
# --------------------------------------------------------------------------
def _library_json(root):
    return os.path.join(root, CONFIG_DIR, "library.json")


def library_info(root):
    info = read_json(_library_json(root), {}) or {}
    base = os.path.basename(root.rstrip("\/"))
    if base.lower() == "snippetlibrary":  # the default <project>/snippetLibrary convention
        base = os.path.basename(os.path.dirname(root.rstrip("\/")))  # <project>/snippetLibrary
    name = info.get("name") or base or os.path.basename(root)
    return {"name": name, "color": info.get("color") or "",
            "links": info.get("links") or []}


def get_libraries(root=None):
    """Primary library first, then links from library.json and SNIPPETLIB_LINKS."""
    root = root or library_root()
    info = library_info(root)
    libs = [{"name": info["name"], "path": root, "primary": True,
             "color": info["color"], "source": "primary"}]
    seen = {os.path.normcase(os.path.abspath(root))}
    links = [dict(l, source="config") for l in info["links"]]
    for p in (os.environ.get(ENV_LINKS) or "").split(";"):
        if p.strip():
            links.append({"path": p.strip(), "source": "env"})
    for link in links:
        path = os.path.abspath(link.get("path") or "")
        key = os.path.normcase(path)
        if not link.get("path") or key in seen:
            continue
        seen.add(key)
        linfo = library_info(path) if os.path.isdir(path) else {"name": "", "color": ""}
        libs.append({"name": link.get("name") or linfo["name"] or os.path.basename(path),
                     "path": path, "primary": False, "color": linfo["color"],
                     "source": link["source"], "missing": not os.path.isdir(path)})
    for i, lib in enumerate(libs):
        lib["id"] = i
        if not lib["color"]:
            lib["color"] = PALETTE[(i * 5 + 6) % len(PALETTE)]
    return libs


def _update_library_json(root, mutate):
    path = _library_json(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    info = read_json(path, {}) or {}
    mutate(info)
    write_json_atomic(path, info, indent=2)


def add_link(path, name="", root=None):
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        raise ValueError("フォルダが見つかりません: %s" % path)

    def mutate(info):
        links = [l for l in info.get("links") or []
                 if os.path.normcase(os.path.abspath(l.get("path", ""))) != os.path.normcase(path)]
        links.append({"name": name, "path": path.replace("\\", "/")})
        info["links"] = links
    _update_library_json(root or library_root(), mutate)


def remove_link(path, root=None):
    key = os.path.normcase(os.path.abspath(path))

    def mutate(info):
        info["links"] = [l for l in info.get("links") or []
                         if os.path.normcase(os.path.abspath(l.get("path", ""))) != key]
    _update_library_json(root or library_root(), mutate)


def set_library_info(name=None, color=None, root=None):
    def mutate(info):
        if name is not None:
            info["name"] = name
        if color is not None:
            info["color"] = color
    _update_library_json(root or library_root(), mutate)


# --------------------------------------------------------------------------
# user profiles (one file per user)
# --------------------------------------------------------------------------
def default_color(user):
    h = int(hashlib.md5(user.encode("utf-8")).hexdigest(), 16)
    return PALETTE[h % len(PALETTE)]


def _profile_path(root, user):
    return os.path.join(root, CONFIG_DIR, "profiles", "%s.json" % user)


def get_profile(user=None, root=None):
    user = user or current_user()
    prof = read_json(_profile_path(root or library_root(), user), {}) or {}
    return {"user": user, "display": prof.get("display") or user,
            "color": prof.get("color") or default_color(user)}


def save_profile(display=None, color=None, user=None, root=None):
    user = user or current_user()
    root = root or library_root()
    prof = get_profile(user, root)
    if display is not None:
        prof["display"] = display.strip() or user
    if color is not None:
        prof["color"] = color
    path = _profile_path(root, user)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_json_atomic(path, prof, indent=2)
    return prof


def all_profiles(roots):
    """user -> profile. The primary library (first root) wins."""
    out = {}
    for root in reversed(list(roots)):
        pdir = os.path.join(root, CONFIG_DIR, "profiles")
        try:
            names = os.listdir(pdir)
        except OSError:
            continue
        for fn in names:
            if fn.endswith(".json"):
                out[fn[:-5]] = get_profile(fn[:-5], root)
    return out


# --------------------------------------------------------------------------
# snippets
# --------------------------------------------------------------------------
def new_snippet(app, context, title, user=None, root=None, name=None):
    """Allocate <root>/<app>/<user>/<context>/<YYYYMMDD.NNN>/ atomically.
    title = display title (any language); name = ASCII file-name part.
    Files are <user>_<context>_<name>.*, the folder is the id."""
    if app not in APPS:
        raise ValueError("unknown app: %s" % app)
    root = root or library_root()
    user = user or current_user()
    context = safe_name(context).lower() or "misc"
    parent = os.path.join(root, app, user, context)
    os.makedirs(parent, exist_ok=True)
    day = datetime.datetime.now().strftime("%Y%m%d")
    for n in range(1, 1000):
        sid = "%s.%03d" % (day, n)
        path = os.path.join(parent, sid)
        try:
            os.mkdir(path)  # atomic: two writers can never get the same id
        except FileExistsError:
            continue
        name = ascii_slug(name) or ascii_slug(title) or "untitled"
        base = "%s_%s_%s" % (user, context, name)
        return {"root": root, "dir": path, "id": sid, "app": app, "user": user,
                "context": context, "title": title, "name": name, "base": base,
                "payload": os.path.join(path, base + PAYLOAD_EXT[app]),
                "graph": os.path.join(path, base + GRAPH_EXT),
                "md": os.path.join(path, base + ".md")}
    raise RuntimeError("too many snippets today in %s" % parent)


def finalize_snippet(info, description="", tags=None, graph=None, extra=None):
    """Write graph + md. The md is written last: a dir without md is ignored."""
    from . import graph as graphmod
    graph = graph or {}
    if graph:
        write_json_atomic(info["graph"], graph)
    stats = graphmod.graph_stats(graph)
    now = now_iso()
    meta = {
        "title": info["title"],
        "app": info["app"],
        "context": info["context"],
        "user": info["user"],
        "id": info["id"],
        "name": info.get("name", ""),
        "created": now,
        "modified": now,
        "crown": False,
        "tags": list(tags or []),
        "app_version": graph.get("app_version", ""),
        "node_count": stats["count"],
        "types": stats["types"],
        "payload": os.path.basename(info["payload"]),
        "graph": os.path.basename(info["graph"]) if graph else "",
    }
    meta.update(extra or {})
    body = "# %s\n\n%s\n\n%s\n\n%s" % (
        info["title"], DESCRIPTION_HEADING, _escape_desc(description),
        graphmod.network_markdown(graph))
    write_text_atomic(info["md"], dump_md(meta, body))
    return meta


def abort_snippet(info):
    shutil.rmtree(info["dir"], ignore_errors=True)
    for d in (os.path.dirname(info["dir"]),):
        try:
            os.rmdir(d)  # only succeeds when empty
        except OSError:
            pass


def find_md(snippet_dir):
    try:
        mds = sorted(f for f in os.listdir(snippet_dir) if f.lower().endswith(".md"))
    except OSError:
        return None
    return os.path.join(snippet_dir, mds[0]) if mds else None


def update_snippet(md_path, title=None, description=None, tags=None, crown=None):
    """Edit meta/comment of an existing snippet. Safe against concurrent edits."""
    for _ in range(3):
        mtime = os.stat(md_path).st_mtime_ns
        meta, body = parse_md(read_text(md_path))
        if title is not None and title.strip():
            meta["title"] = title.strip()
            lines = body.split("\n")
            if lines and lines[0].startswith("# "):
                lines[0] = "# " + meta["title"]
                body = "\n".join(lines)
        if description is not None:
            body = set_description(body, description)
        if tags is not None:
            meta["tags"] = [t.strip() for t in tags if t.strip()]
        if crown is not None:
            meta["crown"] = bool(crown)
        meta["modified"] = now_iso()
        meta["modified_by"] = current_user()
        if os.stat(md_path).st_mtime_ns != mtime:
            continue  # somebody else wrote in between: re-read and retry
        write_text_atomic(md_path, dump_md(meta, body))
        return meta
    raise RuntimeError("他のユーザーが同時に編集中です。もう一度試してください。")


def _snippet_files(sdir):
    """payload / graph found by extension (names in the md can lag behind a rename)."""
    found = {"payload": "", "graph": ""}
    for fn in sorted(os.listdir(sdir)):
        low = fn.lower()
        if low.endswith(GRAPH_EXT):
            found["graph"] = fn
        elif low.endswith(tuple(PAYLOAD_EXT.values())):
            found["payload"] = fn
    return found


def read_snippet(root, rel):
    sdir = resolve_rel(root, rel)
    md = find_md(sdir)
    if not md:
        raise ValueError("snippet not found: %s" % rel)
    meta, body = parse_md(read_text(md))
    found = _snippet_files(sdir)
    graph = read_json(os.path.join(sdir, found["graph"] or "_"), None)
    payload = os.path.join(sdir, found["payload"] or meta.get("payload") or "")
    if graph is None and os.path.isfile(payload):
        # graph file missing (hand-copied payload): rebuild it from the payload
        from . import graph as graphmod
        try:
            if payload.endswith(".nk"):
                graph = graphmod.from_nk(read_text(payload), meta.get("context", ""))
            else:
                graph = graphmod.from_houdini_data(read_json(payload, {}),
                                                   meta.get("context", ""))
        except Exception:
            graph = None
    return {"meta": meta, "description": get_description(body), "graph": graph,
            "dir": sdir, "md": md, "payload": payload}


def trash_snippet(root, rel):
    """Delete = move the whole snippet folder to <root>/_trash/<app>/<user>/<context>/.
    Nothing is erased; move the folder back to restore it."""
    sdir = resolve_rel(root, rel)
    parts = rel.replace("\\", "/").strip("/").split("/")
    if len(parts) != 4 or parts[0] not in APPS or not find_md(sdir):
        raise ValueError("snippet not found: %s" % rel)
    parent = os.path.join(root, TRASH_DIR, *parts[:3])
    os.makedirs(parent, exist_ok=True)
    dest = os.path.join(parent, "%s__%s" % (
        parts[3], datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    try:
        os.rename(sdir, dest)  # atomic on the same volume
    except OSError:
        shutil.move(sdir, dest)
    try:  # remember who removed it and where it came from
        md = find_md(dest)
        meta, body = parse_md(read_text(md))
        meta.update({"deleted": now_iso(), "deleted_by": current_user(),
                     "deleted_from": "/".join(parts)})
        write_text_atomic(md, dump_md(meta, body))
    except Exception:
        pass
    return dest


def resolve_rel(root, rel):
    path = os.path.abspath(os.path.join(root, rel))
    if os.path.commonpath([os.path.abspath(root), path]) != os.path.abspath(root):
        raise ValueError("bad path")
    return path


def import_snippet(src_root, rel, src_lib_name="", root=None, user=None):
    """Copy a snippet from a linked library into the primary one."""
    src = read_snippet(src_root, rel)
    meta = src["meta"]
    info = new_snippet(meta.get("app"), meta.get("context", "misc"),
                       meta.get("title", ""), user=user, root=root, name=meta.get("name"))
    try:
        for fn in os.listdir(src["dir"]):
            if not fn.lower().endswith((".md", ".tmp")):
                shutil.copy2(os.path.join(src["dir"], fn), os.path.join(info["dir"], fn))
        new_meta, body = parse_md(read_text(src["md"]))
        new_meta.update({"user": info["user"], "id": info["id"], "crown": False,
                         "author": meta.get("author") or meta.get("user", ""),
                         "origin": "%s:%s" % (src_lib_name, rel.replace("\\", "/")),
                         "imported": now_iso()})
        write_text_atomic(os.path.join(info["dir"], os.path.basename(src["md"])),
                          dump_md(new_meta, body))
    except Exception:
        abort_snippet(info)
        raise
    return os.path.relpath(info["dir"], info["root"]).replace("\\", "/")


# --------------------------------------------------------------------------
# scanning (tmp index cache on the local machine, keyed by md mtime)
# --------------------------------------------------------------------------
def _subdirs(path):
    try:
        with os.scandir(path) as it:
            return [e for e in it if e.is_dir() and not e.name.startswith((".", "_"))]
    except OSError:
        return []


def scan_library(root):
    """-> list of snippet metas (+rel, desc). Only changed .md files are re-read."""
    root = os.path.abspath(root)
    key = hashlib.md5(os.path.normcase(root).encode("utf-8")).hexdigest()[:16]
    cache_path = os.path.join(local_dir("cache"), "index_%s.json" % key)
    cache = read_json(cache_path, {}) or {}
    fresh, dirty, out = {}, False, []
    for app in APPS:
        for udir in _subdirs(os.path.join(root, app)):
            for cdir in _subdirs(udir.path):
                for sdir in _subdirs(cdir.path):
                    md = find_md(sdir.path)
                    if not md:
                        continue
                    try:
                        st = os.stat(md)
                    except OSError:
                        continue
                    rel = "/".join((app, udir.name, cdir.name, sdir.name))
                    hit = cache.get(rel)
                    if hit and hit.get("_mtime") == st.st_mtime_ns:
                        entry = hit
                    else:
                        dirty = True
                        try:
                            meta, body = parse_md(read_text(md))
                        except (OSError, UnicodeDecodeError):
                            continue
                        entry = dict(meta)
                        entry.setdefault("app", app)
                        entry.setdefault("user", udir.name)
                        entry.setdefault("context", cdir.name)
                        entry.setdefault("id", sdir.name)
                        entry.setdefault("title", sdir.name)
                        entry.setdefault("created", "")
                        entry["desc"] = get_description(body)[:300]
                        entry["_mtime"] = st.st_mtime_ns
                    fresh[rel] = entry
                    item = {k: v for k, v in entry.items() if not k.startswith("_")}
                    item["rel"] = rel
                    out.append(item)
    if dirty or len(fresh) != len(cache):
        try:
            write_json_atomic(cache_path, fresh, indent=None)
        except OSError:
            pass
    return out
