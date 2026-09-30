/* Node network renderer (SVG). Reads the neutral graph.json written by snippetlib/graph.py */
"use strict";

const SVGNS = "http://www.w3.org/2000/svg";

function sv(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") el.textContent = v;
    else el.setAttribute(k, v);
  }
  for (const kid of kids) if (kid) el.appendChild(kid);
  return el;
}

function rgbCss(c, fallback) {
  if (!c || c.length < 3) return fallback;
  return `rgb(${c.slice(0, 3).map(v => Math.round(Math.max(0, Math.min(1, v)) * 255)).join(",")})`;
}

function luminance(c) {
  return c ? 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] : 0.5;
}

/* Nuke's default tile colors by node family (used when the .nk has no tile_color) */
const NUKE_FAMILIES = [
  [/^(Read|Write|Constant|CheckerBoard|ColorBars|ColorWheel|Viewer)/, [0.78, 0.78, 0.62]],
  [/^(Merge|Keymix|AddMix|Dissolve|Switch|ContactSheet|CopyRectangle|Blend)/, [0.30, 0.37, 0.78]],
  [/^(Copy|Shuffle|ChannelMerge|AddChannels|Remove|Premult|Unpremult)/, [0.62, 0.24, 0.39]],
  [/^(Grade|ColorCorrect|ColorLookup|HueCorrect|HueShift|Saturation|Exposure|Gamma|Clamp|Invert|Multiply|Add|Colorspace|OCIO|Expression|Log2Lin|Histogram)/, [0.48, 0.66, 1.0]],
  [/^(Blur|Defocus|ZDefocus|Sharpen|Soften|Glow|Erode|Dilate|FilterErode|EdgeBlur|EdgeDetect|Median|Denoise|VectorBlur|MotionBlur|God|Convolve|Emboss|Matrix|DirBlur)/, [0.80, 0.50, 0.31]],
  [/^(Transform|Reformat|Crop|CornerPin|Tracker|Card3D|Mirror|Position|SplineWarp|GridWarp|IDistort|STMap|LensDistortion|Stabilize)/, [0.65, 0.48, 0.67]],
  [/^(Roto|RotoPaint|Bezier|Noise|Radial|Ramp|Rectangle|Text|Grain|Flare|Sparkles|Grid|LightWrap)/, [0.35, 0.72, 0.35]],
  [/^(Keyer|Keylight|Primatte|IBK|Ultimatte|Difference|HueKeyer|ChromaKeyer|Cryptomatte)/, [0.20, 0.78, 0.25]],
  [/^(FrameHold|TimeOffset|Retime|OFlow|Kronos|TimeWarp|FrameRange|TimeEcho|FrameBlend|AppendClip|TimeClip)/, [0.69, 0.64, 0.37]],
  [/^(Scene|Camera|Axis|Light|ScanlineRender|RayRender|ReadGeo|WriteGeo|Card|Sphere|Cube|Cylinder|Geo|TransformGeo|MergeGeo|ApplyMaterial|Project3D|UVProject|Phong|Diffuse|Specular|DirectLight|Spotlight|Environment)/, [0.80, 0.33, 0.33]],
  [/^Deep/, [0.38, 0.38, 0.62]],
  [/^Particle/, [0.75, 0.55, 0.75]],
  [/^(Group|LiveGroup|Gizmo|Input|Output|NoOp)/, [0.60, 0.60, 0.60]],
];
const NUKE_AB = /^(Merge|Copy|Keymix|AddMix|ChannelMerge|CopyBBox|MergeExpression|Dissolve|ZMerge)/;

/* Houdini nodes left at the default grey get a soft tint per node type, so the
   same type reads as the same hue (the viewer has no icons to tell them apart). */
function houdiniColor(node) {
  const c = node.color;
  if (c && !(Math.abs(c[0] - 0.8) < 0.02 && Math.abs(c[1] - 0.8) < 0.02 && Math.abs(c[2] - 0.8) < 0.02)) return c;
  let n = 0;
  for (const ch of node.type.split("::")[0]) n = (n * 33 + ch.charCodeAt(0)) >>> 0;
  const hue = n % 360, s = 0.38, l = 0.74, a = s * Math.min(l, 1 - l);
  const f = k => l - a * Math.max(-1, Math.min((k + hue / 30) % 12 - 3, 9 - (k + hue / 30) % 12, 1));
  return [f(0), f(8), f(4)];
}

function nodeColor(node, isNuke) {
  return isNuke ? node.color || nukeColor(node.type) : houdiniColor(node);
}

