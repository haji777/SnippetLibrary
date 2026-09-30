/* Snippet Library viewer: list + detail views (vanilla JS, no build step) */
"use strict";

const APP_INFO = {
  houdini: { label: "Houdini", color: "#ff6a1a" },
  nuke: { label: "Nuke", color: "#f5c518" },
};

const S = {
  state: null, snippets: [], view: null, timer: null,
  filters: { apps: new Set(), contexts: new Set(), users: new Set(), libs: new Set(), crown: false, q: "", sort: "new" },
};

// ------------------------------------------------------------------ helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [prop, val] of Object.entries(v)) prop.startsWith("--") ? el.style.setProperty(prop, val) : (el.style[prop] = val);
    }
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(kid));
  }
  return el;
}

function put(el, ...kids) {
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-SnippetLib": "1" },
  };
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, kind) {
  const el = h("div", { class: "toast " + (kind || ""), text: msg });
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 3500);
}

const crownSvg = () => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.innerHTML = '<path d="M3 18h18l1.2-10.5-5.4 4.2L12 4.5 7.2 11.7 1.8 7.5z M4 19.5h16v2H4z"/>';
  return s;
};

function crownButton(on, onToggle) {
  return h("button", { class: "crown" + (on ? " on" : ""), title: on ? "殿堂入りを解除" : "殿堂入りにする",
    onclick: e => { e.preventDefault(); e.stopPropagation(); onToggle(); } }, crownSvg());
}

const profile = user => (S.state.profiles[user] || { user, display: user, color: hashColor(user) });
const library = id => S.state.libraries.find(l => l.id === id) || { name: "?", color: "#888" };

function hashColor(text) {
  let n = 0;
  for (const ch of text || "") n = (n * 31 + ch.charCodeAt(0)) >>> 0;
  return S.state.palette[n % S.state.palette.length];
}

function userChip(user, extra) {
  const p = profile(user);
  return h("span", { class: "chip user " + (extra || ""), style: { "--c": p.color }, title: user },
    h("i", { class: "avatar", text: (p.display || user).slice(0, 1).toUpperCase() }), p.display);
}

function appBadge(app) {
  const a = APP_INFO[app] || { label: app, color: "#888" };
  return h("span", { class: "badge app", style: { "--c": a.color }, text: a.label });
}

function versionText(meta) {
  const a = APP_INFO[meta.app] || { label: meta.app };
  return meta.app_version ? `${a.label} ${meta.app_version}` : a.label;
}

const ctxBadge = ctx => h("span", { class: "badge ctx", style: { "--c": hashColor("ctx:" + ctx) }, text: ctx });
const libBadge = id => { const l = library(id); return h("span", { class: "badge lib" + (l.primary ? "" : " linked"), style: { "--c": l.color }, title: l.path }, l.primary ? "" : "🔗 ", l.name); };
const fmtTime = iso => (iso || "").slice(11, 16);
const fmtDay = iso => {
  const d = new Date(iso);
  return isNaN(d) ? (iso || "").slice(0, 10) : `${iso.slice(0, 10)} (${"日月火水木金土"[d.getDay()]})`;
};

// ------------------------------------------------------------------ boot / routing
async function boot() {
  await refreshState();
  document.getElementById("mebtn").addEventListener("click", openSettings);
  window.addEventListener("hashchange", route);
  window.addEventListener("keydown", e => {
    if (/INPUT|TEXTAREA/.test(document.activeElement.tagName) || !S.view || !S.view.graph) return;
    if (e.key === "f" || e.key === "F") S.view.graph.fit();
    if (e.key === "u" || e.key === "U") S.view.graph.up();
  });
  route();
}

async function refreshState() {
  S.state = await api("/api/state");
  const me = document.getElementById("mebtn");
  me.textContent = "";
  me.append(userChip(S.state.user), h("span", { class: "gear", text: "⚙" }));
  const lib = S.state.libraries[0];
  const ln = document.getElementById("libname");
  ln.textContent = "";
  put(ln, h("span", { class: "badge lib", style: { "--c": lib.color }, title: lib.path, text: lib.name }),
    S.state.libraries.length > 1 ? h("span", { class: "muted", text: ` + ${S.state.libraries.length - 1} linked` }) : null);
}

