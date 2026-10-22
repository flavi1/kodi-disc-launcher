# SPDX-License-Identifier: GPL-3.0-or-later
"""Connexion à la socket de contrôle du démon disc-launcher.

L'extension s'annonce par ``{"cmd": "attach-ui", "ui": "kodi"}`` puis la
connexion reste ouverte : une ligne JSON par message dans chaque sens.
Aucun port réseau : une socket Unix privée de l'utilisateur.
"""
import json
import os
import socket
import threading


def socket_path():
    """Même emplacement que disc-launcher : ``$XDG_RUNTIME_DIR/disc-launcher``,
    sinon ``/tmp/disc-launcher-<uid>``."""
    forced = os.environ.get("DISC_LAUNCHER_SOCKET")
    if forced:
        return forced
    uid = os.getuid()
    cands = []
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if rt:
        cands.append(os.path.join(rt, "disc-launcher", "control.sock"))
    cands.append("/run/user/%d/disc-launcher/control.sock" % uid)
    cands.append("/tmp/disc-launcher-%d/control.sock" % uid)
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


class Client(object):
    """``on_message(dict)`` est appelé depuis le fil de lecture ; la fin de la
    connexion arrive comme ``{"type": "_gone"}``."""

    def __init__(self, on_message, path=None):
        self.on_message = on_message
        self.path = path
        self.sock = None
        self.lock = threading.Lock()

    @property
    def connected(self):
        return self.sock is not None

    def connect(self, hello):
        path = self.path or socket_path()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
        except OSError:
            s.close()
            return False
        self.sock = s
        if not self.send({"cmd": "attach-ui", "ui": "kodi"}) or not self.send(dict(hello, type="hello")):
            self.close()
            return False
        threading.Thread(target=self._read, args=(s,), name="disc-launcher-read", daemon=True).start()
        return True

    def _read(self, s):
        buf = b""
        try:
            while True:
                data = s.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.on_message(json.loads(line.decode("utf-8", "replace")))
                    except ValueError:
                        pass
        except OSError:
            pass
        with self.lock:
            if self.sock is s:
                self.sock = None
        try:
            s.close()
        except OSError:
            pass
        self.on_message({"type": "_gone"})

    def send(self, obj):
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock:
            s = self.sock
            if s is None:
                return False
            try:
                s.sendall(data)
                return True
            except OSError:
                return False

    def close(self):
        with self.lock:
            s, self.sock = self.sock, None
        if s is not None:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()