function nukeColor(type) {
  for (const [re, c] of NUKE_FAMILIES) if (re.test(type)) return c;
  return [0.66, 0.66, 0.66];
}

class GraphView {
  constructor(host, graph, onSelect) {
    this.host = host;
    this.graph = graph;
    this.isNuke = graph.app === "nuke";
    this.onSelect = onSelect;
    this.stack = [{ name: "/", net: graph.network }];
    this.selected = null;
    this.t = { x: 0, y: 0, k: 1 };

    this.crumbs = document.createElement("div");
    this.crumbs.className = "crumbs";
    this.svg = sv("svg", { class: "graph" + (this.isNuke ? " nuke" : " houdini") });
    this.svg.appendChild(sv("defs", {},
      sv("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 5, refY: 5, markerWidth: 9, markerHeight: 9, orient: "auto-start-reverse" },
        sv("path", { d: "M1 1 L9 5 L1 9 z", class: "arrowhead" }))));
    this.root = sv("g");
    this.svg.appendChild(this.root);
    const tools = document.createElement("div");
    tools.className = "graphtools";
    tools.innerHTML = '<button data-a="up" title="上の階層へ (U)">▲ Up</button><button data-a="fit" title="全体表示 (F)">Fit</button>';
    tools.addEventListener("click", e => {
      const a = e.target.dataset.a;
      if (a === "fit") this.fit();
      if (a === "up") this.up();
    });
    host.append(this.crumbs, this.svg, tools);
    this._bindPanZoom();
    this.render();
    requestAnimationFrame(() => this.fit());
  }

  get net() { return this.stack[this.stack.length - 1].net; }
  get path() { return this.stack.slice(1).map(s => s.name).join("/"); }

  dive(node) {
    if (!node.network) return;
    this.stack.push({ name: node.name, net: node.network });
    this.select(null);
    this.render();
    this.fit();
  }

  up(level) {
    if (this.stack.length < 2) return;
    this.stack.length = level === undefined ? this.stack.length - 1 : level + 1;
    this.select(null);
    this.render();
    this.fit();
  }

  select(node) {
    this.selected = node;
    this.onSelect(node, this.path);
    this.render();
  }

  selectByName(name) {
    const node = this.net.nodes.find(n => n.name === name);
    if (node) this.select(node);
  }

  // ---------------------------------------------------------------- drawing
  /* Ports are indices, or names in COP / VOP networks: resolve both to slots. */
  _ports(net) {
    const P = {};
    const get = name => P[name] || (P[name] = { ins: [], outs: [], nIn: 0, nOut: 0 });
    const slot = (list, port) => {
      if (typeof port === "number") return port;
      let i = list.indexOf(port);
      if (i < 0) { list.push(port); i = list.length - 1; }
      return i;
    };
    for (const n of net.nodes) {
      const p = get(n.name);
      p.ins = [...(n.in_names || [])];
      p.outs = [...(n.out_names || [])];
    }
    for (const w of net.wires) {
      const a = get(w.src), b = get(w.dst);
      w._o = slot(a.outs, w.src_out);
      w._i = slot(b.ins, w.dst_in);
      a.nOut = Math.max(a.nOut, w._o + 1);
      b.nIn = Math.max(b.nIn, w._i + 1);
    }
    for (const n of net.nodes) {
      const p = get(n.name);
      for (const e of n.ext_inputs || []) { e._i = slot(p.ins, e.dst_in); p.nIn = Math.max(p.nIn, e._i + 1); }
      if (this.flow === "h") { p.nIn = Math.max(p.nIn, p.ins.length, 1); p.nOut = Math.max(p.nOut, p.outs.length); }
      else if (/^(merge|switch)/.test(n.type)) p.nIn = 1;
      else p.nIn = Math.max(p.nIn, Math.min(n.n_in || 1, 4), 1);
      p.nOut = Math.max(p.nOut, 1);
    }
    return P;
  }

  _inPos(n, idx, ports) {
    if (n.kind !== "node") return [n.x + n.w / 2, n.y + n.h / 2];
    const count = ports[n.name].nIn, f = (Math.min(idx, count - 1) + 1) / (count + 1);
    return this.flow === "h" ? [n.x, n.y + n.h * f] : [n.x + n.w * f, n.y];
  }

  _outPos(n, idx, ports) {
    if (n.kind !== "node") return [n.x + n.w / 2, n.y + n.h / 2];
    const count = ports[n.name].nOut, f = (Math.min(idx, count - 1) + 1) / (count + 1);
    return this.flow === "h" ? [n.x + n.w, n.y + n.h * f] : [n.x + n.w * f, n.y + n.h];
  }

