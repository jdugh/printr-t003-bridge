import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from printr_t003.config import Config
from printr_t003.escpos import Renderer, raster_from_bits, UnsupportedESCPos
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
