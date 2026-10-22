# SPDX-License-Identifier: GPL-3.0-or-later
"""Service : connexion au démon disc-launcher, affichage, commandes Kodi.

Rien à régler dans Kodi : tout est dans la configuration de disc-launcher
(``~/.config/disc-launcher/config.toml``, sections ``[kodi]`` et
``[kodi.override]``).
"""
import queue
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui

from . import autoplay
from .client import Client
from .commands import Commands, Player
from .strings import L
from .ui import Panel

SHOW = "disc-launcher.show"
RETRY_S = 5


def log(msg, level=xbmc.LOGINFO):
    xbmc.log("[service.disc-launcher] %s" % msg, level)


def request_show():
    """Entrée du menu des programmes : demande au service d'afficher la liste."""
    xbmcgui.Window(10000).setProperty(SHOW, "1")


def wait_gui_ready(monitor, timeout=90):
    """Attend l'écran d'accueil (fin du démarrage, choix du profil…)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if xbmc.getCondVisibility("Window.IsActive(home)") and not xbmc.getCondVisibility("System.HasActiveModalDialog"):
            return not monitor.waitForAbort(1)
        if monitor.waitForAbort(1):
            return False
    return True


class Service(object):
    def __init__(self, monitor=None, client=None):
        self.monitor = monitor or xbmc.Monitor()
        self.inbox = queue.Queue()
        self.client = client or Client(self.inbox.put)
        self.player = Player(self._stream_stopped)
        self.panel = Panel(self.client.send, self._finished_choice)
        self.commands = Commands(self.client.send, self.player, self.panel)
        self.was_connected = False

    def hello(self):
        try:
            version = xbmcaddon.Addon("service.disc-launcher").getAddonInfo("version")
        except Exception:
            version = ""
        return {"kodi": xbmc.getInfoLabel("System.BuildVersion"), "addon": version}

    def _stream_stopped(self, ident, key):
        # Lecture du flux arrêtée dans Kodi : l'écoute s'arrête aussi.
        self.client.send({"type": "action", "id": ident, "key": key})

    def _finished_choice(self, m, choice):
        self.commands.finished_choice(m, choice)

    def dispatch(self, m):
        kind = m.get("type")
        if kind == "state":
            self.panel.on_state(m)
        elif kind == "_gone":
            log("disc-launcher déconnecté")
            self.panel.on_gone()
        elif not self.commands.handle(m):
            log("message inconnu : %s" % kind, xbmc.LOGDEBUG)

    def step(self, last_try):
        """Un tour de boucle ; renvoie l'heure du dernier essai de connexion."""
        now = time.time()
        if not self.client.connected and now - last_try >= RETRY_S:
            last_try = now
            if self.client.connect(self.hello()):
                log("connecté à disc-launcher")
                self.was_connected = True
        while True:
            try:
                self.dispatch(self.inbox.get_nowait())
            except queue.Empty:
                break
        win = xbmcgui.Window(10000)
        if win.getProperty(SHOW) == "1":
            win.clearProperty(SHOW)
            if not (self.client.connected and self.client.send({"type": "show"})):
                xbmcgui.Dialog().notification("disc-launcher", L(32001), xbmcgui.NOTIFICATION_WARNING, 6000)
        return last_try

    def run(self):
        ui = threading.Thread(target=self._ui, name="disc-launcher-ui")
        ui.start()
        last = 0.0
        try:
            while not self.monitor.abortRequested():
                last = self.step(last)
                if self.monitor.waitForAbort(0.2):
                    break
        finally:
            self.panel.stop()
            self.client.close()
            ui.join(5)

    def _ui(self):
        if not wait_gui_ready(self.monitor):
            return
        self.panel.modal((lambda d: autoplay.check(d),))
        self.panel.run(self.monitor)


def run():
    Service().run()