  render() {
    const net = this.net, g = this.root;
    while (g.firstChild) g.removeChild(g.firstChild);
    const byName = Object.fromEntries(net.nodes.map(n => [n.name, n]));
    // Copernicus / VOP networks run left-to-right (big tiles, named ports). Decided per
    // network because e.g. a COP "sopimport" contains a vertical SOP network.
    this.flow = this.isNuke ? "v"
      : net.nodes.some(n => n.kind === "node" && n.h > 80) || net.wires.some(w => typeof w.dst_in === "string") ? "h" : "v";
    const ports = this._ports(net);
    const sel = this.selected && this.selected.name;

    for (const b of net.boxes || []) {
      const col = rgbCss(b.color, "rgb(140,140,150)");
      g.appendChild(sv("rect", { x: b.x, y: b.y, width: b.w, height: b.h, rx: 6, fill: col, "fill-opacity": 0.16, stroke: col, "stroke-opacity": 0.55 }));
      g.appendChild(sv("text", { x: b.x + 10, y: b.y + 22, class: "boxtitle", fill: col, text: b.title || "" }));
    }
    for (const note of net.notes || []) {
      const fo = sv("foreignObject", { x: note.x, y: note.y, width: note.w, height: note.h });
      const div = document.createElement("div");
      div.className = "sticky";
      div.style.background = rgbCss(note.color, "rgb(255,247,133)");
      div.textContent = note.text || "";
      fo.appendChild(div);
      g.appendChild(fo);
    }

    // wires
    const wires = sv("g", { class: "wires" });
    for (const w of net.wires) {
      const a = byName[w.src], b = byName[w.dst];
      if (!a || !b) continue;
      const hot = sel && (w.src === sel || w.dst === sel);
      if (this.isNuke) {
        const [x1, y1] = [a.x + a.w / 2, a.y + a.h / 2], [x2, y2] = [b.x + b.w / 2, b.y + b.h / 2];
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        wires.appendChild(sv("path", { d: `M${x1} ${y1} L${mx} ${my} L${x2} ${y2}`, class: "wire" + (hot ? " hot" : ""), "marker-mid": "url(#arrow)" }));
        if (b.kind === "node" && (ports[b.name].nIn > 1 || w.dst_in > 0)) {
          const lab = NUKE_AB.test(b.type) ? (["B", "A", "mask"][w.dst_in] || "A" + w.dst_in) : String(w.dst_in);
          const d = Math.hypot(x2 - x1, y2 - y1) || 1, r = Math.min(d * 0.4, b.h / 2 + 16 + Math.abs(x2 - x1) / d * b.w * 0.45);
          wires.appendChild(sv("text", { x: x2 - (x2 - x1) / d * r, y: y2 - (y2 - y1) / d * r - 3, class: "inlabel", "text-anchor": "middle", text: lab }));
        }
      } else {
        const [x1, y1] = this._outPos(a, w._o, ports), [x2, y2] = this._inPos(b, w._i, ports);
        const dx = this.flow === "h" ? Math.max(40, Math.abs(x2 - x1) * 0.45) : 0;
        const dy = this.flow === "h" ? 0 : Math.max(28, Math.abs(y2 - y1) * 0.45);
        wires.appendChild(sv("path", { d: `M${x1} ${y1} C${x1 + dx} ${y1 + dy} ${x2 - dx} ${y2 - dy} ${x2} ${y2}`, class: "wire" + (hot ? " hot" : "") }));
      }
    }
    g.appendChild(wires);

    // nodes
    for (const n of net.nodes) {
      const ng = sv("g", { class: "node " + n.kind + (n.name === sel ? " selected" : "") + (n.flags && n.flags.bypass ? " bypassed" : "") });
      ng.addEventListener("click", e => { e.stopPropagation(); if (!this._dragged) this.select(n); });
      ng.addEventListener("dblclick", e => { e.stopPropagation(); this.dive(n); });
      if (n.kind === "dot") {
        ng.appendChild(sv("circle", { cx: n.x + n.w / 2, cy: n.y + n.h / 2, r: Math.max(6, n.w / 2), class: "dot", fill: rgbCss(n.color, "rgb(170,170,180)") }));
      } else if (n.kind === "input") {
        ng.appendChild(sv("rect", { x: n.x, y: n.y, width: n.w, height: n.h, rx: n.h / 2, class: "indirect" }));
        ng.appendChild(sv("text", { x: n.x + n.w / 2, y: n.y + n.h / 2 + 4, "text-anchor": "middle", class: "indirect-t", text: "in " + n.name }));
      } else {
        this._drawNode(ng, n, ports);
      }
      g.appendChild(ng);
    }
    this._renderCrumbs();
  }

