#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $(id -u) != 0 ]] || { echo 'À lancer sans sudo'; exit 1; }
ROOT="$(pwd)"
USER_NAME="$(id -un)"
[[ -x .venv/bin/python ]] || { echo 'Lancer ./scripts/install.sh avant'; exit 1; }
# Accès usb/lp0 et RFCOMM si le compte appartient aux groupes concernés.
sudo usermod -aG lp,dialout "$USER_NAME"
sed -e "s|__USER__|$USER_NAME|g" -e "s|__WORKDIR__|$ROOT|g" systemd/printr-t003.service.template | sudo tee /etc/systemd/system/printr-t003.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now printr-t003
sudo systemctl status --no-pager printr-t003
printf '\nPour appliquer les nouveaux groupes à une session interactive : reconnectez-vous en SSH.\n'
