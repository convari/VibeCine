# -*- coding: utf-8 -*-
"""Logo/ícone VibeCine — identidade oficial preto/vermelho.

Conceito (conforme design/vibecine-reference.png): triângulo de PLAY em
vermelho gloss com brilho suave superior, envolvido por um FILMSTRIP
(rolo de filme com perfurações) em arco, sobre preto profundo com
glow vermelho sutil.

Sem emoji. Tudo desenhado via QPainter → mesma arte em qualquer tamanho.

Arquivos gerados por ensure_icon_files():
  vibcine.png (512), vibcine.ico (Windows), vibcine_32.png (favicon),
  android/adaptive_icon.png + android/adaptive_icon_foreground.png
  vibcine_horizontal.png (wordmark para headers/sidebar)
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPixmap, QRadialGradient)

from app.ui import theme

RESOURCES_DIR = os.path.dirname(os.path.abspath(__file__))
PNG_PATH = os.path.join(RESOURCES_DIR, "vibcine.png")
ICO_PATH = os.path.join(RESOURCES_DIR, "vibcine.ico")
FAVICON_PATH = os.path.join(RESOURCES_DIR, "vibcine_32.png")
HORIZONTAL_PATH = os.path.join(RESOURCES_DIR, "vibcine_horizontal.png")
ANDROID_DIR = os.path.join(RESOURCES_DIR, "android")
ANDROID_ADAPTIVE = os.path.join(ANDROID_DIR, "adaptive_icon.png")
ANDROID_ADAPTIVE_FG = os.path.join(ANDROID_DIR, "adaptive_icon_foreground.png")

_RED = QColor(theme.BRAND_RED)
_RED_NEON = QColor(theme.BRAND_RED_NEON)
_RED_DARK = QColor(theme.BRAND_RED_DARK)
_BLACK = QColor("#0A0A0C")
_WHITE = QColor("#F2F2F5")


def _play_triangle(size: int, rect: QRectF) -> QPainterPath:
    """Triângulo de play, apontando para a direita, levemente arredondado."""
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.28, rect.top() + rect.height() * 0.10)
    path.lineTo(rect.left() + rect.width() * 0.82, rect.top() + rect.height() * 0.46)
    path.lineTo(rect.left() + rect.width() * 0.28, rect.top() + rect.height() * 0.82)
    path.closeSubpath()
    return path


def _filmstrip(size: int, rect: QRectF, p: QPainter) -> None:
    """Faixa contínua de filme em arco (embaixo do play), com perfurações."""
    cx, cy = size / 2, size / 2.06
    radius = size * 0.33
    band = size * 0.085
    start, end = math.radians(195), math.radians(345)

    # Faixa (anel segmento): arco grosso em gradiente vermelho
    grad = QLinearGradient(QPointF(cx - radius, cy), QPointF(cx + radius, cy))
    grad.setColorAt(0.0, QColor(255, 46, 62))
    grad.setColorAt(1.0, QColor(140, 12, 16))
    pen = p.pen()
    pen.setWidthF(band)
    pen.setCapStyle(Qt.FlatCap)
    pen.setColor(QColor(0, 0, 0, 0))  # cor vem do brush abaixo
    # Desenha com brush: anel via dois círculos
    outer = QPainterPath()
    outer.addEllipse(QPointF(cx, cy), radius + band / 2,
                     (radius + band / 2) * 0.82)
    inner = QPainterPath()
    inner.addEllipse(QPointF(cx, cy), radius - band / 2,
                     (radius - band / 2) * 0.82)
    ring = outer.subtracted(inner)
    # Corta para manter só o arco inferior
    clip = QPainterPath()
    clip.addRect(QRectF(0, cy - band * 0.4, size, size))
    ring = ring.intersected(clip)
    p.setPen(Qt.NoPen)
    p.fillPath(ring, grad)

    # Perfurações (furos escuros ao longo da faixa)
    perf = size * 0.030
    steps = 8
    for i in range(steps):
        ang = start + (end - start) * i / (steps - 1)
        x = cx + radius * math.cos(ang)
        y = cy + radius * math.sin(ang) * 0.82
        hole = QPainterPath()
        hole.addRoundedRect(QRectF(x - perf / 2, y - perf / 2,
                                   perf, perf * 1.3), perf * 0.3, perf * 0.3)
        p.fillPath(hole, QColor("#0A0A0C"))


def _render(size: int, with_bg: bool = True) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)

    margin = size * 0.05
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    if with_bg:
        # Glow vermelho sutil atrás do quadrado preto
        glow = QRadialGradient(QPointF(size / 2, size / 2), size * 0.62)
        glow.setColorAt(0.0, QColor(225, 6, 0, 0))
        glow.setColorAt(0.78, QColor(225, 6, 0, 28))
        glow.setColorAt(1.0, QColor(225, 6, 0, 64))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(size / 2, size / 2), size * 0.52, size * 0.52)

        bg = QPainterPath()
        bg.addRoundedRect(rect, size * 0.24, size * 0.24)
        p.fillPath(bg, _BLACK)
        # borda neon fina
        pen = p.pen()
        pen.setColor(QColor(225, 6, 0, 170))
        pen.setWidthF(max(1.2, size * 0.008))
        p.setPen(pen)
        p.drawPath(bg)

    inner = QRectF(rect.left() + size * 0.06, rect.top() + size * 0.04,
                   rect.width() - size * 0.12, rect.height() - size * 0.08)

    # Filmstrip contínuo em arco (atrás do play)
    _filmstrip(size, inner, p)

    # Triângulo de play em vermelho gloss (claro no topo → escuro embaixo)
    tri = _play_triangle(size, inner)
    grad = QLinearGradient(tri.boundingRect().topLeft(),
                           tri.boundingRect().bottomLeft())
    grad.setColorAt(0.0, QColor(255, 90, 100))   # neon topo
    grad.setColorAt(0.5, QColor(225, 6, 0))      # sangue
    grad.setColorAt(1.0, QColor(140, 12, 16))    # sombra
    p.fillPath(tri, grad)
    pen2 = p.pen()
    pen2.setColor(QColor(255, 255, 255, 60))
    pen2.setWidthF(max(1.0, size * 0.006))
    p.setPen(pen2)
    p.drawPath(tri)

    # Brilho gloss no topo do play
    shine = QPainterPath()
    b = tri.boundingRect()
    shine.addRoundedRect(QRectF(b.left() + b.width() * 0.04,
                                b.top() + b.height() * 0.03,
                                b.width() * 0.75, b.height() * 0.24),
                       size * 0.05, size * 0.05)
    grad_shine = QLinearGradient(QPointF(b.left(), b.top()),
                                 QPointF(b.left(), b.top() + b.height() * 0.28))
    grad_shine.setColorAt(0.0, QColor(255, 255, 255, 110))
    grad_shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(shine, grad_shine)

    p.end()
    return img


def logo_pixmap(size: int = 256) -> QPixmap:
    return QPixmap.fromImage(_render(size))


def app_icon():
    """QIcon multi-tamanho (16→512) para janela/instalador."""
    from PySide6.QtGui import QIcon
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        icon.addPixmap(logo_pixmap(s))
    return icon


def horizontal_pixmap(height: int = 64) -> QPixmap:
    """Wordmark horizontal: ícone + 'VibeCine' (Vibe branco, Cine vermelho)."""
    w_icon = int(height)
    font_px = int(height * 0.52)
    img = QImage(w_icon + int(height * 4.4), height,
                 QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing | QPainter.TextAntialiasing)
    p.drawImage(0, 0, _render(height))
    font = QFont(theme.FONT_FAMILY, 1)
    font.setPixelSize(font_px)
    font.setBold(True)
    p.setFont(font)
    x = w_icon + int(height * 0.18)
    baseline = height * 0.72
    p.setPen(_WHITE)
    p.drawText(x, int(baseline), "Vibe")
    fm = p.fontMetrics()
    x += fm.horizontalAdvance("Vibe")
    p.setPen(_RED)
    p.drawText(x, int(baseline), "Cine")
    p.end()
    return QPixmap.fromImage(img)


def _android_adaptive_foreground(size: int = 432) -> QImage:
    """Foreground do ícone adaptativo Android (play+strip, ~66% do tamanho)."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    m = size * 0.24
    rect = QRectF(m, m, size - 2 * m, size - 2 * m)
    p.setPen(Qt.NoPen)
    p.fillRect(img.rect(), Qt.transparent)
    _filmstrip(size, rect, p)
    tri = _play_triangle(size, rect)
    grad = QLinearGradient(tri.boundingRect().topLeft(),
                           tri.boundingRect().bottomLeft())
    grad.setColorAt(0.0, QColor(255, 90, 100))
    grad.setColorAt(1.0, QColor(140, 12, 16))
    p.fillPath(tri, grad)
    p.end()
    return img


