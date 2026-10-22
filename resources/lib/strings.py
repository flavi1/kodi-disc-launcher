# SPDX-License-Identifier: GPL-3.0-or-later
"""Textes de l'extension (fichiers strings.po), avec repli anglais."""
import xbmcaddon

DEFAULTS = {
    32000: 'Disks & Devices',
    32001: 'disc-launcher is not running (its daemon cannot be reached).',
    32002: 'Kodi also reacts to discs by itself: [B]{0}[/B].[CR][CR]disc-launcher already offers its actions on insertion; both would react at the same time. Turn this off in Kodi?',
    32003: 'Turn off',
    32004: 'Keep',
    32005: 'Play',
    32006: 'Open the folder',
    32007: 'Close',
    32008: 'Done: {0}',
    32009: 'Connected to disc-launcher',
    32010: 'automatic DVD playback',
    32011: 'action on audio CD insertion',
    32012: 'Kodi settings updated',
    32013: 'Back',
}


def L(sid, *args):
    try:
        text = xbmcaddon.Addon("service.disc-launcher").getLocalizedString(sid)
    except Exception:  # hors de Kodi (tests)
        text = ""
    text = text or DEFAULTS.get(sid, "")
    return text.format(*args) if args else text
