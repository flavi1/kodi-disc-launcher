# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests de l'extension avec une API Kodi simulée : python3 -m unittest discover -s tests"""
import json
import os
import socket
import tempfile
import threading
import time
import unittest

import kodi_mock  # noqa: F401  (installe les faux modules Kodi)
from kodi_mock import BUILTINS, RPC, Dialog, DialogProgressBG, reset

from resources.lib import autoplay
from resources.lib.commands import Commands, Player
from resources.lib.ui import Panel, icon_for


def state(items, visible=True, raise_=True):
    return {"type": "state", "visible": visible, "raise": raise_, "title": "Disques et périphériques",
            "empty": "Aucun disque ni périphérique", "items": items}


SR0 = {"id": "/dev/sr0", "icon": "media-optical-blu-ray", "title": "Blu-ray vidéo — AVATAR",
       "lines": ["Lecteur : LG (sr0)", "Avatar (2009)  [TheDiscDB]"],
       "actions": [["play-disc", "Lire le disque"], ["encode-disc", "Encoder (encbd)"], ["eject", "Éjecter"]]}
SR1_IDLE = {"id": "/dev/sr1", "icon": "drive-optical", "title": "Lecteur optique (sr1) — vide", "lines": [],
            "actions": [["open-tray", "Ouvrir le plateau"]], "idle": True}
USB = {"id": "/dev/sdb1", "icon": "drive-removable-media-usb", "title": "Volume USB — MA CLE", "lines": ["Monté sur /media/u/MA CLE"],
       "actions": [["open-files", "Ouvrir"], ["unmount", "Démonter"]]}
TASK = {"id": "task:1", "icon": "media-eject", "title": "Encodage : Avatar", "lines": ["3 min 02 s", "Encoding 42%"],
        "progress": {"fraction": 0.42, "text": "42 %"}, "actions": [["cancel", "Annuler"]]}


class PanelTests(unittest.TestCase):
    def setUp(self):
        reset()
        self.sent = []
        self.panel = Panel(self.sent.append, lambda m, c: None, video_playing=lambda: False)

    def test_single_active_item_goes_straight_to_its_actions(self):
        self.panel.on_state(state([SR0, SR1_IDLE]))
        self.assertTrue(self.panel.want_panel())
        Dialog.answers = [1]
        self.assertEqual(self.panel.show_once(), ("action", "/dev/sr0", "encode-disc"))
        kind, (heading, labels, label2), _ = Dialog.log[0]
        self.assertEqual(heading, "Blu-ray vidéo — AVATAR")
        self.assertEqual(labels, ["Lire le disque", "Encoder (encbd)", "Éjecter"])
        self.assertIn("Avatar (2009)", label2[0])
        self.assertEqual(self.sent, [{"type": "action", "id": "/dev/sr0", "key": "encode-disc"}])
        # Pas de réouverture immédiate : on attend l'état suivant du démon.
        self.assertFalse(self.panel.want_panel())
        self.panel.on_state(state([SR0, SR1_IDLE], raise_=False))
        self.assertTrue(self.panel.want_panel())

    def test_several_items_then_back(self):
        self.panel.on_state(state([SR0, USB, TASK]))
        Dialog.answers = [1, -1, -1]          # clé USB, retour, retour
        self.assertEqual(self.panel.show_once(), ("back",))
        self.assertEqual(Dialog.log[0][1][1], ["Blu-ray vidéo — AVATAR", "Volume USB — MA CLE", "Encodage : Avatar"])
        self.assertEqual(Dialog.log[1][1][1], ["Ouvrir", "Démonter"])
        self.assertEqual(self.sent, [{"type": "hidden"}])
        self.assertFalse(self.panel.want_panel())
        self.panel.on_state(state([SR0, USB, TASK], visible=False, raise_=False))
        self.panel.on_state(state([SR0, USB, TASK]))
        self.assertTrue(self.panel.want_panel())

    def test_progress_bar_for_tasks(self):
        self.panel.on_state(state([SR0, TASK], visible=False))
        bg = DialogProgressBG.instances[0]
        self.assertEqual(bg.updates[-1][0], 42)
        self.assertIn("Encoding 42%", bg.updates[-1][2])
        self.panel.on_state(state([SR0], visible=False))
        self.assertTrue(bg.closed)

    def test_change_while_open_reopens(self):
        self.panel.on_state(state([SR0]))
        self.panel.open = True
        self.panel.on_state(state([SR0, USB]))
        self.assertTrue(self.panel.forced)
        self.assertIn("Dialog.Close(selectdialog,true)", BUILTINS)
        # La progression seule ne rouvre pas la liste.
        del BUILTINS[:]
        self.panel.forced = False
        t2 = dict(TASK, progress={"fraction": 0.5, "text": "50 %"}, lines=["4 min"])
        self.panel.on_state(state([SR0, USB, TASK]))
        self.panel.forced = False
        del BUILTINS[:]
        self.panel.on_state(state([SR0, USB, t2]))
        self.assertFalse(self.panel.forced)

    def test_no_window_over_a_film(self):
        p = Panel(self.sent.append, lambda m, c: None, video_playing=lambda: True)
        p.on_state(state([SR0]))
        self.assertFalse(p.want_panel())
        self.assertTrue(kodi_mock.NOTIFICATIONS)

    def test_icons(self):
        self.assertEqual(icon_for("media-optical-audio,disc-launcher-fallback-audio-cd"), "DefaultCDDA.png")
        self.assertEqual(icon_for("drive-removable-media-usb"), "DefaultRemovableDisk.png")
        self.assertEqual(icon_for("disc-launcher-fallback-vinyl"), "DefaultMusicAlbums.png")
        self.assertEqual(icon_for("inconnu"), "DefaultHardDisk.png")


