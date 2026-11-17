from contextlib import contextmanager
import os
import socket

@contextmanager
def destination(cfg):
    if cfg.dry_run or cfg.transport == 'dry-run':
        class NullWriter:
            def write(self, data): return len(data)
            def flush(self): pass
        yield NullWriter()
    elif cfg.transport == 'usb':
        # Écriture vers le périphérique déjà reconnu par le noyau Linux.
        with open(cfg.usb_path, 'wb', buffering=0) as dest:
            yield dest
    elif cfg.transport == 'bluetooth-rfcomm':
        # rfcomm0 doit être déjà associé à la T003 via BlueZ.
        with open(cfg.bluetooth_path, 'wb', buffering=0) as dest:
            yield dest
    elif cfg.transport == 'bluetooth-socket':
        if not hasattr(socket, 'AF_BLUETOOTH'):
            raise RuntimeError('Bluetooth RFCOMM indisponible dans Python')
        if not cfg.bluetooth_address:
            raise RuntimeError('BLUETOOTH_ADDRESS manquante')
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(30)
        try:
            sock.connect((cfg.bluetooth_address, cfg.bluetooth_channel))
            class Writer:
                def write(self, data):
                    sock.sendall(data)
                    return len(data)
                def flush(self): pass
            yield Writer()
        finally:
            sock.close()
