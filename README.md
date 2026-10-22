# service.disc-launcher

Extension Kodi qui fait de Kodi l'interface de [disc-launcher](https://github.com/flavi1/disc-launcher).

Elle remplace `script.disc.import` (import d'un disque avec encbd) et
[vinylrip-kodi](https://github.com/flavi1/vinylrip-kodi). Le travail reste fait par disc-launcher,
[encbd](https://github.com/flavi1/encbd) et [vinylrip](https://github.com/flavi1/vinylrip) ;
l'extension n'est qu'un affichage, et le relais de Kodi pour la lecture.

## Ce qu'elle fait

Tant que Kodi tourne avec l'extension, en fenêtre comme en plein écran :

- à l'insertion d'un disque (CD audio, DVD, Blu-ray, jeu), d'une cartouche, d'une clé USB, ou au
  branchement d'une platine vinyle, les propositions de disc-launcher s'affichent dans Kodi. Un seul
  périphérique actif : ses actions directement ; plusieurs : leur liste d'abord ;
- les tâches en cours (dump, encodage encbd…) ont une barre de progression discrète, avec
  « Annuler » dans la liste ;
- les notifications de disc-launcher passent par Kodi ;
- certaines actions se font dans Kodi au lieu du bureau :
  - **lecture du disque** et de la copie encodée ;
  - **dossiers** dans les fenêtres Vidéos, Musique ou Images ;
  - **encodage encbd** en arrière-plan, puis bibliothèque mise à jour et menu
    **Lire / Ouvrir le dossier / Fermer** ;
  - **éjection** après l'arrêt de la lecture de ce disque ;
  - **vinyle** : écoute par la sortie audio de Kodi, et encodage pas à pas
    (**Démarrer la face A**, **Arrêter la face**, **Écouter**, **Terminer et traiter**, choix de l'édition).
    En cas d'échec, l'explication de vinylrip s'affiche en entier, avec défilement : ce qui est
    conservé, la commande de reprise, l'import dans Audacity.

Un film est en cours : pas de fenêtre par-dessus, une notification seulement. L'entrée
**disc-launcher** des programmes de Kodi (ou `RunScript(service.disc-launcher)`, pour un bouton de
skin ou une touche) affiche la liste à tout moment, comme l'icône de la zone de notification du bureau.

Au premier démarrage, si Kodi lit lui-même les DVD ou les CD audio à l'insertion, l'extension
propose une fois de désactiver ces réglages : sinon Kodi et disc-launcher réagiraient en même temps.

## Réglages

Aucun dans Kodi : tout est dans la configuration de disc-launcher
(`~/.config/disc-launcher/config.toml`), sections `[kodi]` et `[kodi.override]`. Toutes les
surcharges sont actives par défaut ; on les désactive une à une (voir le README de disc-launcher) :

```toml
[kodi.override]
play-disc = false        # lire les disques avec le lecteur de [media], même sous Kodi
```

## Fonctionnement

L'extension se connecte à la socket de contrôle du démon disc-launcher
(`$XDG_RUNTIME_DIR/disc-launcher/control.sock`) et y reste connectée : aucun port réseau, aucun
contrôle à distance à activer dans Kodi. Kodi doit donc tourner sous le même utilisateur que
disc-launcher (bureau ordinaire ; pas LibreELEC). Si le démon s'arrête ou redémarre, l'extension
se reconnecte d'elle-même ; si Kodi se ferme, disc-launcher revient à sa fenêtre du bureau.
`disc-launcher doctor` indique si l'extension est connectée.

Le protocole (une ligne JSON par message) est décrit en tête de `src/kodi.rs` dans disc-launcher.

## Installation

Prérequis : disc-launcher (dont le démon tourne dans la session), Kodi 19 ou plus récent, Linux.

```sh
./build-zip.sh        # → dist/service.disc-launcher-<version>.zip
```

Puis dans Kodi : *Extensions › Installer depuis un fichier zip*. Pour le développement, un lien
symbolique suffit : `ln -s "$PWD" ~/.kodi/addons/service.disc-launcher`, puis redémarrer Kodi.

Désinstallez `script.disc.import` et vinylrip-kodi : ils réagiraient eux aussi aux disques et à la platine.

## Tests

```sh
python3 -m unittest discover -s tests
# avec le vrai démon (platine simulée) :
DISC_LAUNCHER_BIN=/chemin/vers/disc-launcher/target/debug python3 -m unittest discover -s tests
```

L'API Python de Kodi est simulée (`tests/kodi_mock.py`).

## Licence

GPL-3.0-or-later. Voir `LICENSE`.
