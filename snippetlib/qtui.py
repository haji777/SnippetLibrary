# -*- coding: utf-8 -*-
"""Qt dialogs shared by Houdini and Nuke (PySide6, falls back to PySide2)."""

import os
import subprocess

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # older Houdini / Nuke
    from PySide2 import QtCore, QtGui, QtWidgets

from . import core

APP_COLORS = {"houdini": "#ff6a1a", "nuke": "#f5c518"}


def _exec(dialog):
    return dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()


class _HintedTextEdit(QtWidgets.QPlainTextEdit):
    """QPlainTextEdit keeps its placeholder while only IME preedit text exists
    (the document is still empty), so Japanese input is drawn on top of the
    hint. Hide the hint for as long as something is being composed."""

    def __init__(self, hint, parent=None):
        super(_HintedTextEdit, self).__init__(parent)
        self._hint = hint
        self.setPlaceholderText(hint)

    def inputMethodEvent(self, event):
        self.setPlaceholderText("" if event.preeditString() else self._hint)
        super(_HintedTextEdit, self).inputMethodEvent(event)
        self.viewport().update()


class WordCompleter(QtWidgets.QCompleter):
    """Completes the word under the cursor (the last token) instead of the
    whole line, so 'ripple de|' offers 'deform' and keeps 'ripple '."""

    def __init__(self, words, separators, parent=None):
        super(WordCompleter, self).__init__(sorted(words, key=str.lower), parent)
        self.separators = separators
        self.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterMode(QtCore.Qt.MatchStartsWith)
        self.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)

    def _split(self, text):
        """-> (prefix kept as is, last token being typed)"""
        cut = 0
        for i, ch in enumerate(text):
            if ch in self.separators:
                cut = i + 1
        return text[:cut], text[cut:]

    def splitPath(self, path):
        return [self._split(path)[1]]

    def pathFromIndex(self, index):
        word = index.data() or ""  # the chosen completion (index comes from the completion model)
        prefix, _ = self._split(self.widget().text())
        return prefix + word


def _attach_word_completer(line_edit, words, separators):
    if not words:
        return None
    completer = WordCompleter(words, separators, line_edit)
    line_edit.setCompleter(completer)
    return completer


class _HistoryCombo(QtWidgets.QComboBox):
    """Editable combo: the line is typed freely, the drop-down holds recent values."""

    def __init__(self, history, placeholder, parent=None):
        super(_HistoryCombo, self).__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.addItems(list(history))
        self.setCurrentIndex(-1)
        self.lineEdit().setPlaceholderText(placeholder)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def text(self):
        return self.lineEdit().text()

    def setText(self, text):
        self.lineEdit().setText(text)


