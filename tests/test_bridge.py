import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from printr_t003.config import Config
from printr_t003.escpos import Renderer, cut_mark, raster_from_bits, UnsupportedESCPos
from printr_t003.tspl import normalize, batches


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = replace(Config.from_env(), spool_dir=Path(self.temp.name), transport='dry-run', dry_run=True)

    def test_raster_escpos(self):
        raw = b'\x1dv0\x00' + bytes([1, 0, 8, 0]) + bytes([255] * 8)
        im = Renderer(self.cfg).parse(raw)
        self.assertEqual(im.width, 576)
        self.assertEqual(im.height, 8)
        self.assertEqual(im.getpixel((0, 0)), 0)
        self.assertEqual(im.getpixel((8, 0)), 255)

    def test_text(self):
        im = Renderer(self.cfg).parse(b'\x1b@Bonjour!\nFin\n\x1dV\x00')
        self.assertGreater(im.height, 0)
        self.assertEqual(im.width, 576)

    def test_text_sizes(self):
        # Tailles PrintR S/M/L/XL = GS ! 0x00/0x11/0x22/0x33 (zone PrintR 4/504).
        def ink(size):
            raw = b'\x1b@\x1dL\x04\x00\x1dW\xf8\x01\x1d!' + bytes([size]) + b'Hi\n'
            box = Renderer(self.cfg).parse(raw).point(lambda v: 255 - v).getbbox()
            return box[2] - box[0], box[3] - box[1]
        sizes = [ink(v) for v in (0x00, 0x11, 0x22, 0x33)]
        for k, (w, h) in enumerate(sizes[1:], start=2):
            self.assertAlmostEqual(w / sizes[0][0], k, delta=0.35)
            self.assertAlmostEqual(h / sizes[0][1], k, delta=0.35)
        # Largeur et hauteur indépendantes.
        w, h = ink(0x30)
        self.assertGreater(w, 3 * sizes[0][0])
        self.assertEqual(h, sizes[0][1])

    def test_cut_mark(self):
        # Bloc « Coupe » PrintR (GS V A 0) au milieu : marque pointillée + ciseaux.
        base = Renderer(self.cfg).parse(b'\x1b@A\nB\n')
        cut = Renderer(self.cfg).parse(b'\x1b@A\n\x1dVA\x00B\n')
        self.assertGreater(cut.height, base.height)
        mark = cut_mark(self.cfg.width)
        self.assertEqual(cut.height, base.height + mark.height)
        row = [mark.getpixel((x, 28)) for x in range(100, self.cfg.width)]
        self.assertTrue(0.4 < row.count(0) / len(row) < 0.8)  # pointillés
        # Coupe finale (ou suivie d'avances blanches seules) : rien à dessiner.
        end = Renderer(self.cfg).parse(b'\x1b@A\nB\n\x1bd\x03\x1dVA\x00')
        tail = Renderer(self.cfg).parse(b'\x1b@A\nB\n\x1bd\x03')
        self.assertEqual(end.height, tail.height)
        # Coupes consécutives : une seule marque.
        twice = Renderer(self.cfg).parse(b'\x1b@A\n\x1dVA\x00\x1dV\x00B\n')
        self.assertEqual(twice.height, cut.height)

    def test_inverse_band_height(self):
        # Bandeaux PrintR (GS B 1) : même hauteur avec ou sans accent/jambage.
        def band(text):
            raw = b'\x1b@\x1dL\x04\x00\x1dW\xf8\x01\x1dB\x01' + text + b'\n'
            box = Renderer(self.cfg).parse(raw).point(lambda v: 255 - v).getbbox()
            return box[3] - box[1]
        self.assertEqual(band(b'   LUNE   '), band(b'   \x90NIGME   '))
        self.assertEqual(band(b'   LUNE   '), band(b'   gypj   '))

    def test_font_b_56_columns(self):
        # Petite police PrintR : 56 colonnes sur une seule ligne, sans recoupe.
        line = b'Des 0 et des 1 : jamais trois pareils a la suite, autant'
        self.assertEqual(len(line), 56)
        r = Renderer(self.cfg)
        im = r.parse(b'\x1b@\x1dL\x04\x00\x1dW\xf8\x01\x1bM\x01' + line + b'\n')
        self.assertEqual(im.height, r.line_spacing)

    def test_split_and_backfeed(self):
        im = Image.new('1', (576, 1800), 1)
        blocks = list(batches(im, self.cfg))
        self.assertEqual(len(blocks), 3)
        self.assertNotIn(b'BACKFEED', blocks[0])
        self.assertTrue(blocks[1].startswith(b'BACKFEED 13\r\n'))
        self.assertEqual(sum(b.count(b'PRINT 1,1\r\n') for b in blocks), 3)
        self.assertEqual(len(blocks[0].split(b'BITMAP 0,0,72,600,0,', 1)[1].split(b'\r\nPRINT', 1)[0]), 43200)

    def test_unsupported_rejected(self):
        with self.assertRaises(UnsupportedESCPos):
            Renderer(self.cfg).parse(b'\x1b\xfe\x00')

    def test_white_black_polarity(self):
        im = raster_from_bits(b'\x80',1,1)
        self.assertEqual([im.getpixel((i,0)) for i in range(8)], [0]+[255]*7)

if __name__ == '__main__':
    unittest.main()
