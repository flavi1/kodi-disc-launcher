# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulation minimale de l'API Python de Kodi (xbmc, xbmcgui, xbmcaddon, xbmcvfs)."""
import json
import os
import sys
import tempfile
import threading
import types

BUILTINS = []
RPC = []
WINDOW_PROPS = {}
NOTIFICATIONS = []
PROFILE = tempfile.mkdtemp(prefix="kodi-profile-")
SETTINGS = {"dvds.autorun": True, "audiocds.autoaction": 1}
CONDITIONS = {"Window.IsActive(home)": True}


class Monitor(object):
    def __init__(self):
        self._abort = threading.Event()

    def abortRequested(self):
        return self._abort.is_set()

    def waitForAbort(self, t=0):
        return self._abort.wait(t)

    def request_abort(self):
        self._abort.set()


class Player(object):
    def __init__(self):
        self.playing = ""
        self.played = []

    def play(self, item="", listitem=None):
        self.playing = item
        self.played.append(item)

    def stop(self):
        was = self.playing
        self.playing = ""
        if was:
            self.onPlayBackStopped()

    def isPlaying(self):
        return bool(self.playing)

    def getPlayingFile(self):
        return self.playing

    def onPlayBackStopped(self):
        pass


def executebuiltin(cmd, wait=False):
    BUILTINS.append(cmd)


def executeJSONRPC(req):
    r = json.loads(req)
    RPC.append(r)
    p = r.get("params", {})
    if r["method"] == "Settings.GetSettingValue":
        return json.dumps({"result": {"value": SETTINGS.get(p["setting"])}})
    if r["method"] == "Settings.SetSettingValue":
        SETTINGS[p["setting"]] = p["value"]
        return json.dumps({"result": True})
    return json.dumps({"result": None})


xbmc = types.ModuleType("xbmc")
xbmc.Monitor = Monitor
xbmc.Player = Player
xbmc.executebuiltin = executebuiltin
xbmc.executeJSONRPC = executeJSONRPC
xbmc.log = lambda msg, level=0: None
xbmc.sleep = lambda ms: None
xbmc.getCondVisibility = lambda c: CONDITIONS.get(c, False)
xbmc.getInfoLabel = lambda l: "21.1 (test)" if l == "System.BuildVersion" else ""
xbmc.LOGINFO, xbmc.LOGDEBUG, xbmc.LOGWARNING, xbmc.LOGERROR = 1, 0, 2, 3


class ListItem(object):
    def __init__(self, label="", label2=""):
        self.label, self.label2 = label, label2
        self.art = {}

    def setArt(self, art):
        self.art.update(art)

    def getLabel(self):
        return self.label


class Dialog(object):
    """Réponses scriptées : ``Dialog.answers`` (partagée) est consommée dans l'ordre."""
    answers = []
    log = []

    def _next(self, kind, *a, **k):
        Dialog.log.append((kind, a, k))
        return Dialog.answers.pop(0) if Dialog.answers else -1

    def select(self, heading, items, **k):
        return self._next("select", heading, [i.label if isinstance(i, ListItem) else i for i in items],
                          [i.label2 if isinstance(i, ListItem) else "" for i in items])

    def yesno(self, heading, message, **k):
        return self._next("yesno", heading, message)

    def textviewer(self, heading, text, *a):
        Dialog.log.append(("textviewer", (heading, text), {}))

    def notification(self, *a, **k):
        NOTIFICATIONS.append(a)


class DialogProgressBG(object):
    instances = []

    def __init__(self):
        self.updates = []
        self.closed = False
        DialogProgressBG.instances.append(self)

    def create(self, heading, message=""):
        self.heading = heading

    def update(self, percent=0, heading="", message=""):
        self.updates.append((percent, heading, message))

    def close(self):
        self.closed = True


class Window(object):
    def __init__(self, wid=0):
        pass

    def getProperty(self, k):
        return WINDOW_PROPS.get(k, "")

    def setProperty(self, k, v):
        WINDOW_PROPS[k] = v

    def clearProperty(self, k):
        WINDOW_PROPS.pop(k, None)


xbmcgui = types.ModuleType("xbmcgui")
xbmcgui.ListItem = ListItem
xbmcgui.Dialog = Dialog
xbmcgui.DialogProgressBG = DialogProgressBG
xbmcgui.Window = Window
xbmcgui.NOTIFICATION_INFO, xbmcgui.NOTIFICATION_WARNING, xbmcgui.NOTIFICATION_ERROR = "info", "warning", "error"


class Addon(object):
    def __init__(self, aid=""):
        pass

    def getLocalizedString(self, sid):
        return ""

    def getAddonInfo(self, k):
        return "0.1.0" if k == "version" else ""


xbmcaddon = types.ModuleType("xbmcaddon")
xbmcaddon.Addon = Addon

xbmcvfs = types.ModuleType("xbmcvfs")
xbmcvfs.translatePath = lambda p: p.replace("special://profile/", PROFILE + "/")

for name, mod in (("xbmc", xbmc), ("xbmcgui", xbmcgui), ("xbmcaddon", xbmcaddon), ("xbmcvfs", xbmcvfs)):
    sys.modules[name] = mod

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def reset():
    del BUILTINS[:]
    del RPC[:]
    del NOTIFICATIONS[:]
    WINDOW_PROPS.clear()
    Dialog.answers = []
    Dialog.log = []
    DialogProgressBG.instances = []
