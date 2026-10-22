# SPDX-License-Identifier: GPL-3.0-or-later
"""« Disques et périphériques » dans Kodi.

Le démon envoie le même état que pour sa fenêtre du bureau :
``{visible, raise, title, empty, items: [{id, icon, title, lines, progress, actions, idle}]}``.
Ici : une liste des éléments (sautée s'il n'y en a qu'un d'actif), puis la
liste de ses actions. Les tâches en cours (dump, encodage…) ont aussi une
barre de progression discrète (DialogProgressBG).

Les fenêtres modales de Kodi sont bloquantes : elles s'ouvrent dans un fil à
part. Quand l'état change pendant qu'une liste est ouverte, elle est fermée
et rouverte à jour ; une explication (texte long) ou le menu de fin
d'encodage passent avant la liste.
"""
import collections
import json
import threading
import time

import xbmc
import xbmcgui

from .strings import L

# Icônes du thème de Kodi d'après les noms d'icônes freedesktop envoyés.
ICONS = (
    (("vinyl",), "DefaultMusicAlbums.png"),
    (("audio", "cdda", "music"), "DefaultCDDA.png"),
    (("photo", "camera", "image", "picture"), "DefaultPicture.png"),
    (("blu-ray", "dvd", "video"), "DefaultDVDFull.png"),
    (("cartridge", "game", "console", "joystick"), "DefaultProgram.png"),
    (("removable", "usb", "flash", "sd", "memory"), "DefaultRemovableDisk.png"),
    (("drive-optical",), "DefaultDVDEmpty.png"),
)


def icon_for(names):
    for name in (names or "").split(","):
        n = name.strip().lower()
        for keys, icon in ICONS:
            if any(k in n for k in keys):
                return icon
    return "DefaultHardDisk.png"


def signature(st):
    """Ce qui justifie de rouvrir la liste : éléments et actions (pas la
    progression ni les lignes des tâches, qui changent sans cesse)."""
    if not st:
        return ""
    out = []
    for it in st.get("items", []):
        busy = it.get("progress") is not None or it.get("id", "").startswith(("job:", "task:"))
        out.append((it.get("id"), it.get("title"), [a[0] for a in it.get("actions", [])],
                    None if busy else it.get("lines")))
    return json.dumps(out, sort_keys=True)


