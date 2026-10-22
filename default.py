# SPDX-License-Identifier: GPL-3.0-or-later
"""Entrée « disc-launcher » des programmes de Kodi (et RunScript(service.disc-launcher)) :
affiche « Disques et périphériques », comme un clic sur l'icône du bureau."""
from resources.lib import service

if __name__ == "__main__":
    service.request_show()