class SaveDialog(QtWidgets.QDialog):
    """Title / file name / tags / description for a new snippet.

    vocab (core.naming_vocabulary) fills the drop-downs and completers;
    prefill (a snippet meta) pre-fills everything when a snippet is being
    superseded by a new version."""

    def __init__(self, app, context, contexts=None, node_count=0, parent=None, vocab=None, prefill=None):
        super(SaveDialog, self).__init__(parent)
        self.setWindowTitle("Save to Snippet Library" if not prefill else "Overwrite snippet (new version)")
        self.setMinimumWidth(520)
        profile = core.get_profile()
        vocab = vocab or {"titles": [], "names": [], "tags": [], "words": []}

        header = QtWidgets.QLabel(
            "<span style='color:%s'>&#9679;</span> <b>%s</b> &nbsp; "
            "<span style='color:%s'>&#9632;</span> %s &nbsp; %d nodes"
            % (APP_COLORS.get(app, "#888"), app, profile["color"], profile["display"], node_count))
        self.app, self.user = app, profile["user"]
        self.supersede = prefill  # meta of the snippet this save replaces, if any

        self.title = _HistoryCombo(vocab["titles"], "表示タイトル（日本語OK）")
        _attach_word_completer(self.title.lineEdit(), vocab["words"], " ")
        self.name = _HistoryCombo(vocab["names"], "半角英数字 _ - のみ（ファイル名に使われます）")
        self.name.lineEdit().setValidator(QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression(r"[A-Za-z0-9_\-. ]*"), self.name))
        _attach_word_completer(self.name.lineEdit(), [w for w in vocab["words"] if w.isascii()], "_-. ")
        self._name_edited = False
        self.preview = QtWidgets.QLabel()
        self.preview.setStyleSheet("color: gray; font-family: Consolas, monospace;")
        self.preview.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.context = QtWidgets.QComboBox()
        self.context.addItems(contexts or [context])
        self.context.setEditable(bool(contexts))
        self.context.setCurrentText(context)
        self.context.setEnabled(bool(contexts))

        self.tags = QtWidgets.QLineEdit()
        self.tags.setPlaceholderText("tag1, tag2 ...")
        _attach_word_completer(self.tags, vocab["tags"], ", ")
        tag_btn = QtWidgets.QToolButton()
        tag_btn.setText("▾")
        tag_btn.setToolTip("使われているタグから選ぶ")
        tag_menu = QtWidgets.QMenu(tag_btn)
        for tag in vocab["tags"][:60]:
            tag_menu.addAction(tag, lambda t=tag: self._add_tag(t))
        if not vocab["tags"]:
            tag_menu.addAction("(まだタグがありません)").setEnabled(False)
        tag_btn.setMenu(tag_menu)
        tag_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        tag_row = QtWidgets.QHBoxLayout()
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.addWidget(self.tags, 1)
        tag_row.addWidget(tag_btn)

        self.description = _HintedTextEdit("簡単な説明 / コメント")
        self.description.setMinimumHeight(110)

        self.library = QtWidgets.QComboBox()
        for lib in core.get_libraries():
            if not lib.get("missing"):
                self.library.addItem(("%s" if lib["primary"] else "🔗 %s") % lib["name"], lib["path"])
        self.library.setToolTip("保存先のライブラリ（ビューアーの ⚙ でリンク / 作成したものが選べます）")
        self.libpath = QtWidgets.QLabel()
        self.libpath.setStyleSheet("color: gray;")
        self.libpath.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.library.currentIndexChanged.connect(
            lambda _i: self.libpath.setText(self.library.currentData() or ""))
        self.libpath.setText(self.library.currentData() or "")

        form = QtWidgets.QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("File name", self.name)
        form.addRow("", self.preview)
        form.addRow("Context", self.context)
        form.addRow("Tags", tag_row)
        form.addRow("Description", self.description)
        form.addRow("Library", self.library)
        form.addRow("", self.libpath)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(header)
        if prefill:
            note = QtWidgets.QLabel("「%s」の新しいバージョンとして保存します。保存後、旧バージョンは一覧で打ち消し線表示になり、"
                                    "Houdini / Nuke のロード一覧からは消えます。" % prefill.get("title", ""))
            note.setWordWrap(True)
            note.setStyleSheet("color: #d9a441;")
            layout.addWidget(note)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.title.lineEdit().textChanged.connect(self._title_changed)
        self.name.lineEdit().textEdited.connect(self._name_edited_by_user)
        self.name.lineEdit().textChanged.connect(self._name_changed)
        self.context.currentTextChanged.connect(self._update_preview)
        if prefill:
            self._apply_prefill(prefill)
        self._update_preview()
        self.title.setFocus()

    # ------------------------------------------------------------ behaviour
    def _apply_prefill(self, meta):
        self.title.setText(core.bump_version(meta.get("title", ""), " "))
        self._name_edited = True
        self.name.setText(core.bump_version(meta.get("name", "") or core.ascii_slug(meta.get("title", "")), "_"))
        self.tags.setText(", ".join(meta.get("tags") or []))
        self.description.setPlainText(meta.get("desc") or meta.get("description") or "")
        if meta.get("context") and self.context.isEnabled():
            self.context.setCurrentText(meta["context"])
        root = (meta.get("_lib") or {}).get("path")
        if root:
            for i in range(self.library.count()):
                if os.path.normcase(self.library.itemData(i) or "") == os.path.normcase(root):
                    self.library.setCurrentIndex(i)

    def _title_changed(self, text):
        # follow the title while the user has not typed a file name themselves
        if not self._name_edited:
            self.name.lineEdit().blockSignals(True)
            self.name.setText(core.ascii_slug(text))
            self.name.lineEdit().blockSignals(False)
        self._update_preview()

    def _name_edited_by_user(self, text):
        self._name_edited = bool(text.strip())

    def _name_changed(self, text):
        if " " in text:  # file names never contain spaces: type a space, get an underscore
            edit = self.name.lineEdit()
            pos = edit.cursorPosition()
            edit.blockSignals(True)
            edit.setText(text.replace(" ", "_"))
            edit.setCursorPosition(pos)
            edit.blockSignals(False)
        self._update_preview()

    def _add_tag(self, tag):
        current = [t.strip() for t in self.tags.text().split(",") if t.strip()]
        if tag not in current:
            current.append(tag)
        self.tags.setText(", ".join(current))

    def _update_preview(self, *_):
        slug = core.ascii_slug(self.name.text())
        ext = core.PAYLOAD_EXT.get(self.app, "")
        context = core.safe_name(self.context.currentText()).lower() or "misc"
        if slug:
            self.preview.setText("→ %s_%s_%s%s" % (self.user, context, slug, ext))
        else:
            self.preview.setText("→ ファイル名を半角英数字で入力してください")

    def _accept(self):
        if not self.title.text().strip():
            self.title.setFocus()
            return
        if not core.ascii_slug(self.name.text()):
            self.name.setFocus()
            return
        if self.supersede is None and not self._check_duplicate():
            return
        self.accept()

    def _check_duplicate(self):
        """A title / file name that (almost) matches an existing snippet is most
        likely meant as its next version: offer that. -> False to stay in the dialog."""
        try:
            hits = core.similar_snippets(core.get_libraries(), self.app, self.title.text(),
                                         self.name.text(), threshold=self.SIMILARITY)
        except Exception:
            hits = []
        if not hits:
            return True
        old = hits[0]
        same = old["_score"] >= 1.0
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("同じ名前のスニペットがあります" if same else "似た名前のスニペットがあります")
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setText("「%s」 (%s / %s%s)%s" % (
            old.get("title", ""), old.get("user", ""), (old.get("_lib") or {}).get("name", ""),
            "" if same else "、一致率 %d%%" % round(old["_score"] * 100),
            " と同じ名前です。" if same else " に似ています。"))
        box.setInformativeText("このスニペットの新しいバージョンとして上書きしますか？\n"
                               "上書きすると旧バージョンは一覧で打ち消し線表示になり、Houdini / Nuke のロード一覧からは消えます。")
        overwrite = box.addButton("新しいバージョンとして上書き", QtWidgets.QMessageBox.AcceptRole)
        keep = box.addButton("別のスニペットとして保存", QtWidgets.QMessageBox.DestructiveRole)
        box.addButton("戻る", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(overwrite)
        self._exec_box(box)
        clicked = box.clickedButton()
        if clicked is overwrite:
            self.supersede = old
            # identical name -> number the new version like the Overwrite menu does
            if core._compare_key(self.title.text()) == core._compare_key(old.get("title")):
                self.title.setText(core.bump_version(old.get("title", ""), " "))
            if core._compare_key(self.name.text()) == core._compare_key(old.get("name")):
                self._name_edited = True
                self.name.setText(core.bump_version(old.get("name", "") or core.ascii_slug(old.get("title", "")), "_"))
            return True
        return clicked is keep

    SIMILARITY = 0.9

    def _exec_box(self, box):
        box.exec_() if hasattr(box, "exec_") else box.exec()

    def values(self):
        return {"title": self.title.text().strip(),
                "name": core.ascii_slug(self.name.text()),
                "root": self.library.currentData() or core.library_root(),
                "context": self.context.currentText().strip(),
                "tags": [t.strip() for t in self.tags.text().split(",") if t.strip()],
                "description": self.description.toPlainText().strip(),
                "supersede": self.supersede}


def ask_save(app, context, contexts=None, node_count=0, parent=None, prefill=None):
    roots = [l["path"] for l in core.get_libraries() if not l.get("missing")]
    try:
        vocab = core.naming_vocabulary(roots, app=app)
    except Exception:
        vocab = None
    dialog = SaveDialog(app, context, contexts, node_count, parent, vocab=vocab, prefill=prefill)
    if _exec(dialog):
        return dialog.values()
    return None


class BrowserDialog(QtWidgets.QDialog):
    """Small in-app browser: works even when the viewer is not running.
    pick=True turns it into a modal chooser (used by "Overwrite exist snippet")."""

    COLUMNS = ("", "Date", "User", "Context", "Title", "Description", "Library")

    def __init__(self, app, on_load, parent=None, pick=False):
        super(BrowserDialog, self).__init__(parent)
        self.app, self.on_load, self.pick = app, on_load, pick
        self.picked = None
        self.setWindowTitle("Snippet Library - %s" % app if not pick else "上書きするスニペットを選択 - %s" % app)
        self.resize(900, 520)
        self.items = []

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("filter...")
        self.crown = QtWidgets.QCheckBox("\U0001F451 殿堂入りのみ")
        self.mine = QtWidgets.QCheckBox("自分のみ")
        self.old = QtWidgets.QCheckBox("旧バージョンも表示")
        reload_btn = QtWidgets.QPushButton("Reload")
        viewer_btn = QtWidgets.QPushButton("Open Viewer")
        top = QtWidgets.QHBoxLayout()
        for w in (self.search, self.crown, self.mine, self.old, reload_btn, viewer_btn):
            top.addWidget(w)

        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)

        load_btn = QtWidgets.QPushButton("Load" if not pick else "Select")
        load_btn.setDefault(True)
        close_btn = QtWidgets.QPushButton("Close" if not pick else "Cancel")
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(load_btn)
        bottom.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addLayout(bottom)

        self.search.textChanged.connect(self.refresh)
        self.crown.toggled.connect(self.refresh)
        self.mine.toggled.connect(self.refresh)
        self.old.toggled.connect(self.refresh)
        reload_btn.clicked.connect(self.reload)
        viewer_btn.clicked.connect(launch_viewer)
        load_btn.clicked.connect(self.load_current)
        close_btn.clicked.connect(self.reject)
        self.table.doubleClicked.connect(self.load_current)
        self.reload()

    def reload(self):
        self.items = []
        self.profiles = core.all_profiles([l["path"] for l in core.get_libraries()])
        for lib in core.get_libraries():
            if lib.get("missing"):
                continue
            for meta in core.scan_library(lib["path"]):
                if meta.get("app") == self.app:
                    meta["_lib"] = lib
                    self.items.append(meta)
        self.items.sort(key=lambda m: m.get("created", ""), reverse=True)
        self.refresh()

    def refresh(self):
        text = self.search.text().lower()
        me = core.current_user()
        self.table.setRowCount(0)
        for meta in self.items:
            if meta.get("superseded_by") and not self.old.isChecked():
                continue  # replaced by a newer version: hidden unless asked for
            if self.crown.isChecked() and not meta.get("crown"):
                continue
            if self.mine.isChecked() and meta.get("user") != me:
                continue
            hay = " ".join([meta.get("title", ""), meta.get("desc", ""), meta.get("user", ""),
                            " ".join(meta.get("tags") or []),
                            " ".join(meta.get("types") or [])]).lower()
            if text and text not in hay:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            cells = ("\U0001F451" if meta.get("crown") else "",
                     meta.get("created", "")[:16].replace("T", " "),
                     meta.get("user", ""), meta.get("context", ""), meta.get("title", ""),
                     meta.get("desc", "").split("\n")[0], meta["_lib"]["name"])
            for col, value in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(value)
                if col == 0:
                    item.setData(QtCore.Qt.UserRole, meta)
                if col == 2:
                    color = self.profiles.get(meta.get("user"), {}).get("color") \
                        or core.default_color(meta.get("user", ""))
                    item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
                if meta.get("superseded_by"):
                    font = item.font()
                    font.setStrikeOut(True)
                    item.setFont(font)
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#777")))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(5, 320)

    def current_meta(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(QtCore.Qt.UserRole)

    def load_current(self, *_):
        meta = self.current_meta()
        if meta is None:
            return
        if self.pick:
            self.picked = meta
            self.accept()
            return
        sdir = core.resolve_rel(meta["_lib"]["path"], meta["rel"])
        self.on_load(os.path.join(sdir, meta.get("payload", "")), meta)


_browsers = {}


def show_browser(app, on_load, parent=None):
    dialog = _browsers.get(app)
    if dialog is None:
        dialog = _browsers[app] = BrowserDialog(app, on_load, parent)
    else:
        dialog.reload()
    dialog.show()
    dialog.raise_()
    return dialog


def pick_snippet(app, parent=None):
    """Modal chooser -> the chosen snippet's meta (with _lib and rel), or None."""
    dialog = BrowserDialog(app, None, parent, pick=True)
    if _exec(dialog):
        return dialog.picked
    return None


def launch_viewer():
    """Start the viewer server with the DCC's environment (same library/user)."""
    script = os.path.join(core.repo_dir(), "viewer", "server.py")
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH"):  # the DCC's python env breaks system python
        env.pop(key, None)
    # SNIPPETLIB_ROOT / _USER are inherited when the DCC has them; otherwise the
    # viewer reads the same machine setting the DCC used, so nothing is forced here.
    for exe in (["py", "-3"], ["python"]):  # never sys.executable: that is the DCC itself
        try:
            subprocess.Popen(exe + [script], creationflags=flags, cwd=core.repo_dir(), env=env)
            return
        except OSError:
            continue
    QtWidgets.QMessageBox.warning(None, "Snippet Library",
                                  "python が見つかりません。launch_viewer.bat を使ってください。")
