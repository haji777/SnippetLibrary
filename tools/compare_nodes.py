# -*- coding: utf-8 -*-
"""Compare two Houdini networks node by node and print what differs.

Use it in the Python Shell of a running Houdini (or hython):

    import sys; sys.path.append("C:/path/to/SnippetLibrary/tools")
    import compare_nodes
    compare_nodes.compare("/stage/editmaterial1", "/stage/editmaterial7")

    # or write everything about one node to a JSON file to diff it elsewhere
    compare_nodes.dump("/stage/editmaterial1", "C:/temp/editmaterial1.json")

Both sides are walked recursively; nodes are matched by their path relative
to the root you pass in. For every node it compares: type (and HDA
definition), every parameter (value, raw expression, at-default, locked),
parameter templates (spare parameters, ranges, menus), input connections
by connector name, VOP connector names / data types, flags, user data,
data blocks, comment, cook errors. Position / colour / selection are ignored.
"""

import json
import os

import hou

IGNORE_PARMS = set()


# ---------------------------------------------------------------- describe
def _parm_info(parm):
    info = {}
    try:
        info["value"] = parm.eval()
    except hou.Error as exc:
        info["value"] = "EVAL ERROR: %s" % exc
    try:
        raw = parm.unexpandedString()
        if raw != str(info["value"]):
            info["raw"] = raw
    except hou.Error:
        pass
    try:
        if parm.keyframes():
            info["keyframes"] = len(parm.keyframes())
            try:
                info["expression"] = parm.expression()
            except hou.Error:
                pass
    except hou.Error:
        pass
    if parm.isLocked():
        info["locked"] = True
    if not parm.isAtDefault():
        info["non_default"] = True
    return info


def _vop_info(node):
    if not isinstance(node, hou.VopNode):
        return {}
    info = {}
    for name, fn in (("input_names", node.inputNames), ("output_names", node.outputNames),
                     ("input_types", node.inputDataTypes), ("output_types", node.outputDataTypes),
                     ("input_labels", node.inputLabels), ("output_labels", node.outputLabels)):
        try:
            info[name] = list(fn())
        except hou.Error:
            pass
    try:
        info["shader_name"] = node.shaderName()
    except hou.Error:
        pass
    return info


def describe(node):
    """Everything about one node that can influence its behaviour."""
    d = {"type": node.type().name(), "category": node.type().category().name()}
    defn = node.type().definition()
    if defn is not None:
        d["hda"] = defn.libraryFilePath()
    d["parms"] = {}
    for parm in node.parms():
        try:
            pname = parm.name()
            if pname in IGNORE_PARMS:
                continue
            d["parms"][pname] = _parm_info(parm)
        except hou.Error as exc:  # parameter interface regenerated while being read
            d.setdefault("parm_errors", []).append(str(exc))
    try:
        d["parm_templates"] = node.parmTemplateGroup().asCode()
    except hou.Error as exc:
        d["parm_templates"] = "ERROR: %s" % exc
    d["spare_parms"] = sorted(p.name() for p in node.spareParms())
    inputs = []
    try:
        for c in node.inputConnections():
            try:
                src = c.inputNode()
                inputs.append({"to": c.inputName() if hasattr(c, "inputName") else c.inputIndex(),
                               "from": src.name() if src else None,
                               "from_output": c.outputName() if hasattr(c, "outputName") else c.outputIndex()})
            except hou.Error as exc:  # connection vanished while being described (regenerating network)
                inputs.append({"error": str(exc)})
    except hou.Error as exc:
        inputs.append({"error": str(exc)})
    d["inputs"] = inputs
    d["vop"] = _vop_info(node)
    flags = {}
    for name in ("bypass", "display", "render", "template", "material", "debug", "lock",
                 "compress", "highlight", "audio", "export"):
        fn = getattr(node, "is%sFlagSet" % name.capitalize(), None)
        if fn is None:
            continue
        try:
            flags[name] = fn()
        except hou.Error:
            pass
    d["flags"] = flags
    d["user_data"] = dict(node.userDataDict())
    try:
        d["data_blocks"] = sorted(node.dataBlockKeys())
    except (hou.Error, AttributeError):
        pass
    d["comment"] = node.comment()
    try:
        d["errors"] = list(node.errors())
        d["warnings"] = list(node.warnings())
    except hou.Error:
        pass
    if node.isLockedHDA() if hasattr(node, "isLockedHDA") else False:
        d["locked_hda"] = True
    return d


def describe_tree(root):
    """{relative path: description} for root and everything inside it."""
    root = hou.node(root) if isinstance(root, str) else root
    out = {"": describe(root)}
    base = root.path() + "/"
    for node in root.allSubChildren():
        out[node.path()[len(base):]] = describe(node)
    return out


# ---------------------------------------------------------------- compare
def _diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append("%s.%s: only in B = %s" % (path, key, _short(b[key])))
            elif key not in b:
                out.append("%s.%s: only in A = %s" % (path, key, _short(a[key])))
            else:
                _diff(a[key], b[key], "%s.%s" % (path, key), out)
    elif a != b:
        out.append("%s:\n      A = %s\n      B = %s" % (path, _short(a), _short(b)))


def _short(value, limit=300):
    text = json.dumps(value, default=str, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[:limit] + "..."


def compare(path_a, path_b, show_same=False, redact_paths=True):
    """Print the differences between two networks. Returns the list of lines.
    File paths inside values are masked as <path:basename> unless redact_paths=False."""
    tree_a, tree_b = describe_tree(path_a), describe_tree(path_b)
    lines = []
    for rel in sorted(set(tree_a) | set(tree_b)):
        label = rel or "(root)"
        if rel not in tree_a:
            lines.append("[%s] only in B (%s)" % (label, tree_b[rel]["type"]))
            continue
        if rel not in tree_b:
            lines.append("[%s] only in A (%s)" % (label, tree_a[rel]["type"]))
            continue
        node_lines = []
        _diff(tree_a[rel], tree_b[rel], "", node_lines)
        if node_lines:
            lines.append("[%s] %s" % (label, tree_a[rel]["type"]))
            lines.extend("   " + l.lstrip(".") for l in node_lines)
        elif show_same:
            lines.append("[%s] identical" % label)
    header = "A = %s\nB = %s\n%s" % (path_a, path_b, "=" * 60)
    text = header + "\n" + ("\n".join(lines) if lines else "no differences found")
    if redact_paths:
        from diag_vop_storage import redact
        text = redact(text)
        lines = [redact(l) for l in lines]
    print(text)
    return lines


def dump(path, out_file):
    """Write describe_tree(path) as JSON (diff two of these with any text diff tool)."""
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(describe_tree(path), f, indent=1, ensure_ascii=False, default=str, sort_keys=True)
    print("wrote", os.path.abspath(out_file))
