# -*- coding: utf-8 -*-
"""Houdini side: save selected network items as JSON (hou.data), load them back."""

import contextlib
import json
import os

import hou

from . import bridge, core
from . import graph as graphmod

CATEGORY_TO_CONTEXT = {"Object": "obj", "Driver": "rop"}  # others: lower case name
# container node types to try when the current network has the wrong category
CONTAINERS = {"sop": ("geo", "sopnet"), "obj": ("objnet",), "cop": ("copnet",),
              "cop2": ("cop2net",), "dop": ("dopnet",), "lop": ("lopnet",),
              "top": ("topnet",), "rop": ("ropnet",), "chop": ("chopnet",),
              "vop": ("matnet",)}


def context_of(network):
    name = network.childTypeCategory().name()
    return CATEGORY_TO_CONTEXT.get(name, name.lower())


# ---------------------------------------------------------------------- save
def _selected_items():
    items, seen = [], set()

    def add(item):
        key = (type(item).__name__, item.path() if hasattr(item, "path") else item.name())
        if key not in seen:
            seen.add(key)
            items.append(item)

    for item in hou.selectedItems():
        add(item)
        if isinstance(item, hou.NetworkBox):  # a selected box brings its contents
            for sub in item.items():
                add(sub)
    return items


def _anchor(items):
    xs = [i.position()[0] for i in items]
    ys = [i.position()[1] for i in items]
    return hou.Vector2((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5)


def _enrich(net, parent):
    """Add what the JSON does not carry: type labels, colors, sizes, parm labels."""
    horizontal = context_of(parent) in graphmod.H_HORIZONTAL
    for node in net["nodes"]:
        if node["kind"] != "node":
            continue
        live = parent.node(node["name"])
        if live is None:
            continue
        try:
            node["type_label"] = live.type().description()
            node["color"] = list(live.color().rgb())
            node["label"] = live.comment() or ""
            size = live.size()
            new_w, new_h = size[0] * graphmod.H_SCALE, size[1] * graphmod.H_SCALE
            node["y"] -= new_h - node["h"]
            node["w"], node["h"] = new_w, new_h
            node["n_in"] = min(live.type().maxNumInputs(), 8)
            node["n_out"] = live.type().maxNumOutputs()
            if horizontal:  # named ports: keep their real order for the viewer
                node["in_names"] = list(live.inputNames())
                node["out_names"] = list(live.outputNames())
            for p in node["params"]:
                pt = live.parmTuple(p["name"])
                if pt is not None:
                    p["label"] = pt.parmTemplate().label()
        except hou.Error:
            pass
        if node.get("network"):
            # editable network inside a locked asset (e.g. sopmodify -> "modify/modify")
            inner = live.node(node["net_path"]) if node.get("net_path") else live
            if inner is not None:
                _enrich(node["network"], inner)


def save_items(items, title, description="", tags=None, context=None, name=None, root=None,
               supersede=None):
    """supersede = meta of an existing snippet (with _lib / rel): the new snippet
    is saved as its next version and the old one is marked as superseded."""
    parent = items[0].parent()
    context = context or context_of(parent)
    with recipe_workarounds():
        data = hou.data.itemsAsData(items, anchor_position=_anchor(items))
    try:
        _record_extras(data, parent)
    except Exception:
        pass  # worst case: the loader guesses MaterialX from the node types
    info = core.new_snippet("houdini", context, title, name=name, root=root)
    try:
        core.write_json_atomic(info["payload"], data)
        graph = graphmod.from_houdini_data(data, context, hou.applicationVersionString())
        try:
            _enrich(graph["network"], parent)
        except Exception:
            pass  # the plain JSON is enough for the viewer
        extra = {"scene": hou.hipFile.basename(), "source_path": parent.path()}
        if supersede:
            extra["version"] = int(supersede.get("version") or 1) + 1
        core.finalize_snippet(info, description, tags, graph, extra=extra)
        if supersede:
            core.mark_superseded(supersede["_lib"]["path"], supersede["rel"], info["root"],
                                 os.path.relpath(info["dir"], info["root"]).replace("\\", "/"))
    except Exception:
        core.abort_snippet(info)
        raise
    return info


@contextlib.contextmanager
def recipe_workarounds():
    """Houdini 22.0's recipe API (hou.data.itemsAsData) raises IndexError on a
    Copernicus network when a node has a wire on an input beyond its named
    inputs: the COP Output node reports no input names at all, so every COP
    snippet with a connected Output node failed to save. Fall back to the plain
    index; our loader wires by index just as well."""
    try:
        from hrecipes.api import networkitemconnection as nic
    except ImportError:
        yield
        return
    orig = getattr(nic, "_inputIndexToName", None)
    if orig is None:
        yield
        return

    def tolerant(item, index, *args, **kwargs):
        try:
            return orig(item, index, *args, **kwargs)
        except IndexError:
            return index

    nic._inputIndexToName = tolerant
    try:
        yield
    finally:
        nic._inputIndexToName = orig


def _selection_for_save():
    items = _selected_items()
    if not items:
        hou.ui.displayMessage("保存するノードを選択してください。", title="Snippet Library")
        return None
    if len({i.parent().path() for i in items}) > 1:
        hou.ui.displayMessage("同じネットワーク内のノードだけを選択してください。",
                              title="Snippet Library")
        return None
    return items


def save_selected_dialog(supersede=None):
    from . import qtui
    start_bridge()
    items = _selection_for_save()
    if not items:
        return
    count = len([i for i in items if isinstance(i, hou.Node)])
    values = qtui.ask_save("houdini", context_of(items[0].parent()), None, count,
                           hou.qt.mainWindow(), prefill=supersede)
    if not values:
        return
    supersede = values.get("supersede") or supersede  # the dialog may have offered "new version"
    info = save_items(items, values["title"], values["description"], values["tags"],
                      name=values["name"], root=values["root"], supersede=supersede)
    hou.ui.setStatusMessage("Snippet Library: saved %s" % info["dir"])


def overwrite_selected_dialog():
    """Pick an existing snippet, then save the selection as its new version."""
    from . import qtui
    start_bridge()
    if not _selection_for_save():
        return
    old = qtui.pick_snippet("houdini", hou.qt.mainWindow())
    if old:
        save_selected_dialog(supersede=old)


# ---------------------------------------------------------------------- load
def _network_editor():
    editors = [p for p in hou.ui.paneTabs() if p.type() == hou.paneTabType.NetworkEditor]
    for editor in editors:
        if editor.isCurrentTab():
            return editor
    return editors[0] if editors else None


def _target_network(parent, context):
    """The current network if the category matches, else a new container in it."""
    if not context or context_of(parent) == context:
        return parent, False
    for type_name in CONTAINERS.get(context, ()):
        try:
            return parent.createNode(type_name, "snippetlib_%s" % context), True
        except hou.Error:
            continue
    raise RuntimeError("このスニペットは %s 用です。%s ネットワークを開いてからロードしてください。"
                       "（現在: %s）" % (context, context, parent.path()))


def load(payload_path, meta=None):
    data = core.read_json(payload_path)
    if not data:
        raise RuntimeError("読み込めません: %s" % payload_path)
    editor = _network_editor()
    if editor is None:
        raise RuntimeError("Network Editor が見つかりません。")
    parent = editor.pwd()
    if not parent.isEditable():
        raise RuntimeError("%s はロックされています。" % parent.path())
    context = (meta or {}).get("context") or \
        os.path.basename(os.path.dirname(os.path.dirname(payload_path)))
    with hou.undos.group("Snippet Library: load"):
        target, is_new = _target_network(parent, context)
        if is_new:
            target.setPosition(editor.visibleBounds().center())
            offset = hou.Vector2(0, 0) - _data_center(data)
        else:  # drop the block in the middle of what the user is looking at
            offset = editor.visibleBounds().center() - _data_center(data)
        created = _create_items(target, data, offset)
    hou.clearAllSelected()
    top = [i for i in created.values() if i.parent() == target]
    for item in top:
        item.setSelected(True)
    if is_new:
        editor.cd(target.path())
    message = "%d items -> %s" % (len(top), target.path())
    saved_in = (meta or {}).get("app_version") or ""
    if saved_in and saved_in != hou.applicationVersionString():
        message += "  (保存時 Houdini %s / 現在 %s)" % (saved_in, hou.applicationVersionString())
    hou.ui.setStatusMessage("Snippet Library: loaded " + message)
    return message


SHADER_LANG_KEY = "snippetlib_shader_language"
PARM_UI_KEY = "snippetlib_parm_interface"


def _record_extras(data, parent):
    """What hou.data does not carry, stored in each node's user_data (removed
    again on load):

    * SHADER_LANG_KEY: a VOP node's shader language (MaterialX / VEX / OSL ...).
      A VOP subnet's connector storage types depend on it (a MaterialX string
      parameter is a uniform "ustring").
    * PARM_UI_KEY: folder tags and menu generator scripts of nodes whose
      parameter interface hou.data re-applies on load (nodes with spare
      parameters, "parmtemplates" in the data); that re-application drops both."""
    for name, d in data.items():
        if not isinstance(d, dict):
            continue
        live = parent.node(name)
        if live is None:
            continue
        if isinstance(live, hou.VopNode):
            try:
                lang = live.shaderLanguageName()
            except hou.Error:
                lang = ""
            if lang:  # VEX too: inside a MaterialX subnet a VEX parameter must stay varying
                d.setdefault("user_data", {})[SHADER_LANG_KEY] = lang
        extras = _parm_interface_extras(live, interface=bool(d.get("parmtemplates")))
        if extras:
            d.setdefault("user_data", {})[PARM_UI_KEY] = json.dumps(extras, ensure_ascii=False)
        if isinstance(d.get("children"), dict):
            _record_extras(d["children"], live)
        for path, e in (d.get("editables") or {}).items():
            inner = live.node(path)
            if inner is not None and isinstance(e.get("children"), dict):
                _record_extras(e["children"], inner)


_record_shader_language = _record_extras  # old name


def _parm_interface_extras(node, interface=True):
    """{"tags": {folder name: tags}, "generators": {parm name: [script, language]},
    "locked": [parm names]}. hou.data records the lock of a parameter only
    together with a non-default value, so locks at default values (the 43
    locked ramp parameters of a Karma ROP, a parameter a user locked without
    changing it) come back unlocked. Tags / generators only matter when
    hou.data re-applies the interface (interface=True)."""
    tags, gens = {}, {}

    def walk(templates):
        for t in templates:
            if isinstance(t, hou.FolderParmTemplate):
                if t.tags():
                    tags[t.name()] = dict(t.tags())
                walk(t.parmTemplates())
                continue
            gen = getattr(t, "itemGeneratorScript", None)
            if gen is None:
                continue
            menu = {}
            if gen():
                menu["gen"] = [gen(), t.itemGeneratorScriptLanguage().name()]
            try:
                if t.menuType() != hou.menuType.Normal:  # Mini / ControlNextParameter ... also dropped
                    menu["type"] = t.menuType().name()
            except hou.Error:
                pass
            if menu:
                gens[t.name()] = menu

    out = {}
    try:
        if interface:
            walk(node.parmTemplateGroup().parmTemplates())
        locked = [p.name() for p in node.parms() if p.isLocked()]
    except hou.Error:
        return None
    if tags:
        out["tags"] = tags
    if gens:
        out["generators"] = gens
    if locked:
        out["locked"] = locked
    return out or None


def _guess_shader_language(children):
    """Snippets saved before languages were recorded at all: MaterialX if the
    subnet holds mtlx* nodes. Never used when the payload carries records."""
    if any(isinstance(c, dict) and str(c.get("type", "")).startswith("mtlx") for c in children.values()):
        return "MaterialX"
    return None


def _has_language_records(data):
    for d in data.values():
        if not isinstance(d, dict):
            continue
        if SHADER_LANG_KEY in (d.get("user_data") or {}):
            return True
        if isinstance(d.get("children"), dict) and _has_language_records(d["children"]):
            return True
    return False


def _create_items(target, data, offset):
    """createItemsFromData with cooking paused, built level by level:
    nodes (no children, no wires) -> shader languages -> wires -> children.

    Paused: nodes that translate to USD while being built (the parameter VOPs
    inside an Edit Material LOP) otherwise cook half-configured and pop "Error
    while translating a USD shader" dialogs.

    Languages before wires: a VOP connector's storage (uniform / varying) is
    decided from the node's shader language when the wire is made and never
    recomputed, so a MaterialX parameter wired while still VEX stays varying
    ("Input storage type (uniform/varying) does not match input 'file'" on
    every mtlximage) and a VEX parameter wired as MaterialX becomes uniform.
    Languages are per node, not per subnet: a VEX subnet made by Edit Material
    holds MaterialX parameters next to VEX ones."""
    old = hou.updateModeSetting()
    hou.setUpdateMode(hou.updateMode.Manual)
    try:
        return _create_level(target, data, offset, clear=False, guess=not _has_language_records(data))
    finally:
        hou.setUpdateMode(old)


def _create_level(parent, data, offset, clear, guess):
    shallow, wires = {}, []
    for name, d in data.items():
        if isinstance(d, dict):
            d = dict(d)
            d.pop("children", None)
            for w in d.pop("inputs", None) or []:
                wires.append((name, w))
        shallow[name] = d
    made = hou.data.createItemsFromData(parent, shallow, offset_position=offset, clear_content=clear)
    for name, item in list(made.items()):
        d = data.get(name)
        if isinstance(item, hou.Node) and isinstance(d, dict) and d.get("flags"):
            _apply_flags(item, d["flags"])
        if isinstance(item, hou.Node) and isinstance(d, dict) and PARM_UI_KEY in (d.get("user_data") or {}):
            _repair_parm_templates(item, d["user_data"][PARM_UI_KEY])
            if PARM_UI_KEY in item.userDataDict():
                item.destroyUserData(PARM_UI_KEY)
        if not isinstance(item, hou.VopNode) or not isinstance(d, dict):
            continue
        lang = (d.get("user_data") or {}).get(SHADER_LANG_KEY)
        if not lang and guess and isinstance(d.get("children"), dict):
            lang = _guess_shader_language(d["children"])
        if lang:
            try:
                item.setShaderLanguageName(lang)
            except hou.Error:
                pass
        if SHADER_LANG_KEY in item.userDataDict():
            item.destroyUserData(SHADER_LANG_KEY)
    for name, w in wires:
        _wire(parent, made, name, w)
    for name, item in list(made.items()):
        d = data.get(name)
        if isinstance(item, hou.Node) and isinstance(d, dict) and isinstance(d.get("children"), dict) and d["children"]:
            sub = _create_level(item, d["children"], hou.Vector2(0, 0), clear=True, guess=guess)
            made.update({name + "/" + k: v for k, v in sub.items()})
    return made


FLAG_SETTERS = {"display": ("isDisplayFlagSet", "setDisplayFlag"), "render": ("isRenderFlagSet", "setRenderFlag"),
                "template": ("isTemplateFlagSet", "setTemplateFlag"), "bypass": ("isBypassed", "bypass"),
                "lock": ("isHardLocked", "setHardLocked"), "export": ("isExportFlagSet", "setExportFlag"),
                "audio": ("isAudioFlagSet", "setAudioFlag"), "debug": ("isDebugFlagSet", "setDebugFlag"),
                "highlight": ("isHighlightFlagSet", "setHighlightFlag"), "compress": ("isCompressFlagSet", "setCompressFlag")}


def _apply_flags(node, flags):
    """hou.data records every node's flags but createItemsFromData only restores
    them for some categories: a DOP Output node comes back without its display
    flag and a TOP scheduler without its render flag (Houdini 22.0). Apply what
    the payload says, only where the live node differs."""
    for key, want in flags.items():
        getter, setter = FLAG_SETTERS.get(key, (None, None))
        if setter is None or not hasattr(node, setter) or not hasattr(node, getter):
            continue
        try:
            if bool(getattr(node, getter)()) != bool(want):
                getattr(node, setter)(bool(want))
        except hou.Error:
            pass


def _repair_parm_templates(node, recorded):
    """When a node has spare parameters (every camera / light / geo object has
    them), hou.data re-applies the whole parameter interface on load and that
    copy drops two things (Houdini 22.0): folder tags such as
    sidefx::switcher (the spare tabs then show up as a second tab row) and the
    item generator scripts of menus (the camera's Choose Resolution menu comes
    back empty). Put back what _parm_interface_extras recorded at save time."""
    try:
        extras = json.loads(recorded) if isinstance(recorded, str) else recorded
        live = node.parmTemplateGroup()
    except (ValueError, hou.Error):
        return
    changed = False
    for name, tags in (extras.get("tags") or {}).items():
        t = live.find(name)
        if isinstance(t, hou.FolderParmTemplate) and dict(t.tags()) != tags:
            t.setTags(dict(t.tags(), **tags))
            live.replace(name, t)
            changed = True
    for name, menu in (extras.get("generators") or {}).items():
        t = live.find(name)
        if t is None or not hasattr(t, "itemGeneratorScript"):
            continue
        if isinstance(menu, list):  # first payload format: [script, language]
            menu = {"gen": menu}
        fixed = False
        if menu.get("gen") and t.itemGeneratorScript() != menu["gen"][0]:
            t.setItemGeneratorScript(menu["gen"][0])
            t.setItemGeneratorScriptLanguage(getattr(hou.scriptLanguage, menu["gen"][1], hou.scriptLanguage.Python))
            fixed = True
        if menu.get("type") and t.menuType().name() != menu["type"] and hasattr(hou.menuType, menu["type"]):
            t.setMenuType(getattr(hou.menuType, menu["type"]))
            fixed = True
        if fixed:
            live.replace(name, t)
            changed = True
    if changed:
        try:
            node.setParmTemplateGroup(live)
        except hou.Error as exc:
            print("SnippetLibrary: could not repair parameter interface of %s: %s" % (node.path(), exc))
    for name in extras.get("locked") or []:
        parm = node.parm(name)
        if parm is not None and not parm.isLocked():
            try:
                parm.lock(True)
            except hou.Error:
                pass


def _wire(parent, made, name, w):
    """Recreate one input connection from hou.data's {"from", "from_index", "to_index"}.
    Indices are ints, or connector names in COP / VOP networks. A source that is
    not part of the snippet is looked up by name in the parent, like
    createItemsFromData(external_connections=True) does."""
    dst = made.get(name)
    src = made.get(w.get("from"))
    if src is None and w.get("from"):
        src = parent.item(w["from"]) if hasattr(parent, "item") else parent.node(w["from"])
    if dst is None or src is None:
        return
    fi, ti = w.get("from_index", 0), w.get("to_index", 0)
    try:
        if isinstance(dst, hou.NetworkDot):  # a dot has one unnamed input
            dst.setInput(src, _output_index(src, fi))
            return
        if not isinstance(dst, hou.Node):
            return
        in_names = dst.inputNames()
        named_in = isinstance(ti, str) or (isinstance(fi, str) and ti < len(in_names))
        if named_in and isinstance(src, hou.Node):
            in_name = ti if isinstance(ti, str) else in_names[ti]
            out_name = fi if isinstance(fi, str) else src.outputNames()[fi]
            dst.setNamedInput(in_name, src, out_name)
        else:  # plain index (SOP ...), dots / indirect inputs, or a COP input beyond the named ones (Output node)
            in_index = in_names.index(ti) if isinstance(ti, str) else ti
            dst.setInput(in_index, src, _output_index(src, fi))
    except (hou.Error, ValueError, IndexError) as exc:
        print("SnippetLibrary: could not wire %s[%s] <- %s[%s]: %s" % (name, ti, w.get("from"), fi, exc))


def _output_index(src, fi):
    if isinstance(fi, int):
        return fi
    if isinstance(src, hou.Node):
        return list(src.outputNames()).index(fi)
    return 0  # dots and indirect inputs have a single output


def _data_center(data):
    """Payloads saved by us are anchored around 0,0; foreign ones are absolute."""
    pts = [d["position"] for d in data.values() if isinstance(d, dict) and d.get("position")]
    if not pts:
        return hou.Vector2(0, 0)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return hou.Vector2((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5)


def show_browser():
    from . import qtui
    start_bridge()

    def on_load(path, meta):
        try:
            load(path, meta)
        except Exception as exc:
            hou.ui.displayMessage("%s" % exc, title="Snippet Library",
                                  severity=hou.severityType.Error)
    qtui.show_browser("houdini", on_load, hou.qt.mainWindow())


def open_viewer():
    from . import qtui
    start_bridge()
    qtui.launch_viewer()


# ---------------------------------------------------------------------- bridge
def _handle(request):
    if request.get("action") == "load":
        return load(request["payload"], request.get("meta"))
    raise RuntimeError("unknown action: %s" % request.get("action"))


def start_bridge():
    if hou.isUIAvailable():
        bridge.start("houdini", hou.applicationVersionString(),
                     lambda: hou.hipFile.name(), _handle)
