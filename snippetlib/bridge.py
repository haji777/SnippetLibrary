# -*- coding: utf-8 -*-
"""Viewer -> running Houdini/Nuke, without sockets.

Every DCC session registers itself in a machine local folder and polls an
inbox folder with a QTimer (main thread, so hou/nuke calls are safe):

    %LOCALAPPDATA%/SnippetLibrary/sessions/<app>_<pid>.json      heartbeat + scene name
    %LOCALAPPDATA%/SnippetLibrary/sessions/<app>_<pid>.inbox/    *.json requests
                                                              *.done  results

The viewer lists sessions with a fresh heartbeat and drops a request file.
"""

import os
import time

from . import core

HEARTBEAT_SEC = 10.0
ALIVE_SEC = 30.0
POLL_MS = 1500

_state = {"timer": None}


def _sessions_dir():
    return core.local_dir("sessions")


# ------------------------------------------------------------------ viewer side
def list_sessions(app=None):
    out, now = [], time.time()
    sdir = _sessions_dir()
    for fn in os.listdir(sdir):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(sdir, fn)
        info = core.read_json(path)
        if not info:
            continue
        if now - info.get("heartbeat", 0) > ALIVE_SEC:
            if now - info.get("heartbeat", 0) > 3600:  # crashed long ago: clean up
                _remove_session_files(path[:-5])
            continue
        if app and info.get("app") != app:
            continue
        out.append(info)
    return sorted(out, key=lambda s: s.get("started", 0))


def send_request(session_id, request, wait=8.0):
    """Drop a request into the session inbox and wait for the DCC's answer."""
    inbox = os.path.join(_sessions_dir(), session_id + ".inbox")
    if not os.path.isdir(inbox):
        return {"ok": False, "message": "セッションが見つかりません"}
    req = os.path.join(inbox, "%d_%d.json" % (int(time.time() * 1000), os.getpid()))
    core.write_json_atomic(req, request)
    done = req[:-5] + ".done"
    end = time.time() + wait
    while time.time() < end:
        if os.path.exists(done):
            result = core.read_json(done, {"ok": True, "message": ""})
            try:
                os.remove(done)
            except OSError:
                pass
            return result
        time.sleep(0.15)
    return {"ok": False, "pending": True,
            "message": "応答待ちタイムアウト。アプリ側でダイアログが開いていないか確認してください。"}


# ------------------------------------------------------------------ DCC side
def _remove_session_files(base):
    inbox = base + ".inbox"
    try:
        for fn in os.listdir(inbox):
            os.remove(os.path.join(inbox, fn))
        os.rmdir(inbox)
    except OSError:
        pass
    try:
        os.remove(base + ".json")
    except OSError:
        pass


def start(app, version, scene_name, handler):
    """Start polling (idempotent). handler(request dict) -> message string;
    scene_name() -> current scene file for display in the viewer."""
    if _state["timer"] is not None:
        return
    from .qtui import QtCore, QtWidgets
    qapp = QtWidgets.QApplication.instance()
    if qapp is None:  # batch mode (hython / nuke -t): nothing to load into
        return

    session_id = "%s_%d" % (app, os.getpid())
    base = os.path.join(_sessions_dir(), session_id)
    inbox = base + ".inbox"
    os.makedirs(inbox, exist_ok=True)
    started = time.time()
    last_beat = [0.0]

    def beat():
        try:
            scene = scene_name()
        except Exception:
            scene = ""
        core.write_json_atomic(base + ".json", {
            "id": session_id, "app": app, "pid": os.getpid(), "version": version,
            "scene": scene, "user": core.current_user(),
            "started": started, "heartbeat": time.time()})

    def poll():
        now = time.time()
        if now - last_beat[0] > HEARTBEAT_SEC:
            last_beat[0] = now
            try:
                beat()
            except OSError:
                pass
        try:
            names = sorted(f for f in os.listdir(inbox) if f.endswith(".json"))
        except OSError:
            return
        for fn in names:
            path = os.path.join(inbox, fn)
            request = core.read_json(path)
            try:
                os.remove(path)
            except OSError:
                continue
            if request is None:
                continue
            try:
                result = {"ok": True, "message": handler(request) or ""}
            except Exception as exc:  # report to the viewer instead of raising in the DCC
                result = {"ok": False, "message": "%s" % exc}
            try:
                core.write_json_atomic(path[:-5] + ".done", result)
            except OSError:
                pass

    timer = QtCore.QTimer(qapp)
    timer.setInterval(POLL_MS)
    timer.timeout.connect(poll)
    timer.start()
    _state["timer"] = timer
    qapp.aboutToQuit.connect(lambda: _remove_session_files(base))
    poll()
