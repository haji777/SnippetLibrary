# -*- coding: utf-8 -*-
"""Neutral network description used by the viewer ("graph.json") + md export.

graph   = {"schema": 1, "app", "context", "app_version", "network": NET}
NET     = {"nodes": [NODE], "wires": [WIRE], "notes": [NOTE], "boxes": [BOX]}
NODE    = {"name", "type", "type_label", "kind": "node|dot|input",
           "x", "y", "w", "h",          view units, y down, x/y = top left
           "color": [r,g,b]|None, "label", "flags": {..},
           "params": [{"name", "label", "value"}],   changed parameters only
           "ext_inputs": [{"dst_in", "from"}],       wires leaving the selection
           "network": NET|None}                       subnet / Group contents
WIRE    = {"src", "src_out", "dst", "dst_in"}     ports: index, or name (COP/VOP)
graph["flow"] = "h" for left-to-right networks (Copernicus, VOP), else "v"

Everything here is pure python so the viewer can rebuild a graph from a
payload (.json / .nk) without Houdini or Nuke.
"""

import json
import re

SCHEMA = 1

# ---------------------------------------------------------------------------
# Houdini: hou.data.itemsAsData() dict -> graph
# ---------------------------------------------------------------------------
H_SCALE = 100.0
H_NODE_W, H_NODE_H = 1.13, 0.28


def _empty_net():
    return {"nodes": [], "wires": [], "notes": [], "boxes": []}


def _h_network(items):
    net = _empty_net()
    names = set(items)
    for name, d in items.items():
        if not isinstance(d, dict):
            continue
        typ = d.get("type", "")
        pos = d.get("position") or [0, 0]
        size = d.get("size") or [2.5, 2.5]
        if typ == "StickyNote":
            net["notes"].append({
                "name": name, "text": d.get("text", ""), "color": d.get("color"),
                "x": pos[0] * H_SCALE, "y": -(pos[1] + size[1]) * H_SCALE,
                "w": size[0] * H_SCALE, "h": size[1] * H_SCALE})
            continue
        if typ == "NetworkBox":
            net["boxes"].append({
                "name": name, "title": d.get("title") or d.get("comment") or "",
                "color": d.get("color"),
                "x": pos[0] * H_SCALE, "y": -(pos[1] + size[1]) * H_SCALE,
                "w": size[0] * H_SCALE, "h": size[1] * H_SCALE})
            continue
        if typ == "NetworkDot":
            kind, w, h = "dot", 0.16, 0.16
            x, y = pos[0] - w / 2.0, pos[1] - h / 2.0  # dots are positioned by center
        elif typ == "SubnetIndirectInput":
            kind, w, h = "input", 0.6, H_NODE_H
            x, y = pos[0], pos[1]
        else:
            kind = "node"
            w, h = d.get("size") or (H_NODE_W, H_NODE_H)  # COP tiles carry their size
            x, y = pos[0], pos[1]
        node = {
            "name": name, "type": typ, "type_label": "", "kind": kind,
            "x": x * H_SCALE, "y": -(y + h) * H_SCALE, "w": w * H_SCALE, "h": h * H_SCALE,
            "color": d.get("color"), "label": d.get("comment", "") or "",
            "flags": d.get("flags") or {},
            "params": [{"name": k, "label": "", "value": v}
                       for k, v in (d.get("parms") or {}).items()],
            "ext_inputs": [], "network": None}
        sub, sub_path = _h_contents(d)
        if sub:
            node["network"], node["net_path"] = sub, sub_path
        for inp in d.get("inputs") or []:
            src = inp.get("from")
            if src is None:
                continue
            if src in names:
                net["wires"].append({"src": src, "src_out": inp.get("from_index", 0),
                                     "dst": name, "dst_in": inp.get("to_index", 0)})
            else:
                node["ext_inputs"].append({"dst_in": inp.get("to_index", 0), "from": src})
        net["nodes"].append(node)
    return net


def _h_contents(d):
    """-> (network, relative path of that network inside the node) or (None, "").

    Subnets keep their nodes in "children". Locked assets with an editable dive
    target (e.g. the SOP network of a LOP "sopmodify") keep them in
    "editables": {"modify/modify": {"children": {...}}} instead."""
    children = d.get("children")
    if isinstance(children, dict) and children:
        return _h_network(children), ""
    editables = d.get("editables")
    if not isinstance(editables, dict):
        return None, ""
    nets = [(path, e["children"]) for path, e in editables.items()
            if isinstance(e, dict) and isinstance(e.get("children"), dict) and e["children"]]
    if len(nets) == 1:
        return _h_network(nets[0][1]), nets[0][0]
    if not nets:
        return None, ""
    net = _empty_net()  # several dive targets: one container node for each
    for i, (path, kids) in enumerate(nets):
        net["nodes"].append({
            "name": path, "type": "subnet", "type_label": "editable network", "kind": "node",
            "x": i * 2.5 * H_SCALE, "y": 0, "w": H_NODE_W * H_SCALE, "h": H_NODE_H * H_SCALE,
            "color": None, "label": "", "flags": {}, "params": [], "ext_inputs": [],
            "network": _h_network(kids), "net_path": ""})
    return net, ""