class Panel(object):
    def __init__(self, send, finished_choice, dialog=xbmcgui.Dialog, builtin=xbmc.executebuiltin,
                 progress_bg=xbmcgui.DialogProgressBG, video_playing=None):
        self.send, self.finished_choice = send, finished_choice
        self.dialog, self.builtin, self.progress_bg = dialog, builtin, progress_bg
        self.video_playing = video_playing or (lambda: xbmc.getCondVisibility("Player.HasVideo"))
        self.cond = threading.Condition()
        self.state = None
        self.version = 0
        self.modals = collections.deque()
        self.open = False
        self.forced = False
        # Après « Retour » : rien jusqu'au prochain état demandant l'affichage.
        self.hidden_at = -1
        # Après une action : liste rouverte au prochain état, ou au bout de 2 s.
        self.acted_at = -1
        self.acted_until = 0.0
        self.bgs = {}
        self.stopping = False

    # -- appelé par le fil principal ------------------------------------------
    def on_state(self, st):
        with self.cond:
            changed = signature(st) != signature(self.state)
            self.state = st
            self.version += 1
            if st.get("raise") or not st.get("visible"):
                self.hidden_at = -1
            if st.get("raise") and self.video_playing() and not self.open:
                # Film en cours : pas de fenêtre par-dessus, une notification suffit.
                self.hidden_at = self.version
                self._notify_items(st)
            if self.open and (changed or not st.get("visible")):
                self._force_close()
            self.cond.notify_all()
        self._update_bgs(st)

    def on_gone(self):
        with self.cond:
            self.state = None
            self.version += 1
            if self.open:
                self._force_close()
            self.cond.notify_all()
        self._update_bgs({"items": []})

    def modal(self, item):
        with self.cond:
            self.modals.append(item)
            if self.open:
                self._force_close()
            self.cond.notify_all()

    def stop(self):
        with self.cond:
            self.stopping = True
            if self.open:
                self._force_close()
            self.cond.notify_all()
        self._update_bgs({"items": []})

    # -- fil de l'interface ---------------------------------------------------
    def want_panel(self):
        st = self.state
        if not st or not st.get("visible"):
            return False
        if self.hidden_at >= 0 and self.version <= self.hidden_at:
            return False
        if self.acted_at >= 0 and self.version <= self.acted_at and time.time() < self.acted_until:
            return False
        return True

    def run(self, monitor):
        while not monitor.abortRequested():
            with self.cond:
                while not (self.stopping or self.modals or self.want_panel()):
                    self.cond.wait(0.5)
                    if monitor.abortRequested():
                        return
                if self.stopping:
                    return
                item = self.modals.popleft() if self.modals else None
            if item is not None:
                self._run_modal(item)
            else:
                self.show_once()

    def _run_modal(self, item):
        d = self.dialog()
        if item[0] == "text":
            d.textviewer(item[1] or "disc-launcher", item[2])
        elif item[0] == "finished":
            m = item[1]
            choices = [("play", L(32005)), ("open", L(32006)), ("close", L(32007))]
            i = d.select(L(32008, m.get("title", "")), [c[1] for c in choices])
            if 0 <= i < len(choices):
                self.finished_choice(m, choices[i][0])
        elif callable(item[0]):
            item[0](d)

    def show_once(self):
        """Affiche la liste ; renvoie ce qui s'est passé (pour les tests)."""
        with self.cond:
            st = self.state
            shown = self.version
            self.open, self.forced = True, False
        try:
            res = self._flow(st)
        finally:
            with self.cond:
                self.open = False
                forced = self.forced
        if forced:
            return ("forced",)
        if res[0] == "back":
            with self.cond:
                self.hidden_at = max(self.version, shown)
            self.send({"type": "hidden"})
        elif res[0] == "action":
            with self.cond:
                self.acted_at = self.version
                self.acted_until = time.time() + 2.0
            self.send({"type": "action", "id": res[1], "key": res[2]})
        return res

    def _flow(self, st):
        d = self.dialog()
        items = list(st.get("items", []))
        if not items:
            d.select(st.get("title", L(32000)), [st.get("empty", "")])
            return ("back",)
        active = [i for i in items if not i.get("idle")]
        direct = len(active) == 1 or len(items) == 1
        while True:
            if direct:
                item = active[0] if active else items[0]
            else:
                lis = []
                for it in items:
                    li = xbmcgui.ListItem(it.get("title", ""), " · ".join(it.get("lines", [])))
                    li.setArt({"icon": icon_for(it.get("icon")), "thumb": icon_for(it.get("icon"))})
                    lis.append(li)
                idx = d.select(st.get("title", L(32000)), lis, useDetails=True)
                if self.forced:
                    return ("forced",)
                if idx < 0:
                    return ("back",)
                item = items[idx]
            acts = item.get("actions", [])
            lis = []
            for n, a in enumerate(acts):
                li = xbmcgui.ListItem(a[1], " · ".join(item.get("lines", [])) if n == 0 else "")
                li.setArt({"icon": icon_for(item.get("icon"))})
                lis.append(li)
            if not lis:
                # Rien à faire (traitement en cours…) : les lignes, en lecture seule.
                lis = [xbmcgui.ListItem(l) for l in item.get("lines", [])] or [xbmcgui.ListItem(item.get("title", ""))]
                d.select(item.get("title", ""), lis)
                if self.forced:
                    return ("forced",)
                if direct:
                    return ("back",)
                continue
            idx = d.select(item.get("title", ""), lis, useDetails=True)
            if self.forced:
                return ("forced",)
            if idx < 0:
                if direct:
                    return ("back",)
                continue
            return ("action", item.get("id"), acts[idx][0])

    # -- interne ----------------------------------------------------------------
    def _force_close(self):
        self.forced = True
        self.builtin("Dialog.Close(selectdialog,true)")

    def _notify_items(self, st):
        active = [i for i in st.get("items", []) if not i.get("idle") and i.get("actions")]
        if active:
            xbmcgui.Dialog().notification(st.get("title", "disc-launcher"), active[0].get("title", ""),
                                          xbmcgui.NOTIFICATION_INFO, 6000)

    def _update_bgs(self, st):
        seen = set()
        for it in st.get("items", []):
            iid = it.get("id", "")
            if not iid.startswith(("job:", "task:")):
                continue
            seen.add(iid)
            pr = it.get("progress") or {}
            pct = int(round((pr.get("fraction") or 0) * 100))
            msg = " — ".join(x for x in [pr.get("text", "")] + list(it.get("lines", [])) if x)
            bg = self.bgs.get(iid)
            if bg is None:
                bg = self.progress_bg()
                bg.create(it.get("title", ""), msg)
                self.bgs[iid] = bg
            bg.update(pct, it.get("title", ""), msg)
        for iid in [k for k in self.bgs if k not in seen]:
            self.bgs.pop(iid).close()
