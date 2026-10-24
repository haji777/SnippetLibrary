# -*- coding: utf-8 -*-
"""Round-trip check: build test networks in every context, save them the way
Snippet Library does (hou.data.itemsAsData + our extras -> JSON) and load them
back with our loader, then compare the copy with the original node by node.

Run headless:

    hython tools/roundtrip_check.py [report.txt]

Each case also reports what plain hou.data.createItemsFromData loses, so a
difference can be attributed to Houdini's recipe API or to our loader.
File paths in the report are masked (<path:basename>); node paths are kept.
"""
import contextlib
import io
import json
import os
import re
import sys

import hou

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from snippetlib import houdini_io  # noqa: E402
import compare_nodes  # noqa: E402
from diag_vop_storage import redact  # noqa: E402

# cook state, Houdini-internal user data, UI folder tabs, name-derived labels, temp dirs
NOISE = ("errors:", "warnings:", "parm_errors", "user_data.___", "user_data.sidefx::", "parms.stash.value",
         "parms.defaultlabel.", "savetodirectory_directory", "parms.objects.value",
         # values derived from the node's own path / name ($OS, opfullpath ...)
         "vop.shader_name", "parms.showlopstage.", "parms.rendergallerysource.", "parms.explicitcachename.",
         "parms.playfilesname.", "parms.dopoutput.")
NOISE_RE = r"parms\.(folder|stdswitcher)\d+\.|parms\.\w*resMenu\."  # tab indices, menu buttons


# ----------------------------------------------------------------- builders
def key(parm, values):
    for frame, value in values:
        parm.setKeyframe(hou.Keyframe(value, frame))


def build_sop(obj):
    geo = obj.createNode("geo", "sop_src")
    box = geo.createNode("box", "box1")
    key(box.parm("sizex"), [(1, 1.0), (24, 3.0)])
    box.setColor(hou.Color(1, 0.5, 0))
    box.setComment("keyframed size")
    box.setUserData("snippet_note", "hello")
    wr = geo.createNode("attribwrangle", "wrangle1")
    wr.setInput(0, box)
    wr.parm("snippet").set('@P.y += ch("amp") * @ptnum;')
    ptg = wr.parmTemplateGroup()
    ptg.append(hou.FloatParmTemplate("amp", "Amp", 1, default_value=(0.25,), min=0, max=2))
    wr.setParmTemplateGroup(ptg)
    wr.parm("amp").set(0.5)
    dot = geo.createNetworkDot()
    dot.setInput(wr)
    py = geo.createNode("python", "python1")
    py.setInput(0, dot)
    py.parm("python").set("node = hou.pwd()\ngeo = node.geometry()\ngeo.addAttrib(hou.attribType.Point, 'foo', 1.0)\n")
    py.bypass(True)
    sc = geo.createNode("scatter", "scatter1")
    sc.setInput(0, py)
    sc.parm("npts").setExpression('ch("../box1/sizex") * 100')
    ac = geo.createNode("attribcreate", "attribcreate1")
    ac.setInput(0, sc)
    ac.parm("numattr").set(2)
    ac.parm("name1").set("mass")
    ac.parm("value1v1").set(2.5)
    ac.parm("name2").set("tag")
    ac.parm("type2").set("index")  # string attribute
    ac.parm("string2").set("abc")
    sw = geo.createNode("switch", "switch1")
    sw.setInput(0, ac)
    sw.setInput(1, box)
    sw.parm("input").setExpression("$F % 2")
    st = geo.createNode("stash", "stash1")
    st.setInput(0, sw)
    st.parm("stashinput").pressButton()
    st.setInput(0, None)
    lk = geo.createNode("null", "hardlock1")
    lk.setInput(0, sw)
    lk.setHardLocked(True)
    lk.setTemplateFlag(True)
    sub = geo.createNode("subnet", "subnet1")
    sub.setInput(0, sw)
    inner = sub.createNode("sphere", "sphere1")
    inner.setInput(0, sub.indirectInputs()[0])
    mat = geo.createNode("material", "material1")
    mat.setInput(0, sub)
    mat.parm("shop_materialpath1").set("/mat/principledshader1")
    bb, be = geo.createNode("block_begin", "block_begin1"), geo.createNode("block_end", "block_end1")
    bb.setInput(0, mat)
    bb.parm("method").set("feedback")
    bb.parm("blockpath").set("../block_end1")
    be.setInput(0, bb)
    be.parm("blockpath").set("../block_begin1")
    be.parm("templatepath").set("../block_begin1")
    be.parm("iterations").set(3)
    be.setDisplayFlag(True)
    be.setRenderFlag(True)
    pig = geo.createNode("testgeometry_pighead", "pighead_edited")
    pig.allowEditingOfContents()
    for child in pig.children():
        if child.type().name() == "xform" or child.type().name().startswith("xform"):
            child.parm("scale").set(2.0)
            break
    box_nb = geo.createNetworkBox("box_notes")
    box_nb.setComment("inside the box")
    box_nb.addItem(sc)
    box_nb.addItem(ac)
    note = geo.createStickyNote("note1")
    note.setText("sticky text")
    geo.layoutChildren()
    return geo