class CommandTests(unittest.TestCase):
    def setUp(self):
        reset()
        self.sent = []
        self.stopped = []
        self.player = Player(lambda i, k: self.stopped.append((i, k)))
        self.modals = []
        ui = type("UI", (), {"modal": lambda s, m: self.modals.append(m)})()
        self.c = Commands(self.sent.append, self.player, ui)

    def test_builtins(self):
        self.c.handle({"type": "play-disc", "device": "/dev/sr0"})
        self.c.handle({"type": "open", "window": "music", "path": "/run/media/u/CLE"})
        self.c.handle({"type": "library", "kind": "video", "path": "/home/u/Vidéos"})
        self.c.handle({"type": "play-album", "path": "/home/u/Musique/A/B"})
        self.assertEqual(BUILTINS, ["PlayDisc", 'ActivateWindow(Music,"/run/media/u/CLE/",return)',
                                    'UpdateLibrary(video,"/home/u/Vidéos/")', 'PlayMedia("/home/u/Musique/A/B/",isdir)'])
        self.assertFalse(self.c.handle({"type": "inconnu"}))

    def test_stream_stopped_in_kodi_stops_listening(self):
        self.c.handle({"type": "play", "file": "http://127.0.0.1:5/vinyl.wav", "title": "Vinyle", "id": "vinyl:Device", "stop_key": "stop-listen"})
        self.assertEqual(self.player.getPlayingFile(), "http://127.0.0.1:5/vinyl.wav")
        self.player.stop()                       # l'utilisateur arrête dans Kodi
        self.assertEqual(self.stopped, [("vinyl:Device", "stop-listen")])
        # Arrêt demandé par disc-launcher : pas de renvoi.
        self.c.handle({"type": "play", "file": "http://127.0.0.1:5/vinyl.wav", "id": "vinyl:Device", "stop_key": "stop-listen"})
        self.c.handle({"type": "stop", "match": "/vinyl.wav"})
        self.assertEqual(len(self.stopped), 1)
        self.assertFalse(self.player.isPlaying())

    def test_stop_device_only_if_playing_it(self):
        self.player.play("/home/u/film.mkv")
        self.c.handle({"type": "stop-device", "device": "/dev/sr0", "paths": ["/run/media/u/AVATAR"], "req": 3})
        self.assertTrue(self.player.isPlaying())
        self.player.play("bluray://udf%3a%2f%2f/BDMV/PLAYLIST/00800.mpls")
        self.c.handle({"type": "stop-device", "device": "/dev/sr0", "paths": [], "req": 4})
        self.assertFalse(self.player.isPlaying())
        self.assertEqual(self.sent, [{"type": "done", "req": 3}, {"type": "done", "req": 4}])

    def test_text_and_finished_are_modal(self):
        self.c.handle({"type": "text", "title": "Vinyle", "text": "Reprendre :\n  vinylrip process /j"})
        self.c.handle({"type": "finished", "title": "Avatar", "kind": "video", "path": "/v/Avatar (2009).mkv", "folder": "/v"})
        self.assertEqual(self.modals[0][0], "text")
        self.c.finished_choice(self.modals[1][1], "play")
        self.assertEqual(self.player.getPlayingFile(), "/v/Avatar (2009).mkv")
        self.c.finished_choice({"kind": "music", "path": "/m/A/B", "folder": "/m/A/B"}, "open")
        self.assertEqual(BUILTINS[-1], 'ActivateWindow(Music,"/m/A/B/",return)')


