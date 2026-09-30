# -*- coding: utf-8 -*-
"""Nuke side: save selected nodes as .nk (nuke.nodeCopy), load with nodePaste."""

import os

import nuke

from . import bridge, core
from . import graph as graphmod

CONTEXTS = ["comp", "3d", "deep", "particle", "gizmo", "tool"]
_3D_CLASSES = ("Scene", "Camera", "Camera2", "Camera3", "Camera4", "ScanlineRender",
               "ScanlineRender2", "ReadGeo", "ReadGeo2", "Card", "Card2", "GeoCard",
               "Axis", "Axis2", "Axis3", "Light", "Light2", "Light3", "TransformGeo")


def _guess_context(nodes):
    classes = [n.Class() for n in nodes]
    if any(c.startswith("Deep") for c in classes):
        return "deep"
    if any(c.startswith("Particle") for c in classes):
        return "particle"
    if any(c in _3D_CLASSES or c.startswith("Geo") for c in classes):
        return "3d"
    return "comp"


def _main_window():
    from .qtui import QtWidgets
    app = QtWidgets.QApplication.instance()
    for widget in app.topLevelWidgets() if app else []:
        if widget.inherits("QMainWindow") and widget.metaObject().className() == "Foundry::UI::DockMainWindow":
            return widget
    return app.activeWindow() if app else None


# ---------------------------------------------------------------------- save
def _enrich(net, parent):
    """Replace parsed guesses with what the live nodes say: wires, size, color."""
    live = {}
    with parent:
        for n in nuke.allNodes():
            live[n.name()] = n
    names = {n["name"] for n in net["nodes"]}
    wires = []
    for node in net["nodes"]:
        ln = live.get(node["name"])
        if ln is None:
            continue
        node["w"] = ln.screenWidth() * graphmod.N_SCALE or node["w"]
        node["h"] = ln.screenHeight() * graphmod.N_SCALE or node["h"]
        if node["kind"] == "node":
            color = int(ln["tile_color"].value()) or int(nuke.defaultNodeColor(ln.Class()))
            node["color"] = [((color >> s) & 255) / 255.0 for s in (24, 16, 8)]
            node["n_in"] = min(ln.maxInputs(), 8)
            for p in node["params"]:
                knob = ln.knob(p["name"])
                if knob is not None:
                    p["label"] = knob.label() or ""
        node["ext_inputs"] = []
        for i in range(ln.inputs()):
            src = ln.input(i)
            if src is None:
                continue
            if src.name() in names:
                wires.append({"src": src.name(), "src_out": 0, "dst": node["name"], "dst_in": i})
            else:
                node["ext_inputs"].append({"dst_in": i, "from": src.name()})
        if node.get("network") is not None and hasattr(ln, "begin"):
            _enrich(node["network"], ln)
    if all(n["name"] in live for n in net["nodes"]):
        net["wires"] = wires  # live wiring is authoritative over the parsed stack


def _parent_of(nodes):
    try:
        return nodes[0].parent() or nuke.root()
    except Exception:
        return nuke.root()


def save_nodes(title, description="", tags=None, context="comp"):
    """Saves the current selection."""
    info = core.new_snippet("nuke", context, title)
    try:
        nuke.nodeCopy(info["payload"])
        graph = graphmod.from_nk(core.read_text(info["payload"]), context,
                                 nuke.NUKE_VERSION_STRING)
        try:
            _enrich(graph["network"], _parent_of(nuke.selectedNodes()))
        except Exception:
            pass  # the parsed .nk is enough for the viewer
        core.finalize_snippet(info, description, tags, graph, extra={
            "scene": os.path.basename(nuke.root().name())})
    except Exception:
        core.abort_snippet(info)
        raise
    return info


def save_selected_dialog():
    from . import qtui
    start_bridge()
    nodes = nuke.selectedNodes()
    if not nodes:
        nuke.message("保存するノードを選択してください。")
        return
    values = qtui.ask_save("nuke", _guess_context(nodes), CONTEXTS, len(nodes), _main_window())
    if not values:
        return
    info = save_nodes(values["title"], values["description"], values["tags"],
                      values["context"] or "comp")
    nuke.tprint("Snippet Library: saved %s" % info["dir"])


# ---------------------------------------------------------------------- load
def load(payload_path, meta=None):
    if not os.path.isfile(payload_path):
        raise RuntimeError("読み込めません: %s" % payload_path)
    for n in nuke.selectedNodes():
        n.setSelected(False)
    try:
        center = nuke.center()
    except Exception:
        center = None
    nuke.nodePaste(payload_path)
    nodes = nuke.selectedNodes()
    if center and nodes:  # move the pasted block to the middle of the DAG view
        xs = [n.xpos() for n in nodes]
        ys = [n.ypos() for n in nodes]
        dx = int(center[0] - (min(xs) + max(xs)) / 2)
        dy = int(center[1] - (min(ys) + max(ys)) / 2)
        for n in nodes:
            n.setXYpos(n.xpos() + dx, n.ypos() + dy)
    message = "%d nodes" % len(nodes)
    saved_in = (meta or {}).get("app_version") or ""
    if saved_in and saved_in != nuke.NUKE_VERSION_STRING:
        message += "  (保存時 Nuke %s / 現在 %s)" % (saved_in, nuke.NUKE_VERSION_STRING)
    return message


def show_browser():
    from . import qtui
    start_bridge()

    def on_load(path, meta):
        try:
            load(path, meta)
        except Exception as exc:
            nuke.message("%s" % exc)
    qtui.show_browser("nuke", on_load, _main_window())


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
    if nuke.GUI:
        bridge.start("nuke", nuke.NUKE_VERSION_STRING, lambda: nuke.root().name(), _handle)
