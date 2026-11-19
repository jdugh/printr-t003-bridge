# PrintR → ORGSTA T003 : passerelle TCP 9100 (prototype v0.1)

Projet Python **neuf**, indépendant de CUPS et de `emupos` ; testé localement en simulation. Pour Raspberry Pi Zero W, OS 32 bits. Aucun pilote constructeur requis.

## Architecture

`Printr (ESC/POS)` → `TCP:9100` → **décodeur ESC/POS** → `PNG 576 px` → découpage `600 px` → **TSPL2** → `USB /dev/usb/lp0` ou **Bluetooth RFCOMM**.

**Important :** PrintR émet de l'ESC/POS et non un PNG. Le décodeur fourni supporte surtout `GS v 0` (raster), `ESC *` (bitmap colonnes), texte simple, alignement, styles, et coupes (`GS V`) remplacées par une ligne pointillée avec ciseaux, puisque la T003 n'a pas de massicot ; la coupe finale du ticket n'est pas dessinée. Des variantes (`GS ( L`, QR, codes-barres, commandes de positions, encodages) peuvent nécessiter des adaptations. **Ce n'est pas un émulateur ESC/POS exhaustif**. Les commandes inconnues déclenchent une erreur dans les logs, jamais une impression volontairement approximative. Pour un premier ticket réel, tester une impression Printr en simulation et comparer le PNG rendu.

La gestion Bluetooth est implémentée mais **non validée matériellement** : une liaison SPP RFCOMM doit être établie et le TSPL accepté par Bluetooth, ce qui reste à tester. BLE/GATT n'est pas inclus.

## Installation Pi Zero (SSH)

Dézipper dans un dossier (ex. `~/printr-t003-bridge`) et entrer dedans :

```bash
cd ~/printr-t003-bridge
bash scripts/install.sh
cp .env.example .env  # facultatif : déjà créé si absent
nano .env
```

L'installation utilise `python3-pil` d'apt (évite de compiler Pillow sur ARMv6), `python3-venv`, les polices DejaVu et BlueZ. Le `requirements.txt` est fourni pour des machines où `pip install -r requirements.txt` fonctionne ; **sur le Pi Zero, utiliser le script `install.sh`**, qui évite une compilation potentiellement coûteuse.

## Premier test sans papier

Dans `.env`, laisser `TRANSPORT=dry-run`.

```bash
.venv/bin/python -m printr_t003 demo
.venv/bin/python -m printr_t003 serve
```

Sur une autre session Pi :

```bash
python3 - <<'PY'
import socket
with socket.create_connection(('127.0.0.1', 9100), timeout=10) as s:
    s.sendall(b'\x1b@Bonjour PrintR!\nTest sans papier\n\x1dV\x00')
PY
```

Consulter `spool/*.png` et les logs. **Ne pas laisser emupos écouter sur le même port :** arrêter `emupos run` avant le lancement (`ss -ltnp | grep ':9100'`).

Depuis le PC qui exécute Printr, renseigner le Pi comme destination TCP (IP du Pi, port `9100`). Dans Printr : `--tcp <IP_DU_PI>:9100` ou `PRINTR_TCP=<IP_DU_PI>:9100` suivant la façon de lancer Printr. Voir son aide pour les options disponibles.

Pour enregistrer et étudier un vrai ticket inconnu, mettre `SAVE_RAW=true`, envoyer un travail, puis :

```bash
.venv/bin/python -m printr_t003 render spool/AAAA-tcp.escpos
```

**Les sauvegardes contiennent les données des tickets** ; purger `spool` quand elles ne servent plus.

## Activer USB

Dans `.env` :

```ini
TRANSPORT=usb
BACKFEED=13
```

Vérifier `/dev/usb/lp0` puis exécuter d'abord notre PNG de référence (la commande n'a pas besoin du décodeur ESC/POS) :

```bash
ls -l /dev/usb/lp0
.venv/bin/python -m printr_t003 image ~/mon-image.png
```

