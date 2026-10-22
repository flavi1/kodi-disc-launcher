# SPDX-License-Identifier: GPL-3.0-or-later
"""Commandes Kodi envoyées par disc-launcher (surcharges) : lecture,
fenêtres, bibliothèque, arrêt de la lecture avant éjection."""
import xbmc
import xbmcgui

WINDOWS = {"videos": "Videos", "music": "Music", "pictures": "Pictures"}
# Lecture de disque par Kodi, sans chemin de fichier local.
DISC_PREFIXES = ("dvd://", "bluray://", "cdda://", "iso9660://", "udf://")


def quote(path):
    return '"%s"' % path.replace("\\", "\\\\").replace('"', '\\"')


def folder(path):
    return path.rstrip("/") + "/"


class Player(xbmc.Player):
    """Lecture lancée pour disc-launcher (flux d'écoute du vinyle) : si
    l'utilisateur l'arrête dans Kodi, l'écoute s'arrête aussi."""

    def __init__(self, on_stopped):
        xbmc.Player.__init__(self)
        self.on_stopped = on_stopped
        self.ours = None          # (fichier, id, clé d'action à l'arrêt)
        self.stopping = False

    def start(self, file, title, ident, stop_key):
        li = xbmcgui.ListItem(title or "")
        self.ours = (file, ident, stop_key) if ident and stop_key else None
        self.play(file, li)

    def stop_ours(self, match):
        """Arrête la lecture si elle correspond (sans prévenir disc-launcher)."""
        if self.isPlaying() and (not match or match in self.playing_file()):
            self.stopping = True
            self.ours = None
            self.stop()

    def playing_file(self):
        try:
            return self.getPlayingFile() if self.isPlaying() else ""
        except RuntimeError:
            return ""

    def _ended(self):
        ours, self.ours = self.ours, None
        if self.stopping:
            self.stopping = False
            return
        if ours:
            self.on_stopped(ours[1], ours[2])

    def onPlayBackStopped(self):
        self._ended()

    def onPlayBackEnded(self):
        self._ended()

    def onPlayBackError(self):
        self._ended()


class Commands(object):
    def __init__(self, send, player, ui, builtin=xbmc.executebuiltin, sleep=xbmc.sleep):
        self.send, self.player, self.ui = send, player, ui
        self.builtin, self.sleep = builtin, sleep

    def handle(self, m):
        fn = getattr(self, "c_" + m.get("type", "").replace("-", "_"), None)
        if fn is None:
            return False
        fn(m)
        return True

    def c_play(self, m):
        self.player.start(m["file"], m.get("title", ""), m.get("id"), m.get("stop_key"))

    def c_play_disc(self, m):
        self.builtin("PlayDisc")

    def c_play_album(self, m):
        self.builtin("PlayMedia(%s,isdir)" % quote(folder(m["path"])))

    def c_stop(self, m):
        match = m.get("match")
        if match:
            self.player.stop_ours(match)
        elif self.player.isPlaying():
            self.player.stop()

    def c_stop_device(self, m):
        """Arrête la lecture si elle utilise ce disque, puis acquitte."""
        playing = self.player.playing_file()
        prefixes = list(DISC_PREFIXES) + [m.get("device", "")] + list(m.get("paths") or [])
        if playing and any(p and playing.startswith(p) for p in prefixes):
            self.player.stop()
            self.sleep(1500)
        self.send({"type": "done", "req": m.get("req")})

    def c_open(self, m):
        window = WINDOWS.get(m.get("window"), "Videos")
        self.builtin("ActivateWindow(%s,%s,return)" % (window, quote(folder(m["path"]))))

    def c_library(self, m):
        kind = "music" if m.get("kind") == "music" else "video"
        self.builtin("UpdateLibrary(%s,%s)" % (kind, quote(folder(m["path"]))))

    def c_notify(self, m):
        icon = xbmcgui.NOTIFICATION_ERROR if m.get("error") else xbmcgui.NOTIFICATION_INFO
        xbmcgui.Dialog().notification(m.get("title", "disc-launcher"), m.get("message", ""), icon, 8000 if m.get("error") else 5000)

    def c_text(self, m):
        self.ui.modal(("text", m.get("title", ""), m.get("text", "")))

    def c_finished(self, m):
        self.ui.modal(("finished", m))

    # Fin d'un encodage (menu de fin) : lancé par l'interface.
    def finished_choice(self, m, choice):
        path, kind, fold = m.get("path", ""), m.get("kind", "video"), m.get("folder") or m.get("path", "")
        if choice == "play":
            if kind == "music":
                self.c_play_album({"path": path or fold})
            else:
                self.player.start(path, m.get("title", ""), None, None)
        elif choice == "open":
            self.c_open({"window": "music" if kind == "music" else "videos", "path": fold})
