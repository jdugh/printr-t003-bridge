from dataclasses import dataclass
from pathlib import Path
import os


def load_env(path):
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        key, val = key.strip(), val.strip()
        if val[:1] in ('"', "'") and val[-1:] == val[:1]:
            val = val[1:-1]
        os.environ.setdefault(key, val)


def boolean(name, default):
    return os.getenv(name, str(default)).lower() in ('1', 'true', 'yes', 'on', 'oui')


@dataclass(frozen=True)
class Config:
    listen_host: str
    listen_port: int
    transport: str
    usb_path: str
    bluetooth_path: str
    bluetooth_address: str
    bluetooth_channel: int
    width: int
    paper_mm: int
    dpi: int
    band: int
    backfeed: int
    threshold: int
    dither: str
    font: str
    font_size: int
    chars_per_line: int
    max_job_bytes: int
    max_height: int
    idle_timeout: float
    dry_run: bool
    spool_dir: Path
    save_raw: bool
    save_png: bool
    strict: bool

    @classmethod
    def from_env(cls):
        c = cls(
            listen_host=os.getenv('LISTEN_HOST', '0.0.0.0'),
            listen_port=int(os.getenv('LISTEN_PORT', '9100')),
            transport=os.getenv('TRANSPORT', 'dry-run'),
            usb_path=os.getenv('USB_DEVICE', '/dev/usb/lp0'),
            bluetooth_path=os.getenv('BLUETOOTH_DEVICE', '/dev/rfcomm0'),
            bluetooth_address=os.getenv('BLUETOOTH_ADDRESS', ''),
            bluetooth_channel=int(os.getenv('BLUETOOTH_CHANNEL', '1')),
            width=int(os.getenv('PRINT_WIDTH', '576')),
            paper_mm=int(os.getenv('PAPER_WIDTH_MM', '80')),
            dpi=int(os.getenv('DPI', '203')),
            band=int(os.getenv('BAND_HEIGHT', '600')),
            backfeed=int(os.getenv('BACKFEED', '13')),
            threshold=int(os.getenv('THRESHOLD', '180')),
            dither=os.getenv('DITHER', 'threshold'),
            font=os.getenv('FONT_PATH', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'),
            font_size=int(os.getenv('FONT_SIZE', '22')),
            chars_per_line=int(os.getenv('CHARS_PER_LINE', '42')),
            max_job_bytes=int(os.getenv('MAX_JOB_BYTES', '4194304')),
            max_height=int(os.getenv('MAX_IMAGE_HEIGHT', '12000')),
            idle_timeout=float(os.getenv('JOB_IDLE_TIMEOUT', '2')),
            dry_run=boolean('DRY_RUN', False),
            spool_dir=Path(os.getenv('SPOOL_DIR', './spool')).expanduser().resolve(),
            save_raw=boolean('SAVE_RAW', False),
            save_png=boolean('SAVE_PNG', True),
            strict=boolean('STRICT_ESCPOS', True),
        )
        if c.transport not in ('dry-run', 'usb', 'bluetooth-rfcomm', 'bluetooth-socket'):
            raise ValueError('TRANSPORT invalide')
        if c.width < 8 or c.width % 8 or c.width > 576:
            raise ValueError('PRINT_WIDTH doit être multiple de 8 et <= 576')
        if not 1 <= c.band <= 800 or not 0 <= c.backfeed <= 100 or not 0 <= c.threshold <= 255:
            raise ValueError('BAND_HEIGHT / BACKFEED / THRESHOLD invalide')
        if c.dither not in ('threshold', 'floyd'):
            raise ValueError('DITHER doit être threshold ou floyd')
        if c.max_job_bytes < 1024 or c.max_height < 1:
            raise ValueError('Limites invalides')
        return c