  _drawNode(ng, n, ports) {
    const color = nodeColor(n, this.isNuke);
    const fill = rgbCss(color);
    const flags = n.flags || {};
    const horiz = this.flow === "h";
    for (const e of n.ext_inputs || []) {
      const [x, y] = this.isNuke ? [n.x + n.w / 2, n.y] : this._inPos(n, e._i, ports);
      if (horiz) {
        ng.appendChild(sv("path", { d: `M${x} ${y} L${x - 34} ${y}`, class: "wire ext" }));
        ng.appendChild(sv("text", { x: x - 38, y: y + 3, "text-anchor": "end", class: "extlabel", text: e.from }));
      } else {
        ng.appendChild(sv("path", { d: `M${x} ${y} L${x} ${y - 26}`, class: "wire ext" }));
        ng.appendChild(sv("text", { x: x + 5, y: y - 16, class: "extlabel", text: e.from }));
      }
    }
    if (n.network) ng.appendChild(sv("rect", { x: n.x + 4, y: n.y + 4, width: n.w, height: n.h, rx: 6, fill, opacity: 0.45 }));
    ng.appendChild(sv("rect", { x: n.x, y: n.y, width: n.w, height: n.h, rx: this.isNuke ? 4 : 6, fill, class: "body" }));
    if (!this.isNuke) {
      const seg = Math.min(16, n.w * 0.14);
      // flags: end caps on SOP style nodes, a strip along the bottom of COP tiles
      const flag = (slot, fill) => ng.appendChild(horiz
        ? sv("rect", { x: slot < 0 ? n.x + 6 : n.x + n.w - 6 - seg * 2 * (slot + 1), y: n.y + n.h - 10, width: seg * 2 - 3, height: 6, rx: 3, fill })
        : sv("rect", { x: slot < 0 ? n.x : n.x + n.w - seg * (slot + 1), y: n.y, width: seg, height: n.h, rx: 3, fill }));
      if (flags.bypass) flag(-1, "#f2c230");
      if (flags.template) flag(2, "#d66ad6");
      if (flags.render) flag(1, "#8a5cf0");
      if (flags.display) flag(0, "#2f9bff");
      const P = ports[n.name];
      for (let i = 0; i < P.nIn; i++) {
        const [x, y] = this._inPos(n, i, ports);
        ng.appendChild(sv("circle", { cx: x, cy: y, r: horiz ? 4 : 3.2, class: "port" }));
        if (horiz && P.ins[i]) ng.appendChild(sv("text", { x: x + 8, y: y + 3, class: "portname", text: P.ins[i] }));
      }
      for (let i = 0; i < (horiz ? P.nOut : 1); i++) {
        const [x, y] = this._outPos(n, i, ports);
        ng.appendChild(sv("circle", { cx: x, cy: y, r: horiz ? 4 : 3.2, class: "port" }));
        if (horiz && P.outs[i]) ng.appendChild(sv("text", { x: x - 8, y: y + 3, "text-anchor": "end", class: "portname", text: P.outs[i] }));
      }
      if (horiz) {  // Copernicus tile: type inside, name below
        ng.appendChild(sv("text", { x: n.x + n.w / 2, y: n.y + 17, "text-anchor": "middle", class: "tiletype", text: n.type_label || n.type }));
        ng.appendChild(sv("text", { x: n.x + n.w / 2, y: n.y + n.h + 16, "text-anchor": "middle", class: "hname", text: n.name }));
        if (n.label) ng.appendChild(sv("text", { x: n.x + n.w / 2, y: n.y + n.h + 32, "text-anchor": "middle", class: "hcomment", text: n.label.split("\n")[0] }));
      } else {
        ng.appendChild(sv("text", { x: n.x + n.w + 9, y: n.y + n.h / 2 + 1, class: "hname", text: n.name }));
        ng.appendChild(sv("text", { x: n.x + n.w + 9, y: n.y + n.h / 2 + 15, class: "htype", text: n.type_label || n.type }));
        if (n.label) ng.appendChild(sv("text", { x: n.x + n.w + 9, y: n.y + n.h / 2 - 14, class: "hcomment", text: n.label.split("\n")[0] }));
      }
    } else {
      const dark = luminance(color) > 0.45;
      ng.appendChild(sv("text", { x: n.x + n.w / 2, y: n.y + n.h / 2 + 4, "text-anchor": "middle", class: "nname", fill: dark ? "#16171c" : "#f2f2f5", text: n.name }));
      (n.label || "").split("\n").slice(0, 3).forEach((line, i) =>
        ng.appendChild(sv("text", { x: n.x + n.w / 2, y: n.y + n.h + 13 + i * 12, "text-anchor": "middle", class: "nlabel", text: line })));
      if (flags.bypass) ng.appendChild(sv("path", { d: `M${n.x} ${n.y} L${n.x + n.w} ${n.y + n.h} M${n.x + n.w} ${n.y} L${n.x} ${n.y + n.h}`, class: "disabled-x" }));
    }
    const count = (n.params || []).length;
    if (count) {
      ng.appendChild(sv("circle", { cx: n.x + (this.isNuke ? n.w : 0), cy: n.y, r: 8, class: "pbadge" }));
      ng.appendChild(sv("text", { x: n.x + (this.isNuke ? n.w : 0), y: n.y + 3.5, "text-anchor": "middle", class: "pbadge-t", text: count > 99 ? "99+" : count }));
    }
    if (n.network) ng.appendChild(sv("text", { x: n.x + 6, y: n.y + n.h / 2 + 4, class: "divehint", fill: luminance(color) > 0.45 ? "#16171c" : "#fff", text: "▾" }));
  }

