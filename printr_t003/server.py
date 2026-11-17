import datetime
import os
import logging
import socket
import time
from pathlib import Path

from .escpos import Renderer
from .tspl import normalize, write_to
from .transport import destination

LOG = logging.getLogger(__name__)


def process(raw, cfg, name='job'):
    """Reçoit UN job ESC/POS, génère PNG, puis TSPL (sans transfert si dry-run)."""
    if not raw:
        return None
    cfg.spool_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    stem = f'{timestamp}-{name}'
    if cfg.save_raw:
        # Un seul fichier de diagnostic, remplace a chaque job (meme en cas d'echec du decodeur).
        # Remplacement atomique pour eviter un fichier partiellement ecrit.
        target = cfg.spool_dir / 'last-ticket.escpos'
        temp = cfg.spool_dir / 'last-ticket.escpos.tmp'
        try:
            temp.write_bytes(raw)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        LOG.info('Capture ESC/POS actualisee : %s (%d octets)', target, len(raw))
    image = Renderer(cfg).parse(raw)
    image = normalize(image, cfg)
    if cfg.save_png:
        image.save(cfg.spool_dir / f'last-ticket.png')
    with destination(cfg) as dev:
        count = write_to(image, cfg, dev)
    LOG.info('job=%s entree=%d octets sortie=%dx%d bandes=%d transport=%s', stem, len(raw), image.width, image.height, count, 'simulation' if cfg.dry_run else cfg.transport)
    return image


def serve(cfg):
    cfg.spool_dir.mkdir(parents=True, exist_ok=True)
    if cfg.listen_host not in ('127.0.0.1','localhost','::1'):
        LOG.warning('Port 9100 sans authentification : réserver au LAN fiable, limiter par pare-feu')
    LOG.info('Écoute TCP %s:%d ; transport=%s ; backfeed=%d', cfg.listen_host, cfg.listen_port, cfg.transport, cfg.backfeed)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((cfg.listen_host, cfg.listen_port))
        srv.listen(8)
        # Un travail à la fois : évite les entrelacements sur l'imprimante.
        while True:
            conn, addr = srv.accept()
            with conn:
                conn.settimeout(cfg.idle_timeout)
                parts = []
                length = 0
                over = False
                while True:
                    try:
                        chunk = conn.recv(65536)
                    except socket.timeout:
                        # Une absence de données termine le job, même si Printr garde la socket ouverte.
                        break
                    if not chunk:
                        break
                    length += len(chunk)
                    if length > cfg.max_job_bytes:
                        over = True
                        break
                    parts.append(chunk)
                if over:
                    LOG.error('Job rejeté depuis %s: dépasse MAX_JOB_BYTES', addr)
                    continue
                if parts:
                    try:
                        process(b''.join(parts), cfg, 'tcp')
                    except Exception:
                        LOG.exception('Échec du job envoyé par %s', addr)

