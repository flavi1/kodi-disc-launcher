# SPDX-License-Identifier: GPL-3.0-or-later
"""L'extension face au vrai démon disc-launcher (platine vinyle simulée).

    DISC_LAUNCHER_BIN=/chemin/vers/disc-launcher/target/debug python3 -m unittest discover -s tests

Sans DISC_LAUNCHER_BIN, le test est ignoré."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

import kodi_mock
from kodi_mock import Dialog, reset

BIN = os.environ.get("DISC_LAUNCHER_BIN", "")

FAKE_VINYLRIP = r'''#!/usr/bin/env python3
import json, sys
a = sys.argv[1:]
def out(e):
    print(json.dumps(e), flush=True)
if "listen" in a:
    out({"event": "listening", "on": True, "url": "http://127.0.0.1:9/vinyl.wav"})
    sys.stdin.read()
elif "session" in a:
    out({"event": "ready", "job": "/j"})
    for line in sys.stdin:
        c = json.loads(line)
        if c.get("cmd") == "finish":
            out({"event": "error", "message": "flac", "stage": "encode", "help": "Reprendre :\n  vinylrip process /j"})
            break
        if c.get("cmd") == "start_face":
            out({"event": "recording", "face": "A"})
        if c.get("cmd") == "stop_face":
            out({"event": "face_done", "face": "A", "overruns": 0})
'''


@unittest.skipUnless(BIN and os.path.exists(os.path.join(BIN, "disc-launcherd")), "DISC_LAUNCHER_BIN non défini")
class WithDaemon(unittest.TestCase):
    def setUp(self):
        reset()
        self.root = tempfile.mkdtemp(prefix="kdl-")
        home, run, fake = (os.path.join(self.root, x) for x in ("home", "run", "bin"))
        for d in (home, run, fake, os.path.join(home, ".config/vinylrip")):
            os.makedirs(d, exist_ok=True)
        os.chmod(run, 0o700)
        with open(os.path.join(home, ".config/vinylrip/config.toml"), "w") as f:
            f.write('device = "Device"\n')
        with open(os.path.join(fake, "vinylrip"), "w") as f:
            f.write(FAKE_VINYLRIP)
        os.chmod(os.path.join(fake, "vinylrip"), 0o755)
        cards = os.path.join(self.root, "cards")
        with open(cards, "w") as f:
            f.write(" 1 [Device         ]: USB-Audio - USB Audio CODEC\n")
        env = dict(os.environ, HOME=home, XDG_RUNTIME_DIR=run, XDG_CONFIG_HOME=os.path.join(home, ".config"),
                   PATH="%s:%s:/usr/bin:/bin" % (fake, BIN), DISC_LAUNCHER_ASOUND_CARDS=cards, DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent",
                   DISC_LAUNCHER_SYSFS_BLOCK=os.path.join(self.root, "noblock"))
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        self.daemon = subprocess.Popen([os.path.join(BIN, "disc-launcherd"), "--foreground"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sock = os.path.join(run, "disc-launcher", "control.sock")
        for _ in range(100):
            if os.path.exists(self.sock):
                break
            time.sleep(0.05)

    def tearDown(self):
        self.daemon.terminate()
        self.daemon.wait(10)
        shutil.rmtree(self.root, ignore_errors=True)

    def wait(self, svc, pred, n=100):
        last = 0
        for _ in range(n):
            last = svc.step(last)
            if pred():
                return True
            time.sleep(0.05)
        return False

    def vinyl(self, svc):
        st = svc.panel.state or {}
        return next((i for i in st.get("items", []) if i.get("id") == "vinyl:Device"), None)

    def test_listen_and_session_through_kodi(self):
        from resources.lib.client import Client
        from resources.lib.service import Service
        svc = Service()
        svc.client = Client(svc.inbox.put, path=self.sock)
        svc.panel.send = svc.client.send
        svc.commands.send = svc.client.send
        self.assertTrue(self.wait(svc, lambda: self.vinyl(svc) is not None), "platine absente de l'état reçu")
        self.assertEqual([a[0] for a in self.vinyl(svc)["actions"]], ["listen", "encode"])
        # « Écouter » choisi dans Kodi : le flux est joué par le lecteur de Kodi.
        Dialog.answers = [0]
        self.assertEqual(svc.panel.show_once(), ("action", "vinyl:Device", "listen"))
        self.assertTrue(self.wait(svc, lambda: svc.player.getPlayingFile().endswith("/vinyl.wav")))
        # Arrêt dans Kodi : l'écoute s'arrête aussi.
        svc.player.stop()
        self.assertTrue(self.wait(svc, lambda: [a[0] for a in (self.vinyl(svc) or {}).get("actions", [])] == ["listen", "encode"]))
        # Encoder : session pilotée ; l'échec affiche l'explication de vinylrip.
        svc.client.send({"type": "action", "id": "vinyl:Device", "key": "encode"})
        acts = lambda: [a[0] for a in (self.vinyl(svc) or {}).get("actions", [])]
        self.assertTrue(self.wait(svc, lambda: acts() == ["vs:start", "vs:cancel"]))
        for key, then in (("vs:start", ["vs:stop", "vs:listen", "vs:cancel"]), ("vs:stop", ["vs:start", "vs:finish", "vs:cancel"])):
            svc.client.send({"type": "action", "id": "vinyl:Device", "key": key})
            self.assertTrue(self.wait(svc, lambda: acts() == then), key)
        svc.client.send({"type": "action", "id": "vinyl:Device", "key": "vs:finish"})
        self.assertTrue(self.wait(svc, lambda: any(m[0] == "text" for m in svc.panel.modals)))
        text = next(m for m in svc.panel.modals if m[0] == "text")
        self.assertIn("vinylrip process /j", text[2])
        svc.client.close()


if __name__ == "__main__":
    unittest.main()
