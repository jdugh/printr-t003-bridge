#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $(id -u) == 0 ]]; then echo 'Lancer sans sudo (sudo seulement pour apt et systemd)'; exit 1; fi
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pil fonts-dejavu-core bluez
python3 -m venv --system-site-packages .venv
# Pillow est fourni par apt, compatible armv6. Pas de compilation pip nécessaire.
.venv/bin/python -c 'from PIL import Image; print("Pillow:", Image.__version__)'
[[ -e .env ]] || cp .env.example .env
mkdir -p spool
chmod 700 spool
.venv/bin/python -m unittest discover -s tests -v
echo 'Installation terminée. Ajuster .env (TRANSPORT=dry-run ou usb).'