def build_obj(obj):
    net = obj.createNode("subnet", "obj_src")
    null = net.createNode("null", "null1")
    key(null.parm("tx"), [(1, 0.0), (24, 5.0)])
    geo = net.createNode("geo", "geo1")
    geo.setInput(0, null)
    geo.parm("ty").setExpression('ch("../null1/tx") * 2')
    geo.createNode("box")
    cam = net.createNode("cam", "cam1")
    cam.parm("lookatpath").set("../null1")
    cam.parm("focal").set(35)
    light = net.createNode("hlight", "light1")
    light.parm("light_type").set("distant")
    light.parm("light_intensity").set(3)
    net.layoutChildren()
    return net


def build_vop(obj):
    net = obj.createNode("matnet", "mat_src")
    pr = net.createNode("principledshader::2.0", "principledshader1")
    pr.parm("basecolorr").set(0.2)
    pr.parm("basecolor_useTexture").set(1)
    pr.parm("basecolor_texture").set("$HIP/tex/color.<UDIM>.rat")
    mb = net.createNode("materialbuilder", "vexbuilder1")
    inl = mb.createNode("inline", "inline1")
    inl.parm("code").set("$out = $a * 2.0;")
    bnd = mb.createNode("bind", "bind1")
    bnd.parm("parmname").set("Cd")
    bnd.parm("parmtype").set("color")
    # MaterialX subnet holding one VEX parameter next to MaterialX ones (the
    # Edit Material situation that broke mtlximage before languages were recorded)
    mx = net.createNode("subnet", "mtlx_mixed")
    mx.setShaderLanguageName("MaterialX")
    surf = mx.createNode("mtlxstandard_surface", "surface")
    img = mx.createNode("mtlximage", "image")
    img.parm("signature").set("color3")
    mul = mx.createNode("mtlxmultiply", "mul")
    mul.parm("signature").set("color3")
    file_parm = mx.createNode("parameter", "file_parm")
    file_parm.parm("parmname").set("file")
    file_parm.parm("parmtype").set("string")
    file_parm.setShaderLanguageName("MaterialX")
    vex_parm = mx.createNode("parameter", "vex_gain")
    vex_parm.parm("parmname").set("gain")
    vex_parm.parm("parmtype").set("float")
    vex_parm.setShaderLanguageName("VEX")
    gpv = mx.createNode("mtlxgeompropvalue", "gpv")
    gpv.parm("signature").set("float")
    img.setNamedInput("file", file_parm, 0)
    mul.setNamedInput("in1", img, "out")
    mul.setNamedInput("in2", vex_parm, 0)
    surf.setNamedInput("base_color", mul, "out")
    surf.setNamedInput("specular_roughness", gpv, "out")
    for n in (net, mb, mx):
        n.layoutChildren()
    return net


