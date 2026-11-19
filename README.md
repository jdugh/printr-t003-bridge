# PrintR → TSPL/TSPL2 · Bridge pour Orgsta T003

Cette passerelle Python permet d’imprimer des tickets PrintR sur une Orgsta T003.  
PrintR envoie le ticket en ESC/POS sur TCP (port 9100 par défaut).
Le bridge le convertit en image monochrome, puis l’envoie à l’imprimante sous forme de commandes TSPL/TSPL2.

**Configuration testée sur matériel** · Raspberry Pi Zero W, Orgsta T003,
papier thermique continu de 80 mm et impression depuis PrintR en Bluetooth
classique (RFCOMM). Le bridge propose également un transport USB (testé).

## Architecture

`Printr (ESC/POS)` → `TCP:9100` → **décodeur ESC/POS** → `PNG 576 px` → découpage `600 px` → **TSPL2** → `USB /dev/usb/lp0` ou **Bluetooth RFCOMM**.

**Important :** PrintR émet de l'ESC/POS. Le décodeur fourni supporte surtout `GS v 0` (raster), `ESC *` (bitmap colonnes), texte simple, alignement, styles, et coupes (`GS V`) remplacées par une ligne pointillée avec ciseaux, puisque la T003 n'a pas de massicot ; la coupe finale du ticket n'est pas dessinée. Des variantes (`GS ( L`, QR, codes-barres, commandes de positions, encodages) peuvent nécessiter des adaptations. **Ce n'est pas un émulateur ESC/POS exhaustif**. Ce décodeur a été testé sur un ticket de 2m60 issue de PrintR contenant un grand nombre d'échantillons de différents blocs. Les commandes inconnues déclenchent une erreur dans les logs, jamais une impression volontairement approximative. Pour un premier ticket réel, tester une impression Printr en simulation et comparer le PNG rendu.

## Installation

Clonnez et dézippez le projet :

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

Consulter `spool/last-ticket.png` et les logs.

Dans Printr : `--tcp <IP_DU_PI>:9100` ou `PRINTR_TCP=<IP_DU_PI>:9100` suivant la façon de lancer Printr. Voir son aide pour les options disponibles.

Pour enregistrer et étudier un vrai ticket, mettre `SAVE_RAW=true`, envoyer un travail, puis :

```bash
.venv/bin/python -m printr_t003 render spool/AAAA-tcp.escpos
```

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

Le script ouvre une seule fois l'USB, puis imprime des pages TSPL `600` lignes et exécute `BACKFEED 13` *avant chaque bande après la première*.

**Sécurité :** le port 9100 est sans authentification. Le limiter au LAN fiable, ne jamais le rediriger depuis Internet ; pare-feu recommandé. Sur une machine avec plusieurs utilisateurs, protéger `.env` et `spool/`.

## Impression en Bluetooth

L’impression depuis PrintR a été testée avec une Orgsta T003 appairée à
un Raspberry Pi Zero W. Après l’appairage, renseigner dans `.env` l’adresse
Bluetooth de l’imprimante et le canal RFCOMM. Le canal `1` a été utilisé
sur la T003 testée.

```ini
TRANSPORT=bluetooth-socket
BLUETOOTH_ADDRESS=AA:BB:CC:DD:EE:FF
BLUETOOTH_CHANNEL=1
DRY_RUN=false
```

Redémarrer le bridge, puis envoyer un ticket de test depuis PrintR.
Le mode `bluetooth-rfcomm` est également disponible si une liaison
`/dev/rfcomm0` a déjà été créée avec BlueZ.

La connexion Bluetooth utilise le profil série RFCOMM (SPP).
Les imprimantes qui communiquent uniquement en BLE/GATT nécessitent
un autre transport.

Pour découvrir :

```bash
bluetoothctl devices
bluetoothctl scan on
sdptool browse AA:BB:CC:DD:EE:FF | grep -A 12 'Serial Port'
# CTRL+C après découverte, puis utiliser l'adresse MAC constatée
```

Pour le premier test Bluetooth, **garder `DRY_RUN=true`** tant que l'adresse, le canal et l'appairage n'ont pas été vérifiés ; `DRY_RUN=true` empêche toute écriture, même si `TRANSPORT=bluetooth-socket`.


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

## Réglages testés en USB et Bluetooth

USB : `/dev/usb/lp0`, papier thermique 80 mm, largeur utile 576 px, TSPL `GAP 0,0` / `DIRECTION 1` / `REFERENCE 0,0`, taille des bandes 600 px, `BACKFEED 13` choisi. 105 mm est une limite de taille de page annoncée dans le Selftest ; les pages bitmap de 900 lignes avaient été tronquées.

Code et documentation : prototype expérimental ; ne pas exposer directement le port 9100 à Internet.

## Compatibilité avec d’autres imprimantes TSPL/TSPL2

D’autres modèles peuvent fonctionner s’ils acceptent les commandes
TSPL/TSPL2 utilisées par le bridge via USB ou Bluetooth RFCOMM.
L’Orgsta T003 est le modèle testé à ce jour.

La largeur du papier (`PAPER_WIDTH_MM`), la largeur d’impression
(`PRINT_WIDTH`), la résolution (`DPI`), la hauteur des bandes
(`BAND_HEIGHT`) et le recul du papier (`BACKFEED`) sont configurables.
Le code actuel émet `GAP 0,0` pour le papier continu et limite
`PRINT_WIDTH` à 576 points.

Si vous essayez le bridge sur un autre modèle, ouvrez une issue avec
la référence de l’imprimante, le transport utilisé, la largeur du
papier et le résultat obtenu. Un essai réussi ou un échec documenté
aidera à préciser la compatibilité.