"""Décodeur ESC/POS limité à un sous-ensemble de commandes courantes.

Une commande inconnue avec paramètres peut désynchroniser le flux : en mode strict
on refuse le job plutôt que d'imprimer un ticket incomplet et trompeur.
"""
import re

from PIL import Image, ImageDraw, ImageFont
import qrcode


class UnsupportedESCPos(ValueError):
    pass


def raster_from_bits(payload, width_bytes, height):
    if width_bytes <= 0 or height <= 0 or len(payload) != width_bytes * height:
        raise ValueError('Raster ESC/POS incomplet')
    # ESC/POS bit 1 = noir ; Pillow mode 1 bit 1 = blanc.
    inverted = bytes(b ^ 255 for b in payload)
    return Image.frombytes('1', (width_bytes * 8, height), inverted).convert('L')


class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.parts = []
        self.height = 0
        self.text = bytearray()
        self.align = 0
        self.bold = False
        self.underline = False
        self.inverse = False
        self.upside_down = False
        # Multiplicateurs de taille de caractère (1 à 8), cf. GS ! / ESC !.
        self.size_w = 1
        self.size_h = 1
        self.font_a = ImageFont.truetype(cfg.font, cfg.font_size)
        # Font B : un peu plus petite/fine pour mieux coller à ESC/POS.
        self.font_b = ImageFont.truetype(cfg.font, max(10, int(round(cfg.font_size * 0.70))))
        self.font_mode = 0  # 0=A, 1=B
        self.line_spacing = max(24, cfg.font_size + 6)
        self.codepage = 'cp858'
        self.graphics = None
        self.qr_data = None
        self.qr_size = 6
        self.qr_ecc = qrcode.constants.ERROR_CORRECT_M
        self.unsupported = []
        # Zone imprimable courante (GS L / GS W), utilisée pour le rendu texte.
        self.area_left = 0
        self.area_width = self.cfg.width

    def current_font(self):
        return self.font_b if self.font_mode == 1 else self.font_a

    def text_area(self):
        left = max(0, min(self.cfg.width - 1, self.area_left))
        width = max(1, min(self.cfg.width - left, self.area_width))
        return left, width

    def reset(self):
        if self.text:
            self.flush_line()
        self.align = 0
        self.bold = False
        self.underline = False
        self.inverse = False
        self.upside_down = False
        self.size_w = 1
        self.size_h = 1
        self.font_mode = 0
        self.line_spacing = max(24, self.cfg.font_size + 6)
        self.area_left = 0
        self.area_width = self.cfg.width

    def append_part(self, image):
        height = self.height + image.height
        if height > self.cfg.max_height:
            raise ValueError(f'Ticket de {height} lignes, maximum {self.cfg.max_height}')
        self.parts.append(image)
        self.height = height

    def flush_line(self):
        text = self.text.decode(self.codepage, errors='replace')
        self.text.clear()
        left, area_width = self.text_area()
        font = self.current_font()
        factor_x = self.size_w
        # Les cellules de la police A sont plus étroites que la police TTF
        # à hauteur équivalente. Les 42 colonnes PrintR tiennent sur 504 points.
        if self.area_left == 4 and self.area_width == 504:
            # PrintR place le texte à 4 points dans son canevas de 512 points.
            if self.cfg.width > 512:
                left += (self.cfg.width - 512) // 2
            if self.font_mode == 0:
                factor_x *= 0.90
        factor_y = self.size_h
        height = self.line_spacing * factor_y

        def fits(line):
            x0, _, x1, _ = font.getbbox(line)
            return round((x1 - x0 + 2) * factor_x) <= area_width

        def draw_line(line):
            canvas = Image.new('L', (self.cfg.width, height), 255)
            if line:
                x0, y0, x1, y1 = font.getbbox(line)
                layer = Image.new('L', (max(1, x1 - x0) + 2, max(1, y1 - y0) + 3), 255)
                pen = ImageDraw.Draw(layer)
                pen.text((-x0, -y0), line, font=font, fill=0)
                if self.bold:
                    pen.text((1 - x0, -y0), line, font=font, fill=0)
                if self.underline:
                    pen.line((0, layer.height - 1, layer.width, layer.height - 1), fill=0)
                size = (max(1, min(area_width, round(layer.width * factor_x))), layer.height * factor_y)
                if size != layer.size:
                    layer = layer.resize(size, Image.Resampling.NEAREST)
                if self.inverse:
                    layer = layer.point(lambda value: 255 - value)

                x = left
                if self.align == 1:
                    x += (area_width - layer.width) // 2
                elif self.align == 2:
                    x += area_width - layer.width
                if self.upside_down:
                    # ESC { inverse aussi le placement gauche/droite dans la zone.
                    x = 2 * left + area_width - x - layer.width
                    layer = layer.transpose(Image.Transpose.ROTATE_180)
                canvas.paste(layer, (x, 0))
            self.append_part(canvas)

        # Les lignes remplies d'espaces de PrintR forment des bandeaux ou
        # des colonnes. Leur mise en page dépend de la position des espaces.
        padded = (
            len(text) <= self.cfg.chars_per_line
            and text.startswith(' ') and text.endswith(' ')
        )
        if padded or fits(text) or not text:
            draw_line(text)
            return

        line = ''
        for token in re.findall(r' +|[^ ]+', text):
            if fits(line + token):
                line += token
                continue
            if line.rstrip(' '):
                draw_line(line.rstrip(' '))
            line = token.lstrip(' ')
            # Découpe également un mot ou une URL trop longue pour la zone.
            while line and not fits(line):
                low, high = 1, len(line)
                while low < high:
                    mid = (low + high + 1) // 2
                    if fits(line[:mid]):
                        low = mid
                    else:
                        high = mid - 1
                draw_line(line[:low])
                line = line[low:]
        if line:
            draw_line(line.rstrip(' '))

    def add_raster(self, img, *, center_on_paper=False):
        if self.text:
            self.flush_line()
        if img.width > self.cfg.width:
            img = img.resize((self.cfg.width, max(1, round(img.height * self.cfg.width / img.width))), Image.Resampling.NEAREST)
        canvas = Image.new('L', (self.cfg.width, img.height), 255)
        left, area_width = self.text_area()
        if center_on_paper:
            x = (self.cfg.width - img.width) // 2
        elif self.align == 1:
            x = left + max(0, (area_width - img.width) // 2)
        elif self.align == 2:
            x = left + max(0, area_width - img.width)
        else:
            x = left
        canvas.paste(img, (x, 0))
        self.append_part(canvas)

    def render(self):
        if self.text:
            self.flush_line()
        if not self.parts:
            raise ValueError('Aucun contenu ESC/POS rendu')
        im = Image.new('L', (self.cfg.width, self.height), 255)
        y = 0
        for part in self.parts:
            im.paste(part, (0, y))
            y += part.height
        return im

    def parse(self, data):
        i, n = 0, len(data)
        after_cancel = -1

        def need(k):
            if i + k > n:
                raise ValueError('Commande ESC/POS tronquée')

        while i < n:
            b = data[i]
            if b == 10:
                self.flush_line(); i += 1
            elif b == 13:
                i += 1
            elif b == 9:
                self.text.extend(b'    '); i += 1
            elif b == 12:
                self.flush_line(); i += 1
            elif b == 27:
                need(2); op = data[i + 1]
                if op == 64:  # ESC @
                    self.reset(); i += 2
                elif op in (97, 69, 45, 51, 32, 77, 116, 33, 74, 100, 82, 54, 55, 123):
                    need(3); v = data[i + 2]; i += 3
                    if op == 97:
                        self.align = min(2, v)
                    elif op == 69:
                        self.bold = v != 0
                    elif op == 45:
                        self.underline = v != 0
                    elif op == 51:
                        self.line_spacing = max(1, v)
                    elif op == 33:
                        # ESC ! : double largeur (bit 5) / double hauteur (bit 4).
                        self.size_w = 2 if v & 0x20 else 1
                        self.size_h = 2 if v & 0x10 else 1
                    elif op == 100:
                        if self.text:
                            self.flush_line()
                        for _ in range(min(v, 255)):
                            self.append_part(Image.new('L', (self.cfg.width, self.line_spacing), 255))
                    elif op == 74:
                        if self.text:
                            self.flush_line()
                        if v:
                            self.append_part(Image.new('L', (self.cfg.width, v), 255))
                    elif op == 116:
                        self.codepage = {0: 'cp437', 19: 'cp858', 16: 'cp1252', 2: 'cp850'}.get(v, 'cp858')
                    elif op == 77:
                        self.font_mode = 1 if v else 0
                    elif op == 123:
                        self.upside_down = v != 0
                elif op == 50:
                    self.line_spacing = max(24, self.cfg.font_size + 6); i += 2
                elif op == 42:  # ESC * m nL nH + columns (8/24 dot)
                    need(5); mode, width = data[i + 2], data[i + 3] + 256 * data[i + 4]
                    bytes_col = 3 if mode in (32, 33) else 1
                    length = width * bytes_col
                    need(5 + length)
                    payload = data[i + 5:i + 5 + length]
                    h = bytes_col * 8
                    im = Image.new('L', (width, h), 255)
                    pix = im.load()
                    for x in range(width):
                        for j in range(bytes_col):
                            v = payload[x * bytes_col + j]
                            for bit in range(8):
                                if v & (128 >> bit):
                                    pix[x, j * 8 + bit] = 0
                    self.add_raster(im)
                    i += 5 + length
                else:
                    raise UnsupportedESCPos(f'Commande ESC {op:02x} à offset {i}')
            elif b == 29:
                need(2); op = data[i + 1]
                if op == 118 and i + 3 < n and data[i + 2] == 48:  # GS v 0
                    need(8); w = data[i + 4] + data[i + 5] * 256; h = data[i + 6] + data[i + 7] * 256
                    size = w * h; need(8 + size)
                    # PrintR précède chaque bande de grille par CAN et
                    # utilise une zone de 512 points à l'origine.
                    center = (
                        i == after_cancel and w == 64
                        and self.area_left == 0 and self.area_width == 512
                    )
                    self.add_raster(
                        raster_from_bits(data[i + 8:i + 8 + size], w, h),
                        center_on_paper=center,
                    )
                    i += 8 + size
                elif op == 40:  # GS ( k / GS ( L: payload with 16-bit length
                    need(5); fn_group = data[i + 2]; length = data[i + 3] + 256 * data[i + 4]
                    if length > 65535:
                        raise ValueError('Commande GS ( trop grande')
                    need(5 + length)
                    body = data[i + 5:i + 5 + length]
                    if fn_group == 76 and len(body) >= 2:
                        if body[:2] == b'0p' and len(body) >= 10:
                            w = body[6] + 256 * body[7]
                            h = body[8] + 256 * body[9]
                            size = w * h
                            if len(body) != 10 + size:
                                raise UnsupportedESCPos('GS ( L store : dimensions imprévues')
                            self.graphics = raster_from_bits(body[10:], w, h)
                        elif body[:2] == b'02' and self.graphics is not None:
                            self.add_raster(self.graphics); self.graphics = None
                        else:
                            raise UnsupportedESCPos(f'GS ( L fonction inconnue : {body[:6].hex()}')
                    elif fn_group == 107:  # GS ( k : QR code natif ESC/POS
                        if len(body) < 2 or body[0] != 49:
                            raise UnsupportedESCPos(f'GS ( k non pris en charge : {body[:8].hex()}')
                        fn = body[1]
                        if fn == 65 and len(body) == 4 and body[2] in (49, 50):
                            pass
                        elif fn == 67 and len(body) == 3 and 1 <= body[2] <= 16:
                            self.qr_size = body[2]
                        elif fn == 69 and len(body) == 3 and body[2] in (48, 49, 50, 51):
                            self.qr_ecc = {
                                48: qrcode.constants.ERROR_CORRECT_L,
                                49: qrcode.constants.ERROR_CORRECT_M,
                                50: qrcode.constants.ERROR_CORRECT_Q,
                                51: qrcode.constants.ERROR_CORRECT_H,
                            }[body[2]]
                        elif fn == 80 and len(body) >= 3 and body[2] == 48:
                            self.qr_data = body[3:]
                        elif fn == 81 and body == b'1Q0':
                            if self.qr_data is None:
                                raise UnsupportedESCPos('QR Print sans QR Store préalable')
                            qr = qrcode.QRCode(error_correction=self.qr_ecc, box_size=self.qr_size, border=4)
                            qr.add_data(self.qr_data, optimize=0)
                            qr.make(fit=True)
                            matrix = qr.get_matrix()
                            size = len(matrix) * self.qr_size
                            image = Image.new('L', (size, size), 255)
                            draw = ImageDraw.Draw(image)
                            for row, values in enumerate(matrix):
                                for col, black in enumerate(values):
                                    if black:
                                        x, y = col * self.qr_size, row * self.qr_size
                                        draw.rectangle((x, y, x + self.qr_size - 1, y + self.qr_size - 1), fill=0)
                            self.add_raster(image)
                            self.qr_data = None
                        else:
                            raise UnsupportedESCPos(f'GS ( k fonction inconnue : {body[:8].hex()}')
                    else:
                        raise UnsupportedESCPos(f'GS ( {fn_group:02x} inconnu')
                    i += 5 + length
                elif op in (76, 87):  # GS L / GS W
                    need(4)
                    value = data[i + 2] | (data[i + 3] << 8)
                    if op == 76:
                        self.area_left = max(0, min(self.cfg.width - 1, value))
                    else:
                        self.area_width = value
                    i += 4
                elif op in (33, 66, 72, 104, 119, 102):
                    need(3); v = data[i + 2]; i += 3
                    if op == 33:
                        # GS ! n : bits 4-6 = largeur - 1, bits 0-2 = hauteur - 1 (×1 à ×8).
                        # PrintR : S=0x00, M=0x11, L=0x22, XL=0x33.
                        self.size_w = ((v >> 4) & 0x07) + 1
                        self.size_h = (v & 0x07) + 1
                    elif op == 66:
                        self.inverse = v != 0
                elif op == 86:  # cut, ignored on T003 continuous paper
                    need(3); m = data[i + 2]; i += 3
                    if m in (65, 66):
                        need(1); i += 1
                elif op == 36:
                    need(4); i += 4
                elif op == 42:
                    raise UnsupportedESCPos('GS * NV image non gérée')
                else:
                    raise UnsupportedESCPos(f'Commande GS {op:02x} à offset {i}')
            elif b == 28:
                need(2); op = data[i + 1]
                if op in (38, 46):
                    i += 2
                elif op == 67:
                    need(3); i += 3
                else:
                    raise UnsupportedESCPos(f'Commande FS {op:02x} à offset {i}')
            elif b == 16:
                raise UnsupportedESCPos(f'Commande temps réel DLE à offset {i}')
            elif b == 24:  # CAN
                self.text.clear()
                i += 1
                after_cancel = i
            elif b < 32:
                if b == 0:
                    i += 1
                else:
                    raise UnsupportedESCPos(f'Contrôle inconnu 0x{b:02x} à offset {i}')
            else:
                self.text.append(b); i += 1
        return self.render()
