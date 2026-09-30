# -*- coding: utf-8 -*-
"""Houdini side: save selected network items as JSON (hou.data), load them back."""

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
            _enrich(node["network"], live)


def save_items(items, title, description="", tags=None, context=None, name=None, root=None):
    parent = items[0].parent()
    context = context or context_of(parent)
    data = hou.data.itemsAsData(items, anchor_position=_anchor(items))
    info = core.new_snippet("houdini", context, title, name=name, root=root)
    try:
        core.write_json_atomic(info["payload"], data)
        graph = graphmod.from_houdini_data(data, context, hou.applicationVersionString())
        try:
            _enrich(graph["network"], parent)
        except Exception:
            pass  # the plain JSON is enough for the viewer
        core.finalize_snippet(info, description, tags, graph, extra={
            "scene": hou.hipFile.basename(), "source_path": parent.path()})
    except Exception:
        core.abort_snippet(info)
        raise
    return info


def save_selected_dialog():
    from . import qtui
    start_bridge()
    items = _selected_items()
    if not items:
        hou.ui.displayMessage("保存するノードを選択してください。", title="Snippet Library")
        return
    parents = {i.parent().path() for i in items}
    if len(parents) > 1:
        hou.ui.displayMessage("同じネットワーク内のノードだけを選択してください。",
                              title="Snippet Library")
        return
    count = len([i for i in items if isinstance(i, hou.Node)])
    values = qtui.ask_save("houdini", context_of(items[0].parent()), None, count,
                           hou.qt.mainWindow())
    if not values:
        return
    info = save_items(items, values["title"], values["description"], values["tags"],
                      name=values["name"], root=values["root"])
    hou.ui.setStatusMessage("Snippet Library: saved %s" % info["dir"])


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
        created = hou.data.createItemsFromData(target, data, offset_position=offset)
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
