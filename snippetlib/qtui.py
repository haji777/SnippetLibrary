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


class SaveDialog(QtWidgets.QDialog):
    """Title + short description (+ context / tags) for a new snippet."""

    def __init__(self, app, context, contexts=None, node_count=0, parent=None):
        super(SaveDialog, self).__init__(parent)
        self.setWindowTitle("Save to Snippet Library")
        self.setMinimumWidth(460)
        profile = core.get_profile()

        header = QtWidgets.QLabel(
            "<span style='color:%s'>&#9679;</span> <b>%s</b> &nbsp; "
            "<span style='color:%s'>&#9632;</span> %s &nbsp; %d nodes"
            % (APP_COLORS.get(app, "#888"), app, profile["color"], profile["display"], node_count))
        self.title = QtWidgets.QLineEdit()
        self.title.setPlaceholderText("タイトル（ファイル名になります）")
        self.context = QtWidgets.QComboBox()
        self.context.addItems(contexts or [context])
        self.context.setEditable(bool(contexts))
        self.context.setCurrentText(context)
        self.context.setEnabled(bool(contexts))
        self.tags = QtWidgets.QLineEdit()
        self.tags.setPlaceholderText("tag1, tag2 ...")
        self.description = QtWidgets.QPlainTextEdit()
        self.description.setPlaceholderText("簡単な説明 / コメント")
        self.description.setMinimumHeight(110)
        root = QtWidgets.QLabel(core.library_root())
        root.setStyleSheet("color: gray;")
        root.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        form = QtWidgets.QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Context", self.context)
        form.addRow("Tags", self.tags)
        form.addRow("Description", self.description)
        form.addRow("Library", root)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(header)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.title.setFocus()

    def _accept(self):
        if not core.safe_name(self.title.text()):
            self.title.setFocus()
            return
        self.accept()

    def values(self):
        return {"title": self.title.text().strip(),
                "context": self.context.currentText().strip(),
                "tags": [t.strip() for t in self.tags.text().split(",") if t.strip()],
                "description": self.description.toPlainText().strip()}


def ask_save(app, context, contexts=None, node_count=0, parent=None):
    dialog = SaveDialog(app, context, contexts, node_count, parent)
    if _exec(dialog):
        return dialog.values()
    return None


class BrowserDialog(QtWidgets.QDialog):
    """Small in-app browser: works even when the viewer is not running."""

    COLUMNS = ("", "Date", "User", "Context", "Title", "Description", "Library")

    def __init__(self, app, on_load, parent=None):
        super(BrowserDialog, self).__init__(parent)
        self.app, self.on_load = app, on_load
        self.setWindowTitle("Snippet Library - %s" % app)
        self.resize(900, 520)
        self.items = []

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("filter...")
        self.crown = QtWidgets.QCheckBox("\U0001F451 殿堂入りのみ")
        self.mine = QtWidgets.QCheckBox("自分のみ")
        reload_btn = QtWidgets.QPushButton("Reload")
        viewer_btn = QtWidgets.QPushButton("Open Viewer")
        top = QtWidgets.QHBoxLayout()
        for w in (self.search, self.crown, self.mine, reload_btn, viewer_btn):
            top.addWidget(w)

        self.table = QtWidgets.QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)

        load_btn = QtWidgets.QPushButton("Load")
        load_btn.setDefault(True)
        close_btn = QtWidgets.QPushButton("Close")
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
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(5, 320)

    def load_current(self, *_):
        row = self.table.currentRow()
        if row < 0:
            return
        meta = self.table.item(row, 0).data(QtCore.Qt.UserRole)
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
