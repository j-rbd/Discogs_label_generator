"""Génération du PDF de vignettes autocollantes (planche A4) avec reportlab."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from discogs_client import Release


@dataclass(frozen=True)
class Sheet:
    """Format de planche : dimensions en mm."""
    name: str
    cols: int
    rows: int
    label_w: float
    label_h: float
    margin_left: float
    margin_top: float
    gap_x: float = 0.0
    gap_y: float = 0.0


# Formats courants de planches A4 autocollantes (Avery / Herma équivalents).
SHEETS: dict[str, Sheet] = {
    "99,1 x 67,7 mm — 8 par page (Avery L7165)": Sheet("L7165", 2, 4, 99.1, 67.7, 4.65, 13.1, 2.5, 0),
    "99,1 x 38,1 mm — 14 par page (Avery L7163)": Sheet("L7163", 2, 7, 99.1, 38.1, 4.65, 15.1, 2.5, 0),
    "63,5 x 38,1 mm — 21 par page (Avery L7160)": Sheet("L7160", 3, 7, 63.5, 38.1, 7.2, 15.1, 2.5, 0),
    "70 x 36 mm — 24 par page (sans marge)": Sheet("70x36", 3, 8, 70.0, 36.0, 0, 4.5, 0, 0),
    "105 x 74 mm — 8 par page (A4 ÷ 8)": Sheet("A4-8", 2, 4, 105.0, 74.25, 0, 0, 0, 0),
}

_FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
_FONTS = {"reg": ("arial.ttf", "DejaVuSans.ttf"), "bold": ("arialbd.ttf", "DejaVuSans-Bold.ttf")}


def _register_fonts() -> tuple[str, str]:
    """Arial (Windows) pour les accents ; Helvetica en dernier recours."""
    out = {}
    for key, candidates in _FONTS.items():
        out[key] = None
        for d in _FONT_DIRS:
            for c in candidates:
                p = d / c
                if p.exists():
                    name = f"Lbl-{key}"
                    if name not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(name, str(p)))
                    out[key] = name
                    break
            if out[key]:
                break
    return out["reg"] or "Helvetica", out["bold"] or "Helvetica-Bold"


def _wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if pdfmetrics.stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(text: str, font: str, max_w: float, max_h: float, size: float, min_size: float):
    """Réduit la taille jusqu'à ce que le texte tienne ; tronque en dernier recours."""
    while True:
        lines = _wrap(text, font, size, max_w)
        if len(lines) * size * 1.15 <= max_h or size <= min_size:
            break
        size -= 0.5
    max_lines = max(1, int(max_h // (size * 1.15)))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" ,.-") + "…"
    return lines, size


def _draw_label(c: canvas.Canvas, r: Release, img: Path | None, x: float, y: float,
                w: float, h: float, fonts: tuple[str, str], show_border: bool) -> None:
    """Dessine une vignette : x,y = coin bas-gauche, en points."""
    reg, bold = fonts
    pad = 2.5 * mm
    if show_border:
        c.setLineWidth(0.3)
        c.setStrokeGray(0.6)
        c.roundRect(x, y, w, h, 2 * mm)

    text_x = x + pad
    # Pochette carrée à gauche si l'étiquette est assez large, sinon pas de photo.
    side = min(h - 2 * pad, w * 0.42)
    if img is not None:
        try:
            c.drawImage(ImageReader(str(img)), x + pad, y + h - pad - side, side, side,
                        preserveAspectRatio=True, anchor="c", mask="auto")
            text_x = x + pad + side + pad
        except Exception:
            pass
    text_w = x + w - pad - text_x
    top = y + h - pad

    # Bloc 1 : « Titre - Artiste » (gras, jusqu'à 3 lignes)
    head = f"{r.title} - {r.artist}" if r.artist else r.title
    h_size_max = min(11.0, h / mm * 0.30)
    lines, size = _fit(head, bold, text_w, h * 0.50, h_size_max, 6.0)
    c.setFillGray(0)
    c.setFont(bold, size)
    cy = top - size
    for ln in lines:
        c.drawString(text_x, cy, ln)
        cy -= size * 1.15

    # Bloc 2 : label / pays-année / style, ancrés vers le bas
    country_year = ", ".join(p for p in (r.country, str(r.year) if r.year else "") if p)
    info = [("Label : ", r.label), ("", country_year), ("Style : ", r.styles)]
    info = [(k, v) for k, v in info if v]
    small = min(8.5, max(6.0, h / mm * 0.20))
    c.setFont(reg, small)
    # Chaque entrée peut passer sur 2 lignes (les styles sont souvent longs).
    out: list[str] = []
    for k, v in info:
        ls, _ = _fit(k + v, reg, text_w, small * 1.2 * 2, small, small)
        out.extend(ls)
    yy = y + pad + (len(out) - 1) * small * 1.2 + 0.5
    for ln in out:
        c.drawString(text_x, yy, ln)
        yy -= small * 1.2


def build_pdf(releases: Iterable[Release], sheet: Sheet,
              get_image: Callable[[Release], Path | None],
              start_position: int = 1, show_border: bool = False) -> bytes:
    """Renvoie le PDF. `start_position` (1-based) permet de réutiliser une planche entamée."""
    fonts = _register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Vignettes Discogs")
    page_w, page_h = A4
    per_page = sheet.cols * sheet.rows
    pos = max(0, min(start_position - 1, per_page - 1))

    for r in releases:
        if pos >= per_page:
            c.showPage()
            pos = 0
        col, row = pos % sheet.cols, pos // sheet.cols
        x = (sheet.margin_left + col * (sheet.label_w + sheet.gap_x)) * mm
        y = page_h - (sheet.margin_top + (row + 1) * sheet.label_h + row * sheet.gap_y) * mm
        _draw_label(c, r, get_image(r), x, y, sheet.label_w * mm, sheet.label_h * mm,
                    fonts, show_border)
        pos += 1
    c.showPage()
    c.save()
    return buf.getvalue()
