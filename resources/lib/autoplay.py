# SPDX-License-Identifier: GPL-3.0-or-later
"""Lecture automatique de Kodi : à l'insertion d'un disque, Kodi peut lire
le DVD ou le CD audio lui-même, en même temps que disc-launcher propose ses
actions. Au démarrage, l'extension le vérifie et propose une seule fois de
désactiver ces réglages (modifiés de l'intérieur de Kodi, sans contrôle à
distance à activer)."""
import json
import os

import xbmc
import xbmcvfs

from .strings import L

# (identifiant du réglage, valeur « désactivé », texte)
SETTINGS = (("dvds.autorun", False, 32010), ("audiocds.autoaction", 0, 32011))


def rpc(method, params, execute=xbmc.executeJSONRPC):
    req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        return json.loads(execute(json.dumps(req))).get("result")
    except (ValueError, TypeError):
        return None


def active(execute=xbmc.executeJSONRPC):
    """Réglages actifs : liste de (identifiant, valeur désactivée, texte)."""
    out = []
    for sid, off, txt in SETTINGS:
        r = rpc("Settings.GetSettingValue", {"setting": sid}, execute)
        if r is not None and r.get("value") not in (None, off):
            out.append((sid, off, txt))
    return out


def disable(found, execute=xbmc.executeJSONRPC):
    for sid, off, _ in found:
        rpc("Settings.SetSettingValue", {"setting": sid, "value": off}, execute)


def state_file():
    d = xbmcvfs.translatePath("special://profile/addon_data/service.disc-launcher/")
    return os.path.join(d, "state.json")


def load_state(path=None):
    try:
        with open(path or state_file(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st, path=None):
    p = path or state_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(st, f)


def check(dialog, execute=xbmc.executeJSONRPC, path=None):
    """Propose une fois de désactiver la lecture automatique de Kodi."""
    st = load_state(path)
    if st.get("autoplay_asked"):
        return
    found = active(execute)
    if not found:
        return
    what = ", ".join(L(t) for _, _, t in found)
    yes = dialog.yesno("disc-launcher", L(32002, what), nolabel=L(32004), yeslabel=L(32003))
    if yes:
        disable(found, execute)
        dialog.notification("disc-launcher", L(32012))
    st["autoplay_asked"] = True
    save_state(st, path)