def build_lop(obj):
    net = obj.createNode("lopnet", "lop_src")
    sph = net.createNode("sphere", "sphere1")
    xf = net.createNode("xform", "xform1")
    xf.setInput(0, sph)
    key(xf.parm("tx"), [(1, 0.0), (24, 2.0)])
    ml = net.createNode("materiallibrary", "materiallibrary1")
    ml.setInput(0, xf)
    surf = ml.createNode("mtlxstandard_surface", "mtlxsurface")
    img = ml.createNode("mtlximage", "mtlximage1")
    img.parm("file").set("$HIP/tex/albedo.exr")
    surf.setNamedInput("base_color", img, "out")
    ml.parm("fillmaterials").pressButton()
    am = net.createNode("assignmaterial", "assignmaterial1")
    am.setInput(0, ml)
    am.parm("primpattern1").set("/sphere1")
    am.parm("matspecpath1").set("/materials/mtlxsurface")
    sm = net.createNode("sopmodify", "sopmodify1")
    sm.setInput(0, am)
    sm.parm("primpattern").set("/sphere1")
    inner = sm.node("modify/modify")  # the editable subnet inside the locked HDA
    if inner is not None:
        out = [c for c in inner.children() if c.type().name() == "output"]
        col = inner.createNode("color", "color1")
        try:
            if out and out[0].inputs():
                col.setInput(0, out[0].inputs()[0])
                out[0].setInput(0, col)
        except hou.Error:
            pass  # wiring inside the editable network is version dependent; the node itself is the test
        col.parm("colorr").set(0.9)
    ps = net.createNode("pythonscript", "pythonscript1")
    ps.setInput(0, sm)
    ps.parm("python").set("node = hou.pwd()\nstage = node.editableStage()\n")
    krp = net.createNode("karmarenderproperties", "karmarenderproperties1")
    krp.setInput(0, ps)
    krp.parm("resolutionx").set(1280)
    rop = net.createNode("usdrender_rop", "usdrender_rop1")
    rop.setInput(0, krp)
    net.layoutChildren()
    return net


def build_cop(obj):
    net = obj.createNode("copnet", "cop_src")
    const = net.createNode("constant", "constant1")
    ramp = net.createNode("ramp", "ramp1")
    blur = net.createNode("blur", "blur1")
    blur.setInput(0, const)
    blur.parm("size").set(10) if blur.parm("size") else None
    blend = net.createNode("blend", "blend1")
    blend.setInput(0, blur)
    blend.setInput(1, ramp)
    wr = net.createNode("wrangle", "wrangle1")
    wr.setInput(0, blend)
    if wr.parm("snippet"):
        wr.parm("snippet").set("@C *= 0.5;")
    out = net.createNode("output", "output1")
    out.setInput(0, wr)
    net.layoutChildren()
    return net


def build_dop(obj):
    net = obj.createNode("dopnet", "dop_src")
    out = net.node("output")
    po = net.createNode("popobject", "popobject1")
    src = net.createNode("popsource", "popsource1")
    src.parm("constantrate").set(500) if src.parm("constantrate") else None
    grav = net.createNode("gravity", "gravity1")
    grav.parm("forcey").set(-4.5)
    rbd = net.createNode("rigidbodysolver", "rigidbodysolver1")
    merge = net.createNode("merge", "merge1")
    grav.setInput(0, po)
    rbd.setInput(0, grav)
    merge.setInput(0, rbd)
    merge.setInput(1, src)
    if out is not None:
        out.setInput(0, merge)
    net.layoutChildren()
    return net


def build_chop(obj):
    net = obj.createNode("chopnet", "chop_src")
    wave = net.createNode("wave", "wave1")
    wave.parm("period").set(2)
    noise = net.createNode("noise", "noise1")
    math = net.createNode("math", "math1")
    math.setInput(0, wave)
    math.setInput(1, noise)
    null = net.createNode("null", "null1")
    null.setInput(0, math)
    null.setExportFlag(True)
    net.layoutChildren()
    return net


