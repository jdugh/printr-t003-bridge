import argparse
import logging
from pathlib import Path

from .config import load_env, Config
from .server import serve, process
from .tspl import normalize, write_to
from .transport import destination
from PIL import Image


def main():
    parser=argparse.ArgumentParser(description='Passerelle Printr ESC/POS TCP 9100 -> Orgsta T003 TSPL')
    parser.add_argument('--env', default=str(Path(__file__).resolve().parent.parent / '.env'))
    parser.add_argument('--verbose', action='store_true')
    sub=parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('serve', help='Recevoir les travaux ESC/POS via TCP')
    p=sub.add_parser('render', help='Décoder un dump ESC/POS local sans imprimer')
    p.add_argument('file', type=Path)
    p=sub.add_parser('image', help='Imprimer un PNG/JPEG via le moteur TSPL, sans ESC/POS')
    p.add_argument('file', type=Path)
    p=sub.add_parser('demo', help='Générer une démo ESC/POS et la convertir en PNG/TSPL')
    args=parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    load_env(args.env)
    cfg=Config.from_env()
    if args.cmd=='serve':
        try:
            serve(cfg)
        except KeyboardInterrupt:
            logging.info('Serveur arrêté (Ctrl+C).')
    elif args.cmd=='render':
        from dataclasses import replace
        cfg = replace(cfg, transport='dry-run', dry_run=True, save_png=True)
        image=process(args.file.read_bytes(), cfg, 'fichier')
        print('Rendu', image.size if image else 'vide', 'dans', cfg.spool_dir)
    elif args.cmd=='demo':
        import struct
        # Mini job texte et bitmap GS v 0, valide pour le parseur.
        rows=bytes([0xFF,0x81,0xBD,0xA5,0xA5,0xBD,0x81,0xFF])
        raw=b'\x1b@Printr T003 bridge\nTest ESC/POS\n' + b'\x1dv0\x00' + bytes([1,0,8,0])+rows+b'\n\x1dV\x00'
        from dataclasses import replace
        cfg=replace(cfg, transport='dry-run', dry_run=True, save_png=True)
        im=process(raw, cfg, 'demo')
        print('Test local généré :', im.size, 'dans', cfg.spool_dir)
    elif args.cmd=='image':
        with Image.open(args.file) as src:
            img=normalize(src, cfg)
        cfg.spool_dir.mkdir(parents=True,exist_ok=True)
        img.save(cfg.spool_dir / 'derniere-image.png')
        with destination(cfg) as dest:
            count=write_to(img,cfg,dest)
        print(f'Image {img.width}x{img.height}, {count} bandes, transport={cfg.transport}')


if __name__=='__main__':
    main()