def fill_missing_networks(net, items):
    """graph.json files written before editable networks were supported lack the
    inside of nodes like "sopmodify": add it from the payload. Returns True if
    anything was added."""
    changed = False
    if not isinstance(items, dict):
        return changed
    for node in (net or {}).get("nodes", []):
        d = items.get(node.get("name"))
        if not isinstance(d, dict):
            continue
        if node.get("network") is None:
            sub, sub_path = _h_contents(d)
            if sub:
                node["network"], node["net_path"] = sub, sub_path
                changed = True
        elif isinstance(d.get("children"), dict):
            changed = fill_missing_networks(node["network"], d["children"]) or changed
    return changed


H_HORIZONTAL = ("cop", "vop")  # left-to-right networks with named ports


def from_houdini_data(data, context="", app_version=""):
    """Wire ports (src_out / dst_in) are ints, or names in COP / VOP networks."""
    return {"schema": SCHEMA, "app": "houdini", "context": context,
            "flow": "h" if context in H_HORIZONTAL else "v",
            "app_version": app_version, "network": _h_network(data or {})}


# ---------------------------------------------------------------------------
# Nuke: .nk text -> graph
# ---------------------------------------------------------------------------
N_SCALE = 1.4
N_NODE_W, N_NODE_H = 80, 18
N_GROUP_CLASSES = ("Group", "LiveGroup")
N_SKIP_CLASSES = ("Root",)
N_LAYOUT_KNOBS = ("name", "xpos", "ypos", "selected", "inputs", "tile_color", "label",
                  "bdwidth", "bdheight", "disable", "note_font_size", "gl_color")


def _tcl_words(text):
    """Split tcl-ish text into commands (one per line), each a list of
    (word, quoting) where quoting is '{', '"' or ''."""
    cmds, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            if cur:
                cmds.append(cur)
                cur = []
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                if text[j] == "\\":
                    j += 1
                elif text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            cur.append((text[i + 1:j - 1], "{"))
            i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            cur.append((text[i + 1:j], '"'))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n":
                j += 1
            cur.append((text[i:j], ""))
            i = j
    if cur:
        cmds.append(cur)
    return cmds


def _unescape(word, quoting):
    if quoting == '"':
        return (word.replace("\\n", "\n").replace("\\t", "\t")
                .replace('\\"', '"').replace("\\\\", "\\"))
    return word


def _nk_int(value, default=0):
    try:
        return int(float(value)) if not str(value).lower().startswith("0x") else int(value, 16)
    except (TypeError, ValueError):
        return default


def _nk_node(cls, body):
    knobs, user_knobs = {}, []
    for cmd in _tcl_words(body):
        key = cmd[0][0]
        value = " ".join(_unescape(w, q) for w, q in cmd[1:])
        if key == "addUserKnob":
            user_knobs.append(value)
        else:
            knobs[key] = value
    total = 0
    for part in str(knobs.get("inputs", "1")).split("+"):
        total += _nk_int(part.strip(), 0)
    x, y = _nk_int(knobs.get("xpos")), _nk_int(knobs.get("ypos"))
    color = None
    if "tile_color" in knobs:
        c = _nk_int(knobs["tile_color"]) & 0xFFFFFFFF
        color = [((c >> 24) & 255) / 255.0, ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0]
    name = knobs.get("name") or cls
    label = knobs.get("label", "")
    if cls == "BackdropNode":
        item = {"name": name, "title": label, "color": color,
                "x": x * N_SCALE, "y": y * N_SCALE,
                "w": _nk_int(knobs.get("bdwidth"), 100) * N_SCALE,
                "h": _nk_int(knobs.get("bdheight"), 100) * N_SCALE}
        return "box", item, 0
    if cls == "StickyNote":
        lines = label.split("\n")
        item = {"name": name, "text": label, "color": color or [1, 0.97, 0.52],
                "x": x * N_SCALE, "y": y * N_SCALE,
                "w": max(60, max(len(l) for l in lines) * 8) * N_SCALE,
                "h": max(24, len(lines) * 16 + 8) * N_SCALE}
        return "note", item, 0
    kind = "dot" if cls == "Dot" else "node"
    w, h = (12, 12) if kind == "dot" else (N_NODE_W, N_NODE_H)
    params = [{"name": k, "label": "", "value": v} for k, v in knobs.items()
              if k not in N_LAYOUT_KNOBS]
    if user_knobs:
        params.append({"name": "addUserKnob", "label": "user knobs",
                       "value": "\n".join(user_knobs)})
    flags = {}
    if knobs.get("disable") in ("true", "1"):
        flags["bypass"] = True
    node = {"name": name, "type": cls, "type_label": "", "kind": kind,
            "x": x * N_SCALE, "y": y * N_SCALE, "w": w * N_SCALE, "h": h * N_SCALE,
            "color": color, "label": label, "flags": flags, "params": params,
            "ext_inputs": [], "network": None}
    return "node", node, total