def build_top(obj):
    net = obj.createNode("topnet", "top_src")
    gen = net.createNode("genericgenerator", "genericgenerator1")
    gen.parm("itemcount").set(5) if gen.parm("itemcount") else None
    py = net.createNode("pythonscript", "pythonscript1")
    py.setInput(0, gen)
    py.parm("script").set("print(work_item.index)\n") if py.parm("script") else None
    fp = net.createNode("filepattern", "filepattern1")
    fp.parm("pattern").set("$HIP/geo/*.bgeo.sc") if fp.parm("pattern") else None
    rf = net.createNode("ropfetch", "ropfetch1")
    rf.setInput(0, py)
    net.layoutChildren()
    return net


def build_rop(obj):
    net = obj.createNode("ropnet", "rop_src")
    g = net.createNode("geometry", "geometry1")
    g.parm("soppath").set("/obj/sop_src/block_end1")
    g.parm("sopoutput").set("$HIP/geo/$HIPNAME.$F4.bgeo.sc")
    g.parm("trange").set(1)
    k = net.createNode("karma", "karma1")
    k.parm("picture").set("$HIP/render/$HIPNAME.$F4.exr")
    m = net.createNode("merge", "merge1")
    m.setInput(0, g)
    m.setInput(1, k)
    f = net.createNode("fetch", "fetch1")
    f.parm("source").set("../geometry1")
    net.layoutChildren()
    return net


CASES = [("sop", build_sop), ("obj", build_obj), ("vop", build_vop), ("lop", build_lop),
         ("cop", build_cop), ("dop", build_dop), ("chop", build_chop), ("top", build_top), ("rop", build_rop)]


# ------------------------------------------------------------------ checks
def geometry_counts(parent):
    """Point counts of nodes that carry geometry in the file itself (stash, hard lock)."""
    out = {}
    for node in parent.allSubChildren():
        if not isinstance(node, hou.SopNode):
            continue
        if node.type().name() == "stash" or node.isHardLocked():
            try:
                g = node.geometry()
                out[node.path()[len(parent.path()) + 1:]] = g.intrinsicValue("pointcount") if g else None
            except hou.Error as exc:
                out[node.path()[len(parent.path()) + 1:]] = "ERROR %s" % exc
    return out


def roundtrip(src, loader):
    """Save src's contents like the library does, load them into a sibling of the same type."""
    items = list(src.allItems())
    with houdini_io.recipe_workarounds():
        data = hou.data.itemsAsData(items, anchor_position=houdini_io._anchor(items))
    houdini_io._record_extras(data, src)
    data = json.loads(json.dumps(data))  # exactly what the .json file carries
    dst = src.parent().createNode(src.type().name(), src.name().replace("_src", "_" + loader))
    for child in dst.children():  # topnet / dopnet create a default scheduler / output: the
        child.destroy()           # loaded ones would be renamed and the compare would look at the wrong node
    if loader == "ours":
        houdini_io._create_items(dst, data, hou.Vector2(0, 0))
    else:
        hou.data.createItemsFromData(dst, data)
    return dst, data


def inside_locked_hda(root, rel):
    """True when rel (relative to root) lies under a locked asset and is not an editable node."""
    node = root.node(rel)
    parts = rel.split("/")
    for i in range(1, len(parts)):
        anc = root.node("/".join(parts[:i]))
        if anc is not None and anc.isLockedHDA():
            return node is None or not node.isEditable()
    return False


