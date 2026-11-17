from PIL import Image, ImageOps


def normalize(image, cfg):
    rgba = image.convert('RGBA')
    bg = Image.new('RGBA', rgba.size, 'white')
    bg.alpha_composite(rgba)
    gray = bg.convert('L')
    if gray.width > cfg.width:
        height = max(1, round(gray.height * cfg.width / gray.width))
        gray = gray.resize((cfg.width, height), Image.Resampling.LANCZOS)
    elif gray.width < cfg.width:
        # Printr utilise 512 px par défaut : conserver ses proportions et centrer sur 576 px.
        canvas = Image.new('L', (cfg.width, gray.height), 255)
        canvas.paste(gray, ((cfg.width - gray.width) // 2, 0))
        gray = canvas
    if gray.height > cfg.max_height:
        raise ValueError(f'Ticket trop long : {gray.height} lignes, limite {cfg.max_height}')
    if cfg.dither == 'floyd':
        return gray.convert('1')
    return gray.point(lambda p: 0 if p < cfg.threshold else 255).convert('1')


def batches(image, cfg):
    """Génère des pages TSPL indépendantes, dans un flux USB unique."""
    if image.mode != '1' or image.width != cfg.width:
        raise ValueError('Image attendue en mode 1 et à largeur configurée')
    total = image.height
    count = (total + cfg.band - 1) // cfg.band
    for n in range(count):
        top = n * cfg.band
        bottom = min(top + cfg.band, total)
        h = bottom - top
        band = image.crop((0, top, cfg.width, bottom))
        mm = h * 25.4 / cfg.dpi
        header = (
            f'SIZE {cfg.paper_mm} mm,{mm:.2f} mm\r\n'
            'GAP 0,0\r\n'
            'DIRECTION 1\r\n'
            'REFERENCE 0,0\r\n'
            'CLS\r\n'
            f'BITMAP 0,0,{cfg.width // 8},{h},0,'
        ).encode('ascii')
        prefix = f'BACKFEED {cfg.backfeed}\r\n'.encode('ascii') if n > 0 and cfg.backfeed else b''
        yield prefix + header + band.tobytes() + b'\r\nPRINT 1,1\r\n'


def write_to(image, cfg, output):
    count = 0
    for block in batches(image, cfg):
        output.write(block)
        count += 1
    if hasattr(output, 'flush'):
        output.flush()
    return count
