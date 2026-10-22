# -*- coding: utf-8 -*-
"""Diagnose uniform / varying differences between an original VOP network and
a copy loaded from the Snippet Library. Run in Houdini's Python Shell:

    import sys; sys.path.append("C:/path/to/SnippetLibrary/tools")
    import diag_vop_storage
    diag_vop_storage.report("/stage/editmaterial6", "/stage/editmaterial7",
                            payload="B:/.../hajime_lop_test.json",   # optional: the snippet's .json
                            out_file="C:/temp/diag.txt")             # optional: also write to a file

For every VOP node under both roots it prints: shader language, parameter
VOP settings (parmuniform / parmscope / parmtype, at default or not), input
connections with the source node's output storage, and the node's own
connector storage types. With `payload` it also shows what the snippet file
stored for each node, so "lost on save" and "lost on load" can be told apart.
"""

import json

import hou


def _node_lines(node, saved):
    lines = []
    vop = isinstance(node, hou.VopNode)
    head = "%s  (%s)" % (node.path(), node.type().name())
    if vop:
        try:
            head += "  language=%s" % node.shaderLanguageName()
        except hou.Error:
            pass
    lines.append(head)
    if node.type().name() == "parameter":
        parms = {}
        for name in ("parmtype", "parmuniform", "parmscope", "exportparm", "useasparmdefiner", "usebound", "parmname"):
            p = node.parm(name)
            if p is not None:
                parms[name] = "%s%s" % (p.evalAsString() if name in ("parmtype", "parmscope", "parmname") else p.eval(),
                                        "" if p.isAtDefault() else "*")
        lines.append("    parms   : %s   (* = not default)" % parms)
    if vop:
        try:
            lines.append("    inputs  : %s" % list(zip(node.inputNames(), node.inputDataTypes())))
            lines.append("    outputs : %s" % list(zip(node.outputNames(), node.outputDataTypes())))
        except hou.Error as exc:
            lines.append("    types   : ERROR %s" % exc)
    conns = []
    for c in node.inputConnections():
        src = c.inputNode()
        try:
            src_type = src.outputDataTypes()[c.outputIndex()] if isinstance(src, hou.VopNode) else "?"
        except Exception:
            src_type = "?"
        conns.append("%s <- %s.%s (%s)" % (c.inputName(), src.name(), c.outputName(), src_type))
    if conns:
        lines.append("    wired   : %s" % "; ".join(conns))
    errs = node.errors()
    if errs:
        lines.append("    ERRORS  : %s" % list(errs))
    if saved is not None:
        lines.append("    saved   : parms=%s user_data=%s" % (saved.get("parms"), saved.get("user_data")))
    return lines


def _find_saved(payload, rel):
    """rel = path relative to the root node, e.g. 'skinBody_mtlSG/copicA1'."""
    if not payload:
        return None
    node = None
    for i, part in enumerate(rel.split("/")):
        container = payload if i == 0 else (node or {}).get("children") or {}
        node = container.get(part)
        if node is None:
            return None
    return node


def report(path_a, path_b, payload=None, out_file=None):
    data = None
    if payload:
        with open(payload, "r", encoding="utf-8") as f:
            data = json.load(f)
    lines = []
    for label, path in (("A (original)", path_a), ("B (loaded / copied)", path_b)):
        root = hou.node(path)
        lines.append("=" * 70)
        lines.append("%s = %s" % (label, path))
        lines.append("=" * 70)
        if root is None:
            lines.append("  not found")
            continue
        base = root.path() + "/"
        for node in [root] + list(root.allSubChildren()):
            if not isinstance(node, hou.VopNode):
                continue
            rel = node.path()[len(base):]
            saved = _find_saved(data, root.name() + ("/" + rel if rel else "")) if data else None
            if data and saved is None:
                # the snippet's top-level key may differ from the live node name
                for key in data:
                    saved = _find_saved(data, key + ("/" + rel if rel else ""))
                    if saved is not None:
                        break
            lines.extend(_node_lines(node, saved if data else None))
    text = "\n".join(lines)
    print(text)
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", out_file)
    return text