function route() {
  clearInterval(S.timer);
  S.view = null;
  const m = location.hash.match(/^#\/s\/(\d+)\/(.+)$/);
  if (m) showDetail(Number(m[1]), decodeURI(m[2]));
  else showList();
}

// ------------------------------------------------------------------ list view
async function showList() {
  const app = document.getElementById("app");
  app.className = "listview";
  app.textContent = "";
  const side = h("aside", { class: "filters" });
  const main = h("section", { class: "results" });
  app.append(side, main);
  try {
    S.snippets = (await api("/api/snippets")).snippets;
  } catch (err) { toast(err.message, "error"); }
  const draw = () => { drawFilters(side, draw); drawResults(main, draw); };
  draw();
}

function countBy(key) {
  const out = new Map();
  for (const s of S.snippets) out.set(s[key], (out.get(s[key]) || 0) + 1);
  return [...out.entries()].sort((a, b) => b[1] - a[1]);
}

function drawFilters(side, redraw) {
  const F = S.filters;
  side.textContent = "";
  const group = (title, key, setName, render) => {
    const entries = countBy(key);
    if (!entries.length) return null;
    return h("div", { class: "fgroup" }, h("h4", { text: title }),
      h("div", { class: "fchips" }, entries.map(([value, count]) => {
        const on = F[setName].has(value);
        return h("button", { class: "fchip" + (on ? " on" : ""), onclick: () => { on ? F[setName].delete(value) : F[setName].add(value); redraw(); } },
          render(value), h("em", { text: count }));
      })));
  };
  put(side, 
    h("button", { class: "crownfilter" + (F.crown ? " on" : ""), onclick: () => { F.crown = !F.crown; redraw(); } },
      crownSvg(), "殿堂入りのみ", h("em", { text: S.snippets.filter(s => s.crown).length })),
    group("Software", "app", "apps", v => appBadge(v)),
    group("User", "user", "users", v => userChip(v)),
    group("Context", "context", "contexts", v => ctxBadge(v)),
    S.state.libraries.length > 1 ? group("Library", "lib", "libs", v => libBadge(v)) : null,
    h("button", { class: "clear", text: "フィルタをクリア", onclick: () => {
      for (const k of ["apps", "contexts", "users", "libs"]) F[k].clear();
      F.crown = false; F.q = ""; redraw();
    } }));
}

function filtered() {
  const F = S.filters, q = F.q.trim().toLowerCase();
  const pass = (set, v) => !set.size || set.has(v);
  let items = S.snippets.filter(s => pass(F.apps, s.app) && pass(F.contexts, s.context) &&
    pass(F.users, s.user) && pass(F.libs, s.lib) && (!F.crown || s.crown));
  if (q) {
    items = items.filter(s => q.split(/\s+/).every(word =>
      [s.title, s.desc, s.user, s.context, s.app, s.app_version, (s.tags || []).join(" "), (s.types || []).join(" ")]
        .join(" ").toLowerCase().includes(word)));
  }
  const by = { new: (a, b) => (b.created || "").localeCompare(a.created || ""),
    old: (a, b) => (a.created || "").localeCompare(b.created || ""),
    title: (a, b) => (a.title || "").localeCompare(b.title || "", "ja"),
    user: (a, b) => (a.user || "").localeCompare(b.user || "") || (b.created || "").localeCompare(a.created || "") };
  return items.sort(by[F.sort]);
}

function drawResults(main, redraw) {
  const F = S.filters;
  const keepFocus = document.activeElement && document.activeElement.id === "q";
  main.textContent = "";
  const items = filtered();
  const search = h("input", { id: "q", type: "search", placeholder: "検索: タイトル / コメント / タグ / ノードタイプ ...", value: F.q,
    oninput: e => { F.q = e.target.value; redraw(); } });
  const sort = h("select", { onchange: e => { F.sort = e.target.value; redraw(); } },
    [["new", "新しい順"], ["old", "古い順"], ["title", "タイトル順"], ["user", "ユーザー順"]]
      .map(([v, t]) => h("option", { value: v, selected: F.sort === v, text: t })));
  put(main, h("div", { class: "toolbar" }, search, sort, h("span", { class: "muted", text: `${items.length} / ${S.snippets.length}` })));
  if (keepFocus) { search.focus(); search.setSelectionRange(F.q.length, F.q.length); }

  if (!items.length) {
    put(main, h("div", { class: "empty" }, S.snippets.length ? "条件に合うスニペットがありません。" :
      ["まだスニペットがありません。", h("br"), "Houdini / Nuke でノードを選択して「Save Selection to Library」を実行してください。",
        h("br"), h("code", { text: S.state.libraries[0].path })]));
    return;
  }
  const dated = F.sort === "new" || F.sort === "old";
  let lastDay = null, list = null;
  for (const s of items) {
    const day = (s.created || "").slice(0, 10);
    if (!list || (dated && day !== lastDay)) {
      if (dated) put(main, h("h3", { class: "day" }, fmtDay(s.created)));
      list = h("div", { class: "rows" });
      put(main, list);
      lastDay = day;
    }
    list.append(row(s, redraw));
  }
}

function row(s, redraw) {
  const p = profile(s.user);
  return h("a", { class: "row" + (s.crown ? " crowned" : ""), href: `#/s/${s.lib}/${encodeURI(s.rel)}`, style: { "--c": p.color, "--app": (APP_INFO[s.app] || {}).color } },
    crownButton(s.crown, async () => {
      try {
        await api("/api/update", { lib: s.lib, rel: s.rel, crown: !s.crown });
        s.crown = !s.crown;
        redraw();
      } catch (err) { toast(err.message, "error"); }
    }),
    h("div", { class: "rmain" },
      h("div", { class: "rtitle" }, h("b", { text: s.title }), (s.tags || []).map(t => h("span", { class: "tag", text: "#" + t }))),
      h("div", { class: "rdesc", text: (s.desc || "").split("\n")[0] })),
    h("div", { class: "rmeta" },
      h("div", {}, appBadge(s.app), ctxBadge(s.context), h("span", { class: "ver", text: s.app_version || "" })),
      h("div", {}, userChip(s.user), libBadge(s.lib))),
    h("div", { class: "rtime" }, h("b", { text: fmtTime(s.created) }), h("span", { text: (s.created || "").slice(0, 10) }),
      h("span", { class: "muted", text: `${s.node_count || 0} nodes` })));
}

// ------------------------------------------------------------------ detail view
async function showDetail(lib, rel) {
  const app = document.getElementById("app");
  app.className = "detailview";
  app.textContent = "";
  let data;
  try {
    data = await api(`/api/snippet?lib=${lib}&rel=${encodeURIComponent(rel)}`);
  } catch (err) {
    app.append(h("div", { class: "empty" }, err.message, h("br"), h("a", { href: "#/", text: "← 一覧へ" })));
    return;
  }
  const view = S.view = { lib, rel, data, sessions: [], graph: null };
  const meta = data.meta;
  const head = h("div", { class: "dhead" });
  const canvas = h("div", { class: "canvas" });
  const panel = h("aside", { class: "panel" });
  app.append(head, canvas, panel);

  const info = h("div", { class: "pinfo" });
  const nodePane = h("div", { class: "pnode" });
  panel.append(info, nodePane);

  const drawHead = () => {
    head.textContent = "";
    const loadBox = h("div", { class: "loadbox" });
    put(head, 
      h("a", { class: "back", href: "#/", text: "←" }),
      crownButton(meta.crown, async () => {
        try { Object.assign(meta, (await api("/api/update", { lib, rel, crown: !meta.crown })).meta); drawHead(); }
        catch (err) { toast(err.message, "error"); }
      }),
      h("div", { class: "dtitle" }, titleBox(),
        h("div", { class: "dsub" }, appBadge(meta.app), h("span", { class: "ver strong", text: versionText(meta) }), ctxBadge(meta.context),
          userChip(meta.user), libBadge(lib), h("span", { class: "muted", text: (meta.created || "").replace("T", " ") }),
          meta.scene ? h("span", { class: "muted", text: "from " + meta.scene }) : null,
          meta.origin ? h("span", { class: "muted", text: `⇠ ${meta.origin} (${meta.author || "?"})` }) : null)),
      h("span", { class: "spacer" }),
      meta.app === "nuke" ? h("button", { class: "btn", title: "クリップボードにコピーして Nuke に Ctrl+V", text: "Copy .nk", onclick: copyNk }) : null,
      h("button", { class: "btn", text: "Copy path", onclick: () => copyText(data.payload, "パスをコピーしました") }),
      h("button", { class: "btn", text: "Open folder", onclick: () => api("/api/reveal", { lib, rel }).catch(e => toast(e.message, "error")) }),
      library(lib).primary ? null : h("button", { class: "btn", title: "このプロジェクトのライブラリへコピー", text: "Import ⇣", onclick: importHere }),
      h("button", { class: "btn danger", title: "削除（_trash フォルダへ移動）", text: "🗑", onclick: confirmDelete }),
      loadBox);
    drawLoad(loadBox);
  };

  // ---- title: click the pencil (or double-click the title) to rename
  let editingTitle = false;
  const titleBox = () => {
    if (!editingTitle) {
      const start = () => { editingTitle = true; drawHead(); };
      return h("div", { class: "titlebox" }, h("h1", { text: meta.title, title: "ダブルクリックで名前を変更", ondblclick: start }),
        h("button", { class: "pencil", title: "タイトルを編集", text: "✎", onclick: start }));
    }
    const input = h("input", { type: "text", class: "titleinput", value: meta.title });
    const cancel = () => { editingTitle = false; drawHead(); };
    const save = async () => {
      const title = input.value.trim();
      if (!title || title === meta.title) return cancel();
      try {
        Object.assign(meta, (await api("/api/update", { lib, rel, title })).meta);
        // file names follow the title, so refresh the payload path shown / copied here
        data.payload = (await api(`/api/snippet?lib=${lib}&rel=${encodeURIComponent(rel)}`)).payload;
        toast("タイトルを変更しました", "ok");
      } catch (err) { toast(err.message, "error"); }
      cancel();
    };
    input.addEventListener("keydown", e => {
      if (e.isComposing || e.keyCode === 229) return;  // Enter that confirms the IME conversion
      if (e.key === "Enter") save();
      if (e.key === "Escape") cancel();
      e.stopPropagation();
    });
    setTimeout(() => { input.focus(); input.select(); });
    return h("div", { class: "titlebox" }, input,
      h("button", { class: "btn primary", text: "✓", title: "保存 (Enter)", onclick: save }),
      h("button", { class: "btn", text: "✕", title: "キャンセル (Esc)", onclick: cancel }));
  };

  function confirmDelete() {
    const root = document.getElementById("modal-root");
    const close = () => { root.textContent = ""; };
    const mine = meta.user === S.state.user;
    put(root, h("div", { class: "modal-bg", onclick: e => { if (e.target.classList.contains("modal-bg")) close(); } },
      h("div", { class: "modal small" },
        h("h2", { text: "このスニペットを削除しますか？" }),
        h("p", {}, h("b", { text: meta.title }), " ", userChip(meta.user), " ", libBadge(lib)),
        mine ? null : h("p", { class: "warn", text: `⚠ これは ${profile(meta.user).display} さんのスニペットです。` }),
        h("p", { class: "muted small", text: "ファイルは消さず、ライブラリ直下の _trash フォルダへ移動します（フォルダを戻せば復元できます）。" }),
        h("div", { class: "actions" },
          h("button", { class: "btn", text: "キャンセル", onclick: close }),
          h("button", { class: "btn danger solid", text: "削除する", onclick: async () => {
            try {
              const res = await api("/api/delete", { lib, rel });
              close();
              toast("削除しました → " + res.trash, "ok");
              location.hash = "#/";
            } catch (err) { close(); toast(err.message, "error"); }
          } })))));
  }

  const drawLoad = box => {
    box.textContent = "";
    const label = (APP_INFO[meta.app] || {}).label || meta.app;
    const ses = view.sessions;
    if (!ses.length) {
      box.append(h("button", { class: "btn load", disabled: true, title: `起動中の ${label} が見つかりません（SnippetLibrary メニューが入った ${label} を起動してください）`, text: `Load → ${label} 未検出` }));
      return;
    }
    const sceneName = s => (s.scene || "untitled").split(/[\\/]/).pop();
    const verNote = s => (meta.app_version && s.version !== meta.app_version ? ` ⚠ ${s.version}` : "");
    if (ses.length === 1) {
      box.append(h("button", { class: "btn load", text: `Load → ${label} (${sceneName(ses[0])})${verNote(ses[0])}`, onclick: () => doLoad(ses[0]) }));
      return;
    }
    const sel = h("select", {}, ses.map(s => h("option", { value: s.id, text: `${sceneName(s)} · ${s.version} · pid ${s.pid}` })));
    box.append(sel, h("button", { class: "btn load", text: `Load → ${label}`, onclick: () => doLoad(ses.find(s => s.id === sel.value)) }));
  };

  const doLoad = async session => {
    try {
      const res = await api("/api/load", { lib, rel, session: session.id });
      toast(res.ok ? `ロードしました: ${res.message}` : res.message, res.ok ? "ok" : "error");
    } catch (err) { toast(err.message, "error"); }
  };

  async function copyNk() {
    try {
      const text = (await api(`/api/payload?lib=${lib}&rel=${encodeURIComponent(rel)}`)).text;
      copyText(text, "コピーしました。Nuke の Node Graph で Ctrl+V");
    } catch (err) { toast(err.message, "error"); }
  }

  async function importHere() {
    try {
      const res = await api("/api/import", { lib, rel });
      toast("このライブラリにコピーしました", "ok");
      location.hash = `#/s/${res.lib}/${encodeURI(res.rel)}`;
    } catch (err) { toast(err.message, "error"); }
  }

  // ---- description / tags editor
  const drawInfo = editing => {
    info.textContent = "";
    if (!editing) {
      put(info, 
        h("div", { class: "phead" }, h("h4", { text: "Description" }), h("button", { class: "link", text: "編集", onclick: () => drawInfo(true) })),
        h("div", { class: "desc" + (data.description ? "" : " muted"), text: data.description || "（コメントなし）" }),
        h("div", { class: "tags" }, (meta.tags || []).map(t => h("span", { class: "tag", text: "#" + t }))),
        meta.modified && meta.modified !== meta.created ? h("div", { class: "muted small", text: `edited ${meta.modified.replace("T", " ")}${meta.modified_by ? " by " + meta.modified_by : ""}` }) : null);
      return;
    }
    const title = h("input", { type: "text", value: meta.title });
    const tags = h("input", { type: "text", value: (meta.tags || []).join(", "), placeholder: "tag1, tag2" });
    const desc = h("textarea", { rows: 7 });
    desc.value = data.description;
    put(info, h("div", { class: "phead" }, h("h4", { text: "Edit" })),
      h("label", { text: "Title" }), title, h("label", { text: "Description" }), desc, h("label", { text: "Tags" }), tags,
      h("div", { class: "actions" },
        h("button", { class: "btn", text: "Cancel", onclick: () => drawInfo(false) }),
        h("button", { class: "btn primary", text: "Save", onclick: async () => {
          try {
            const res = await api("/api/update", { lib, rel, title: title.value, description: desc.value,
              tags: tags.value.split(",").map(t => t.trim()).filter(Boolean) });
            Object.assign(meta, res.meta);
            data.description = desc.value.trim();
            drawHead(); drawInfo(false);
            toast("保存しました", "ok");
          } catch (err) { toast(err.message, "error"); }
        } })));
    desc.focus();
  };

  // ---- node parameters
  const drawNode = (node, path) => {
    nodePane.textContent = "";
    if (!node) {
      const net = view.graph ? view.graph.net : null;
      put(nodePane, h("div", { class: "phead" }, h("h4", { text: "Nodes" }), h("span", { class: "muted small", text: "ノードをクリックで変更パラメータ / ダブルクリックで中へ" })));
      for (const n of (net ? net.nodes : []).filter(n => n.kind === "node")) {
        put(nodePane, h("button", { class: "nitem", onclick: () => view.graph.selectByName(n.name) },
          h("i", { class: "sw", style: { background: rgbCss(nodeColor(n, meta.app === "nuke")) } }),
          h("b", { text: n.name }), h("span", { class: "muted", text: n.type }),
          n.network ? h("span", { class: "muted", text: "▾" }) : null,
          n.params.length ? h("em", { text: n.params.length }) : null));
      }
      return;
    }
    const wiresIn = view.graph.net.wires.filter(w => w.dst === node.name).sort((a, b) => a.dst_in - b.dst_in);
    put(nodePane, 
      h("div", { class: "phead" }, h("h4", {}, node.name), h("button", { class: "link", text: "× 一覧", onclick: () => view.graph.select(null) })),
      h("div", { class: "ntype" }, h("b", { text: node.type_label || node.type }), node.type_label ? h("code", { text: node.type }) : null,
        h("span", { class: "muted small", text: "/" + (path ? path + "/" : "") + node.name })),
      node.label ? h("div", { class: "ncomment", text: node.label }) : null,
      wiresIn.length || (node.ext_inputs || []).length ? h("div", { class: "nin muted small" }, "inputs: ",
        wiresIn.map(w => h("button", { class: "link", text: `[${w.dst_in}] ${w.src}`, onclick: () => view.graph.selectByName(w.src) })),
        (node.ext_inputs || []).map(e => h("span", { text: ` [${e.dst_in}] (${e.from})` }))) : null,
      node.network ? h("button", { class: "btn", text: "▾ 中を見る", onclick: () => view.graph.dive(node) }) : null,
      h("h5", { text: node.params.length ? `変更されたパラメータ (${node.params.length})` : "変更されたパラメータはありません（すべてデフォルト）" }));
    for (const p of node.params) put(nodePane, paramRow(p));
  };

  drawHead();
  drawInfo(false);
  if (data.graph && data.graph.network) {
    view.graph = new GraphView(canvas, data.graph, drawNode);
  } else {
    canvas.append(h("div", { class: "empty", text: "ネットワーク情報 (graph.json) がありません。" }));
  }
  drawNode(null, "");

  const poll = async () => {
    try {
      const ses = (await api("/api/sessions?app=" + meta.app)).sessions;
      if (S.view !== view) return;
      if (JSON.stringify(ses.map(s => [s.id, s.scene])) !== JSON.stringify(view.sessions.map(s => [s.id, s.scene]))) {
        view.sessions = ses;
        drawLoad(head.querySelector(".loadbox"));
      }
    } catch (err) { /* server gone */ }
  };
  poll();
  S.timer = setInterval(poll, 3000);
}

function paramRow(p) {
  let v = p.value, kind = "";
  const isExpr = x => x && typeof x === "object" && !Array.isArray(x) && "expression" in x;
  if (isExpr(v)) { kind = "expr"; v = v.expression; }
  else if (Array.isArray(v) && v.some(isExpr)) {  // vector with per-component expressions
    kind = "expr";
    v = v.map(x => (isExpr(x) ? x.expression : typeof x === "object" ? JSON.stringify(x) : String(x))).join("\n");
  }
  else if (v && typeof v === "object" && !Array.isArray(v) && "keyframes" in v) { kind = "anim"; v = JSON.stringify(v.keyframes, null, 1); }
  else if (Array.isArray(v) && v.every(x => typeof x !== "object" || x === null)) v = v.join(",  ");
  else if (typeof v === "object") v = JSON.stringify(v, null, 1);
  else v = String(v);
  const multi = v.includes("\n") || v.length > 60;
  return h("div", { class: "param" + (multi ? " multi" : "") },
    h("div", { class: "pname" }, h("b", { text: p.label || p.name }), p.label && p.label !== p.name ? h("code", { text: p.name }) : null,
      kind ? h("span", { class: "kind " + kind, text: kind }) : null,
      multi ? h("button", { class: "link", text: "copy", onclick: () => copyText(v, "コピーしました") }) : null),
    multi ? h("pre", { text: v }) : h("div", { class: "pval", text: v }));
}

async function copyText(text, msg) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const ta = h("textarea", { style: { position: "fixed", opacity: 0 } });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  toast(msg, "ok");
}