def _unique(net, node):
    names = {n["name"] for n in net["nodes"]}
    base, i = node["name"], 1
    while node["name"] in names:
        node["name"] = "%s#%d" % (base, i)
        i += 1


def from_nk(text, context="", app_version=""):
    """Replays the .nk stack machine: every node pops `inputs` entries (top of
    the stack is input 0) and pushes itself."""
    root = _empty_net()
    nets, stacks, groups, variables = [root], [[]], [], {}
    for cmd in _tcl_words(text.replace("\r\n", "\n")):
        head = cmd[0][0]
        stack, net = stacks[-1], nets[-1]
        if head == "set" and len(cmd) >= 3:
            variables[cmd[1][0]] = stack[-1] if stack else None
        elif head == "push" and len(cmd) >= 2:
            ref = cmd[1][0]
            stack.append(variables.get(ref[1:]) if ref.startswith("$") else None)
        elif head == "version" and len(cmd) >= 2 and not app_version:
            app_version = "".join(w for w, _ in cmd[1:])  # "16.0 v4" -> "16.0v4" like nuke.NUKE_VERSION_STRING
        elif head == "end_group":
            if groups:
                nets.pop()
                stacks.pop()
                stacks[-1].append(groups.pop()["name"])
        elif len(cmd) == 2 and cmd[1][1] == "{" and re.match(r"^[A-Za-z_][\w.]*$", head):
            if head in N_SKIP_CLASSES:
                continue
            kind, item, n_inputs = _nk_node(head, cmd[1][0])
            if kind == "box":
                net["boxes"].append(item)
                continue
            if kind == "note":
                net["notes"].append(item)
                continue
            _unique(net, item)
            for idx in range(n_inputs):
                src = stack.pop() if stack else None
                if src is not None:
                    net["wires"].append({"src": src, "src_out": 0,
                                         "dst": item["name"], "dst_in": idx})
            net["nodes"].append(item)
            if head in N_GROUP_CLASSES:
                item["network"] = _empty_net()
                groups.append(item)
                nets.append(item["network"])
                stacks.append([])
            else:
                stack.append(item["name"])
    return {"schema": SCHEMA, "app": "nuke", "context": context,
            "app_version": app_version, "network": root}


# ---------------------------------------------------------------------------
# stats + markdown
# ---------------------------------------------------------------------------
def walk_nodes(net, path=""):
    for node in (net or {}).get("nodes", []):
        yield path, node
        if node.get("network"):
            for item in walk_nodes(node["network"], path + "/" + node["name"]):
                yield item


def graph_stats(graph):
    counts = {}
    total = 0
    for _, node in walk_nodes((graph or {}).get("network")):
        if node.get("kind") != "node":
            continue
        total += 1
        counts[node["type"]] = counts.get(node["type"], 0) + 1
    types = sorted(counts, key=lambda t: (-counts[t], t))[:40]
    return {"count": total, "types": types}


def format_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "expression" in value and len(value) <= 2:
        return "expr: %s" % value["expression"]
    return json.dumps(value, ensure_ascii=False)


def _md_network(net, path, out):
    out.append("### %s" % (path or "/"))
    out.append("")
    inputs = {}
    for w in net.get("wires", []):
        inputs.setdefault(w["dst"], []).append((str(w["dst_in"]), w["src"]))
    for node in net.get("nodes", []):
        if node.get("kind") != "node":
            continue
        head = "- **%s** `%s`" % (node["name"], node["type"])
        srcs = [s for _, s in sorted(inputs.get(node["name"], []))]
        srcs += ["(%s)" % e["from"] for e in node.get("ext_inputs", [])]
        if srcs:
            head += " ← " + ", ".join(srcs)
        if node.get("label"):
            head += "  — " + node["label"].replace("\n", " / ")
        out.append(head)
        for p in node.get("params", []):
            text = format_value(p["value"])
            if "\n" in text:
                out.append("    - `%s`:" % p["name"])
                out.append("")
                out.append("        ```")
                out.extend("        " + l for l in text.split("\n"))
                out.append("        ```")
            else:
                out.append("    - `%s`: %s" % (p["name"], text))
    for note in net.get("notes", []):
        out.append("- 📝 %s" % note.get("text", "").replace("\n", " / "))
    out.append("")
    for node in net.get("nodes", []):
        if node.get("network"):
            _md_network(node["network"], path + "/" + node["name"], out)


def network_markdown(graph):
    if not graph or not graph.get("network"):
        return ""
    stats = graph_stats(graph)
    out = ["## Network", "",
           "`%s %s` / context `%s` / %d nodes" % (
               graph.get("app", ""), graph.get("app_version", ""),
               graph.get("context", ""), stats["count"]), ""]
    _md_network(graph["network"], "", out)
    return "\n".join(out)