def nav_icon(name: str, color: QColor | None = None, size: int = 18) -> "QIcon":
    """Ícones vetoriais da sidebar (clapper, download, clock, gear).

    Desenhados com QPainter — sem emojis e escaláveis a qualquer DPI.
    """
    from PySide6.QtGui import QIcon
    col = color or QColor(theme.palette(theme.current())["text_dim"])
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(col)
    pen.setWidthF(max(1.4, size * 0.09))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = size

    if name == "library":  # clapperboard
        p.drawRoundedRect(QRectF(s*0.14, s*0.34, s*0.72, s*0.52), s*0.08, s*0.08)
        p.drawLine(QPointF(s*0.14, s*0.48), QPointF(s*0.86, s*0.48))
        p.drawLine(QPointF(s*0.28, s*0.34), QPointF(s*0.38, s*0.48))
        p.drawLine(QPointF(s*0.52, s*0.34), QPointF(s*0.62, s*0.48))
        pen2 = p.pen(); pen2.setStyle(Qt.DotLine); p.setPen(pen2)
        p.drawLine(QPointF(s*0.16, s*0.34), QPointF(s*0.84, s*0.34))
        p.setBrush(col)
        for i in range(4):
            x = s * (0.20 + i * 0.17)
            p.drawRect(QRectF(x, s*0.40, s*0.07, s*0.05))
    elif name == "downloads":  # seta download
        p.drawLine(QPointF(s*0.5, s*0.16), QPointF(s*0.5, s*0.62))
        path = QPainterPath()
        path.moveTo(QPointF(s*0.26, s*0.44))
        path.lineTo(QPointF(s*0.5, s*0.72))
        path.lineTo(QPointF(s*0.74, s*0.44))
        p.drawPath(path)
        p.drawLine(QPointF(s*0.22, s*0.82), QPointF(s*0.78, s*0.82))
    elif name == "history":  # relógio
        p.drawEllipse(QPointF(s*0.5, s*0.5), s*0.34, s*0.34)
        p.drawLine(QPointF(s*0.5, s*0.5), QPointF(s*0.5, s*0.28))
        p.drawLine(QPointF(s*0.5, s*0.5), QPointF(s*0.66, s*0.55))
    elif name == "settings":  # engrenagem
        p.drawEllipse(QPointF(s*0.5, s*0.5), s*0.17, s*0.17)
        for i in range(8):
            ang = i * math.pi / 4
            r1, r2 = s*0.26, s*0.38
            p.drawLine(QPointF(s*0.5 + r1*math.cos(ang), s*0.5 + r1*math.sin(ang)),
                       QPointF(s*0.5 + r2*math.cos(ang), s*0.5 + r2*math.sin(ang)))
    p.end()
    pix = QPixmap.fromImage(img)
    return QIcon(pix)


def ensure_icon_files() -> tuple[str, str]:
    """Gera todos os assets se ausentes. Retorna (png, ico)."""
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    os.makedirs(ANDROID_DIR, exist_ok=True)
    if not os.path.isfile(PNG_PATH):
        logo_pixmap(512).save(PNG_PATH, "PNG")
    if not os.path.isfile(ICO_PATH):
        _render(256).save(ICO_PATH, "ICO")
    if not os.path.isfile(FAVICON_PATH):
        logo_pixmap(32).save(FAVICON_PATH, "PNG")
    if not os.path.isfile(HORIZONTAL_PATH):
        horizontal_pixmap(128).save(HORIZONTAL_PATH, "PNG")
    if not os.path.isfile(ANDROID_ADAPTIVE):
        logo_pixmap(108).save(ANDROID_ADAPTIVE, "PNG")
        _android_adaptive_foreground(432).save(ANDROID_ADAPTIVE_FG, "PNG")
    return PNG_PATH, ICO_PATH