Le script ouvre une seule fois l'USB, puis imprime des pages TSPL `600` lignes et exécute `BACKFEED 13` *avant chaque bande après la première*. **Ne pas imprimer en parallèle depuis CUPS** ou `print-png-backfeed.py`.

**Sécurité :** le port 9100 est sans authentification. Le limiter au LAN fiable, ne jamais le rediriger depuis Internet ; pare-feu recommandé. Sur une machine avec plusieurs utilisateurs, protéger `.env` et `spool/`.

## Bluetooth (étape suivante)

La T003 annonce Bluetooth sur le Selftest, mais nous n'avons **pas encore vérifié son canal SPP ni son protocole TSPL en Bluetooth**. Deux transports prêts dans le code :

- `TRANSPORT=bluetooth-socket` avec `BLUETOOTH_ADDRESS=AA:BB:...` et `BLUETOOTH_CHANNEL=1` (à déterminer) ; connexion RFCOMM par job.
- `TRANSPORT=bluetooth-rfcomm` avec `BLUETOOTH_DEVICE=/dev/rfcomm0` ; nécessite une liaison BlueZ créée séparément.

Pour découvrir :

```bash
bluetoothctl devices
bluetoothctl scan on
# CTRL+C après découverte, puis utiliser l'adresse MAC constatée
sdptool browse AA:BB:CC:DD:EE:FF | grep -A 12 'Serial Port'
```

Pour le premier test Bluetooth, **garder `DRY_RUN=true`** tant que l'adresse, le canal et l'appairage n'ont pas été vérifiés ; `DRY_RUN=true` empêche toute écriture, même si `TRANSPORT=bluetooth-socket`.

Si la T003 offre uniquement BLE, il faudra développer un transport GATT spécifique avec `bleak` (non inclus dans cette version).

## Service systemd (après validation des tests manuels)

```bash
bash scripts/install-service.sh
sudo journalctl -u printr-t003 -f
sudo systemctl restart printr-t003  # après modification de .env
sudo systemctl stop printr-t003
```

Le script crée un service pour ton utilisateur, ajoute les groupes `lp,dialout` et active le démarrage. L'accès `lp0` dépend des permissions du périphérique ; vérifier avec `ls -l /dev/usb/lp0`. Si besoin, ajuster via udev, pas via `chmod 777`.

## Commandes utiles

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m printr_t003 --help
.venv/bin/python -m printr_t003 demo
.venv/bin/python -m printr_t003 render /chemin/job.escpos
.venv/bin/python -m printr_t003 image /chemin/image.png
ss -ltnp | grep 9100
```

## Limites connues et choix de sûreté

- ESC/POS : sous-ensemble ; pas de garantie de fidélité pour tout ticket Printr sans capture réelle ; certains caractères spéciaux, QR et graphismes avancés non pris en charge. Le service signale alors les erreurs.
- Un client TCP = un ticket. La fin du ticket est détectée à la fermeture de socket ou après `JOB_IDLE_TIMEOUT` secondes sans données. Les données tardives seraient considérées comme un autre travail : ajuster ce paramètre si nécessaire.
- Impression **sérialisée** (un client traité à la fois), sans spool persistant ni reprise garantie après crash/USB débranché.
- Une perte de connexion USB pendant l'impression peut produire un ticket partiel ; pas de reprise automatique pour éviter les doubles impressions.
- `BACKFEED=13` est le choix final de calibration ; seul un test physique dira si le rendu à partir de Printr reste aussi bon.
- Pas de reset usine, ni `SET TEAR OFF`, ni commande ESC/POS envoyée directement à la T003.

## Configuration validée par les essais PrintR/T003 du 16–17 novembre 2026

USB : `/dev/usb/lp0`, papier thermique 80 mm, largeur utile 576 px, TSPL `GAP 0,0` / `DIRECTION 1` / `REFERENCE 0,0`, taille des bandes 600 px, `BACKFEED 13` choisi. 105 mm est une limite de taille de page annoncée dans le Selftest ; les pages bitmap de 900 lignes avaient été tronquées.

Code et documentation : prototype expérimental ; ne pas exposer directement le port 9100 à Internet.