class AutoplayTests(unittest.TestCase):
    def setUp(self):
        reset()
        kodi_mock.SETTINGS.update({"dvds.autorun": True, "audiocds.autoaction": 1})
        self.path = os.path.join(tempfile.mkdtemp(), "state.json")

    def test_offer_once_and_disable(self):
        Dialog.answers = [True]
        autoplay.check(Dialog(), path=self.path)
        self.assertEqual(kodi_mock.SETTINGS, {"dvds.autorun": False, "audiocds.autoaction": 0})
        self.assertEqual(Dialog.log[0][0], "yesno")
        Dialog.log = []
        kodi_mock.SETTINGS["dvds.autorun"] = True
        autoplay.check(Dialog(), path=self.path)    # déjà demandé : plus de question
        self.assertEqual(Dialog.log, [])

    def test_keep(self):
        Dialog.answers = [False]
        autoplay.check(Dialog(), path=self.path)
        self.assertTrue(kodi_mock.SETTINGS["dvds.autorun"])
        with open(self.path) as f:
            self.assertTrue(json.load(f)["autoplay_asked"])

    def test_nothing_active(self):
        kodi_mock.SETTINGS.update({"dvds.autorun": False, "audiocds.autoaction": 0})
        autoplay.check(Dialog(), path=self.path)
        self.assertEqual(Dialog.log, [])


class FakeDaemon(object):
    """Socket de contrôle simulée : accepte une connexion, garde ce qu'elle reçoit."""

    def __init__(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "control.sock")
        self.srv = socket.socket(socket.AF_UNIX)
        self.srv.bind(self.path)
        self.srv.listen(1)
        self.received = []
        self.conn = None
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        self.conn, _ = self.srv.accept()
        f = self.conn.makefile("r", encoding="utf-8")
        for line in f:
            self.received.append(json.loads(line))

    def send(self, obj):
        self.conn.sendall((json.dumps(obj) + "\n").encode())

    def wait(self, pred, n=50):
        for _ in range(n):
            if pred():
                return True
            time.sleep(0.05)
        return False


class ServiceTests(unittest.TestCase):
    def test_protocol_with_a_daemon(self):
        reset()
        from resources.lib.client import Client
        from resources.lib.service import Service
        d = FakeDaemon()
        svc = Service(client=None)
        svc.client = Client(svc.inbox.put, path=d.path)
        svc.panel.send = svc.client.send
        svc.commands.send = svc.client.send
        last = svc.step(0)
        self.assertTrue(d.wait(lambda: len(d.received) >= 2))
        self.assertEqual(d.received[0], {"cmd": "attach-ui", "ui": "kodi"})
        self.assertEqual(d.received[1]["type"], "hello")
        self.assertEqual(d.received[1]["kodi"], "21.1 (test)")
        d.send(state([SR0]))
        d.send({"type": "play-disc", "device": "/dev/sr0"})
        self.assertTrue(d.wait(lambda: not svc.inbox.empty()))
        time.sleep(0.1)
        svc.step(last)
        self.assertEqual(BUILTINS, ["PlayDisc"])
        self.assertTrue(svc.panel.want_panel())
        Dialog.answers = [2]
        svc.panel.show_once()
        self.assertTrue(d.wait(lambda: {"type": "action", "id": "/dev/sr0", "key": "eject"} in d.received))
        # Entrée « disc-launcher » du menu des programmes.
        kodi_mock.WINDOW_PROPS["disc-launcher.show"] = "1"
        svc.step(last)
        self.assertTrue(d.wait(lambda: {"type": "show"} in d.received))
        # Démon arrêté : déconnexion propre.
        d.conn.shutdown(socket.SHUT_RDWR)
        self.assertTrue(d.wait(lambda: not svc.client.connected))
        svc.client.close()
        d.conn.close()
        d.srv.close()


if __name__ == "__main__":
    unittest.main()