def compare(src, dst):
    with contextlib.redirect_stdout(io.StringIO()):
        lines = compare_nodes.compare(src.path(), dst.path(), redact_paths=False)
    real, noise = [], []
    for line in lines:
        head = line.splitlines()[0] if line else ""
        is_noise = any(n in head for n in NOISE) or re.search(NOISE_RE, head)
        if not is_noise and "only in" in head and head.startswith("["):
            # the inside of a locked HDA is built lazily (on first cook): not saved data
            rel = head[1:head.index("]")]
            is_noise = inside_locked_hda(src, rel) or inside_locked_hda(dst, rel)
        (noise if is_noise else real).append(line)
    # node header lines whose every detail was noise
    kept = []
    for i, line in enumerate(real):
        if line.startswith("[") and "only in" not in line and (i + 1 >= len(real) or real[i + 1].startswith("[")):
            noise.append(line)
        else:
            kept.append(line)
    return kept, noise


def main(report_path=None):
    hou.hipFile.clear(suppress_save_prompt=True)
    obj = hou.node("/obj")
    hou.setUpdateMode(hou.updateMode.Manual)
    report = ["Houdini %s round-trip check" % hou.applicationVersionString(), ""]
    summary = []
    for name, build in CASES:
        try:
            src = build(obj)
        except Exception as exc:  # a builder that fails on this version is reported, not fatal
            report += ["### %s: BUILD FAILED: %s" % (name, exc), ""]
            summary.append((name, "build failed"))
            continue
        block = ["### %s  (%s, %d items)" % (name, src.path(), len(src.allItems()))]
        verdict = []
        for loader in ("ours", "hou.data"):
            try:
                dst, data = roundtrip(src, loader)
            except Exception as exc:
                block.append("  [%s] LOAD FAILED: %s" % (loader, exc))
                verdict.append("%s: load failed" % loader)
                continue
            real, noise = compare(src, dst)
            geo_a, geo_b = geometry_counts(src), geometry_counts(dst)
            block.append("  [%s] %d differences, %d cook-state lines ignored" % (loader, len(real), len(noise)))
            for line in real:
                block.append("     " + line.replace("\n", "\n     "))
            if geo_a != geo_b:
                block.append("     geometry held by node: A=%s B=%s" % (geo_a, geo_b))
                real.append("geometry")
            verdict.append("%s: %s" % (loader, "OK" if not real else "%d diffs" % len(real)))
        report += block + [""]
        summary.append((name, ", ".join(verdict)))
    # the whole save path once (library files, graph for the viewer), re-loaded from the .json
    report += ["### save_items -> payload file -> loader"]
    import tempfile
    import shutil
    from snippetlib import core
    tmp = tempfile.mkdtemp(prefix="snippetlib_rt_")
    os.environ[core.ENV_ROOT] = tmp
    for name, _ in CASES:
        src = obj.node("%s_src" % name)
        if src is None:
            continue
        try:
            info = houdini_io.save_items(list(src.allItems()), "rt %s" % name, "round trip", ["rt"], root=tmp)
            payload = core.read_json(info["payload"])
            dst = obj.createNode(src.type().name(), "%s_file" % name)
            for child in dst.children():
                child.destroy()
            houdini_io._create_items(dst, payload, hou.Vector2(0, 0))
            real, noise = compare(src, dst)
            files = sorted(os.listdir(info["dir"]))
            graph = [f for f in files if f.endswith(core.GRAPH_EXT)]
            nodes = len((core.read_json(os.path.join(info["dir"], graph[0])) or {}).get("network", {}).get("nodes", [])) if graph else 0
            report.append("  %-5s saved + reloaded: %s | files: %d, viewer graph nodes: %d" % (
                name, "OK" if not real else "%d diffs" % len(real), len(files), nodes))
            for line in real:
                report.append("     " + line.replace("\n", "\n     "))
            summary.append((name + "/file", "OK" if not real else "%d diffs" % len(real)))
        except Exception as exc:
            report.append("  %-5s SAVE/RELOAD FAILED: %s" % (name, exc))
            summary.append((name + "/file", "failed"))
    shutil.rmtree(tmp, ignore_errors=True)
    report.append("")
    report += ["### summary"] + ["  %-10s %s" % s for s in summary]
    text = redact("\n".join(report))
    print(text)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("\nwrote", report_path)
    return summary


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