// ------------------------------------------------------------------ settings
function openSettings() {
  const root = document.getElementById("modal-root");
  const close = () => { root.textContent = ""; };
  const st = S.state;
  let color = st.profile.color;
  const display = h("input", { type: "text", value: st.profile.display });
  const swatches = h("div", { class: "swatches" });
  const custom = h("input", { type: "color", value: color, oninput: e => { color = e.target.value; drawSw(); } });
  const drawSw = () => {
    swatches.textContent = "";
    for (const c of st.palette) swatches.append(h("button", { class: "sw" + (c === color ? " on" : ""), style: { background: c }, onclick: () => { color = c; custom.value = c; drawSw(); } }));
    swatches.append(custom, h("span", { class: "chip user", style: { "--c": color } }, h("i", { class: "avatar", text: (display.value || st.user).slice(0, 1).toUpperCase() }), display.value || st.user));
  };
  display.addEventListener("input", drawSw);
  drawSw();

  const libs = h("div", { class: "liblist" });
  const drawLibs = () => {
    libs.textContent = "";
    for (const l of S.state.libraries) {
      put(libs, h("div", { class: "librow" + (l.missing ? " missing" : "") }, libBadge(l.id), h("code", { text: l.path }),
        l.missing ? h("span", { class: "muted", text: "見つかりません" }) : null,
        l.source === "env" ? h("span", { class: "muted small", text: "SNIPPETLIB_LINKS" }) : null,
        l.source === "config" ? h("button", { class: "link", text: "解除", onclick: async () => {
          try { await api("/api/links", { action: "remove", path: l.path }); await refreshState(); drawLibs(); } catch (err) { toast(err.message, "error"); }
        } }) : null));
    }
  };
  drawLibs();
  const linkPath = h("input", { type: "text", placeholder: "P:\\OtherProject\\snippetLibrary" });
  const linkName = h("input", { type: "text", placeholder: "表示名（省略可）", class: "short" });
  const libName = h("input", { type: "text", value: st.libraries[0].name, class: "short" });
  const rootPath = h("input", { type: "text", value: st.root, disabled: st.root_source === "env", placeholder: st.default_root });
  const changeRoot = async create => {
    try {
      await api("/api/root", { path: rootPath.value, create });
      await refreshState();
      toast("ライブラリを切り替えました", "ok");
      close();
      if (!S.view) showList(); else location.hash = "#/";
    } catch (err) {
      if (!create && /見つかりません/.test(err.message) && confirm(`${rootPath.value}
フォルダがありません。新しく作成しますか？`)) return changeRoot(true);
      toast(err.message, "error");
    }
  };
  const rootBtn = h("button", { class: "btn", text: "変更", disabled: st.root_source === "env", onclick: () => changeRoot(false) });
  rootPath.addEventListener("keydown", e => { if (e.key === "Enter" && !e.isComposing) changeRoot(false); });

  root.append(h("div", { class: "modal-bg", onclick: e => { if (e.target.classList.contains("modal-bg")) close(); } },
    h("div", { class: "modal" },
      h("h2", { text: "Profile" }),
      h("p", { class: "muted small", text: `ユーザー: ${st.user}（Windows ユーザー名。環境変数 SNIPPETLIB_USER で上書き可）` }),
      h("label", { text: "表示名" }), display, h("label", { text: "カラー" }), swatches,
      h("div", { class: "actions" }, h("button", { class: "btn primary", text: "プロフィールを保存", onclick: async () => {
        try { await api("/api/profile", { display: display.value, color }); await refreshState(); toast("保存しました", "ok"); if (!S.view) showList(); }
        catch (err) { toast(err.message, "error"); }
      } })),
      h("h2", { text: "Libraries" }),
      h("label", { text: "ライブラリのパス（このマシンの設定）" }),
      h("div", { class: "linkadd" }, rootPath, rootBtn),
      st.root_source === "env" ? h("p", { class: "muted small", text: "環境変数 SNIPPETLIB_ROOT で固定されています（起動 bat を編集してください）" })
        : h("p", { class: "muted small", text: `既定: ${st.default_root}` }),
      h("div", { class: "linkadd" }, h("label", { text: "このライブラリの名前" }), libName, h("button", { class: "btn", text: "変更", onclick: async () => {
        try { await api("/api/links", { action: "library", name: libName.value }); await refreshState(); drawLibs(); } catch (err) { toast(err.message, "error"); }
      } })),
      libs,
      h("label", { text: "他プロジェクトのライブラリをリンク" }),
      h("div", { class: "linkadd" }, linkPath, linkName, h("button", { class: "btn", text: "リンク追加", onclick: async () => {
        try { await api("/api/links", { action: "add", path: linkPath.value, name: linkName.value }); linkPath.value = ""; linkName.value = ""; await refreshState(); drawLibs(); toast("リンクしました", "ok"); }
        catch (err) { toast(err.message, "error"); }
      } })),
      h("div", { class: "actions" }, h("button", { class: "btn", text: "閉じる", onclick: () => { close(); if (!S.view) showList(); } })))));
}

boot().catch(err => { document.getElementById("app").textContent = "起動エラー: " + err.message; });