  _renderCrumbs() {
    this.crumbs.textContent = "";
    this.stack.forEach((s, i) => {
      const b = document.createElement("button");
      b.textContent = i === 0 ? "root" : s.name;
      b.disabled = i === this.stack.length - 1;
      b.addEventListener("click", () => this.up(i));
      this.crumbs.appendChild(b);
      if (i < this.stack.length - 1) this.crumbs.appendChild(document.createTextNode("›"));
    });
    this.host.querySelector('[data-a="up"]').disabled = this.stack.length < 2;
  }

  // ---------------------------------------------------------------- view
  bounds() {
    const net = this.net;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const add = (x, y, w, h) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + w); y1 = Math.max(y1, y + h); };
    for (const n of net.nodes) {
      const horiz = this.flow === "h";
      const textW = this.isNuke || n.kind !== "node" || horiz ? 0 : 12 + Math.max(n.name.length, (n.type_label || n.type).length * 0.85) * 7;
      add(n.x - (horiz ? 40 : 0), n.y - 12, n.w + textW + (horiz ? 40 : 0), n.h + (horiz ? 44 : 24));
    }
    for (const b of (net.boxes || []).concat(net.notes || [])) add(b.x, b.y, b.w, b.h);
    if (x0 === Infinity) return { x: 0, y: 0, w: 100, h: 100 };
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  fit() {
    const r = this.svg.getBoundingClientRect();
    if (!r.width) return;
    const b = this.bounds(), pad = 50;
    const k = Math.min(1.4, (r.width - pad * 2) / b.w, (r.height - pad * 2) / b.h);
    this.t = { k, x: r.width / 2 - (b.x + b.w / 2) * k, y: r.height / 2 - (b.y + b.h / 2) * k };
    this._apply();
  }

  _apply() {
    this.root.setAttribute("transform", `translate(${this.t.x},${this.t.y}) scale(${this.t.k})`);
  }

  _bindPanZoom() {
    const svg = this.svg;
    let drag = null;
    svg.addEventListener("pointerdown", e => {
      drag = { x: e.clientX, y: e.clientY, tx: this.t.x, ty: this.t.y };
      this._dragged = false;
    });
    window.addEventListener("pointermove", e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) this._dragged = true;
      if (!this._dragged) return;
      this.t.x = drag.tx + dx;
      this.t.y = drag.ty + dy;
      svg.classList.add("panning");
      this._apply();
    });
    window.addEventListener("pointerup", () => { drag = null; svg.classList.remove("panning"); });
    svg.addEventListener("click", () => { if (!this._dragged) this.select(null); });
    svg.addEventListener("wheel", e => {
      e.preventDefault();
      const r = svg.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      const k = Math.max(0.08, Math.min(4, this.t.k * Math.exp(-e.deltaY * 0.0015)));
      this.t.x = px - (px - this.t.x) * k / this.t.k;
      this.t.y = py - (py - this.t.y) * k / this.t.k;
      this.t.k = k;
      this._apply();
    }, { passive: false });
  }
}
