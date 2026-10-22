#!/bin/sh
# Construit l'archive installable dans Kodi (« Installer depuis un fichier zip ») :
# dist/service.disc-launcher-<version>.zip, dossier service.disc-launcher/ à la racine.
set -eu
cd "$(dirname "$0")"
id=service.disc-launcher
version=$(sed -n 's/.*<addon [^>]*version="\([^"]*\)".*/\1/p' addon.xml | head -n 1)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/$id" dist
cp -r addon.xml service.py default.py LICENSE README.md resources "$stage/$id/"
find "$stage/$id" -name '__pycache__' -prune -exec rm -rf {} +
rm -f "dist/$id-$version.zip"
(cd "$stage" && python3 -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', '.', '$id')" "$OLDPWD/dist/$id-$version")
echo "dist/$id-$version.zip"
