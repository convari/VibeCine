# -*- coding: utf-8 -*-
"""Identidade visual VibeCine: paleta de cores, QSS e QPalette.

IDENTIDADE OFICIAL (a partir de design/vibecine-reference.png):
- preto profundo como fundo; vermelho-sangue como destaque;
- vermelho neon para estados ativos; brilho vermelho sutil;
- alto contraste cinematográfico; bordas arredondadas; premium.

FONTE ÚNICA DE CORES: nenhuma página usa hexadecimal "na unha".
Use palette(theme)["chave"] / accent() / type_color() / status_color().

Regra de contraste (WCAG AA): texto normal >= 4.5:1, texto grande >= 3:1;
desabilitados atenuados mas legíveis (>= 3:1 contra o próprio fundo).
"""

from __future__ import annotations

FONT_FAMILY = "Segoe UI"

# ── Vermelho VibeCine — identidade oficial (altere AQUI para re-colorir) ──
BRAND_RED = "#E10600"           # vermelho sangue (referência)
BRAND_RED_NEON = "#FF2E3E"      # hover/ativo luminoso (glow)
BRAND_RED_PRESS = "#9E0400"     # pressionado
BRAND_RED_DARK = "#6E0A0F"      # sombra no gradiente do logo
BRAND_RED_LIGHT = "#C70000"     # variante com contraste sobre branco

PALETTES = {
    "dark": {
        "bg": "#0A0A0C",
        "panel": "#0D0D10",
        "card": "#15151B",
        "card_hover": "#1E1E26",
        "input_bg": "#111116",
        "border": "#2A2A33",
        "accent": BRAND_RED,
        "accent_hover": BRAND_RED_NEON,
        "accent_press": BRAND_RED_PRESS,
        "accent_soft": "#E1060026",
        "glow": "#E1060080",
        "text": "#F2F2F5",
        "text_dim": "#A9A9B4",
        "text_disabled": "#6A6A75",
        "placeholder": "#7F7F8A",
        "selection": BRAND_RED,
        "selection_text": "#FFFFFF",
        "success": "#2EC66E",
        "warning": "#F0A020",
        "error": "#FF4D4D",
        "info": "#FF6B5E",
        "on_accent": "#FFFFFF",
    },
    "light": {
        "bg": "#F6F6F8",
        "panel": "#FFFFFF",
        "card": "#FFFFFF",
        "card_hover": "#FCEAEA",
        "input_bg": "#FFFFFF",
        "border": "#D8D8E0",
        "accent": BRAND_RED_LIGHT,
        "accent_hover": "#E10600",
        "accent_press": "#8F0400",
        "accent_soft": "#E1060014",
        "glow": "#E1060059",
        "text": "#18181D",
        "text_dim": "#494952",
        "text_disabled": "#8A8A96",
        "placeholder": "#8A8A96",
        "selection": BRAND_RED_LIGHT,
        "selection_text": "#FFFFFF",
        "success": "#0E7A3D",
        "warning": "#8F5F00",
        "error": "#C01919",
        "info": "#B21212",
        "on_accent": "#FFFFFF",
    },
}

_STATUS_COLOR = {
    "aguardando": "text_dim",
    "baixando": "accent",
    "concluido": "success",
    "erro": "error",
    "cancelado": "warning",
    "pausado": "warning",
}

_STATUS_LABEL = {
    "aguardando": "Aguardando",
    "baixando": "Baixando",
    "concluido": "Concluído",
    "erro": "Erro",
    "cancelado": "Cancelado",
    "pausado": "Pausado",
}

_TYPE_LABEL = {
    "filme": "Filme", "serie": "Série", "radio": "Rádio",
    "esporte": "Esporte", "youtube": "YouTube", "canal": "Canal",
}

#: Cores de categoria na família vermelha/cinemática (contraste OK nos 2 temas).
_TYPE_COLORS = {
    "dark": {
        "filme": "#FF4D5E", "serie": "#FF9E66", "radio": "#BFBFD0",
        "esporte": "#FFC14D", "youtube": "#FF1A1A", "canal": "#9A9AA6",
    },
    "light": {
        "filme": "#B00015", "serie": "#B5441F", "radio": "#55555F",
        "esporte": "#8F5200", "youtube": "#E10600", "canal": "#494952",
    },
}


def palette(theme: str = "dark") -> dict:
    return PALETTES.get(theme, PALETTES["dark"])


def accent(theme: str = "") -> str:
    """Vermelho principal do tema ativo (ou do informado)."""
    return palette(theme or current())["accent"]


_current_theme = "dark"


def set_theme(name: str) -> None:
    global _current_theme
    _current_theme = name if name in PALETTES else "dark"


def current() -> str:
    return _current_theme


def status_color(pal: dict, status: str) -> str:
    return pal[_STATUS_COLOR.get(status, "text_dim")]


def status_label(status: str) -> str:
    return _STATUS_LABEL.get(status, status)


def type_label(kind: str) -> str:
    return _TYPE_LABEL.get(kind, kind.capitalize())


def type_color(kind: str, theme: str = "") -> str:
    colors = _TYPE_COLORS.get(theme or _current_theme, _TYPE_COLORS["dark"])
    return colors.get(kind, colors["canal"])


# ── Contraste (WCAG) — usado em testes ──────────────────────────────────────

def _lum(hex_color: str) -> float:
    c = hex_color.lstrip("#")[:6]
    r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    r, g, b = (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
               for x in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def app_palette(theme: str = "dark"):
    """QPalette coerente (placeholder, linhas alternadas, disabled, links)."""
    from PySide6.QtGui import QColor, QPalette
    p = palette(theme)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p["bg"]))
    pal.setColor(QPalette.WindowText, QColor(p["text"]))
    pal.setColor(QPalette.Base, QColor(p["input_bg"]))
    pal.setColor(QPalette.AlternateBase, QColor(p["card_hover"]))
    pal.setColor(QPalette.Text, QColor(p["text"]))
    pal.setColor(QPalette.Button, QColor(p["card"]))
    pal.setColor(QPalette.ButtonText, QColor(p["text"]))
    pal.setColor(QPalette.BrightText, QColor(p["error"]))
    pal.setColor(QPalette.Highlight, QColor(p["selection"]))
    pal.setColor(QPalette.HighlightedText, QColor(p["selection_text"]))
    pal.setColor(QPalette.Link, QColor(p["accent"]))
    pal.setColor(QPalette.ToolTipBase, QColor(p["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(p["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(p["placeholder"]))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor(p["text_disabled"]))
    return pal


def build_qss(theme: str = "dark") -> str:
    p = palette(theme)
    return f"""
/* ═══ VibeCine — identidade preto/vermelho (referência oficial) ═══ */
* {{ font-family: "{FONT_FAMILY}", "Inter"; font-size: 13px;
     color: {p['text']}; }}
QMainWindow, QDialog, QWidget#root {{ background: {p['bg']}; }}
QDialog {{ color: {p['text']}; }}

/* Sidebar preta com item ativo vermelho (como na referência) */
QFrame#sidebar {{ background: {p['panel']}; border-right: 1px solid {p['border']}; }}
QLabel#brand {{ font-size: 20px; font-weight: 700; color: {p['text']}; }}
QLabel#brandSub {{ font-size: 11px; color: {p['text_dim']}; }}
QPushButton#nav {{ background: transparent; border: none; border-radius: 10px;
    padding: 11px 14px; text-align: left; color: {p['text_dim']};
    font-weight: 600; }}
QPushButton#nav:hover {{ background: {p['card_hover']}; color: {p['text']}; }}
QPushButton#nav:checked {{ background: {p['accent_soft']}; color: {p['accent_hover']};
    border: 1px solid {p['accent']}; }}

/* Páginas e cards */
QFrame#card {{ background: {p['card']}; border: 1px solid {p['border']};
    border-radius: 14px; }}
QLabel#pageTitle {{ font-size: 18px; font-weight: 700; color: {p['text']}; }}
QLabel {{ color: {p['text']}; background: transparent; }}
QLabel#muted {{ color: {p['text_dim']}; }}
QLabel#emptyIcon {{ color: {p['text_dim']}; }}
QLabel:disabled {{ color: {p['text_disabled']}; }}

/* Chips de filtro (referência: Todos/Filmes/Séries/Canais/YouTube) */
QPushButton#chip {{ background: transparent; border: 1px solid {p['border']};
    border-radius: 14px; padding: 6px 16px; color: {p['text_dim']};
    font-weight: 600; }}
QPushButton#chip:hover {{ color: {p['text']}; border-color: {p['accent']}; }}
QPushButton#chip:checked {{ background: {p['accent']};
    border-color: {p['accent']}; color: {p['on_accent']}; }}

/* Botões */
QPushButton {{ background: {p['card']}; border: 1px solid {p['border']};
    border-radius: 8px; padding: 7px 14px; font-weight: 600;
    color: {p['text']}; }}
QPushButton:hover {{ background: {p['card_hover']}; }}
QPushButton:pressed {{ background: {p['panel']}; }}
QPushButton:disabled {{ color: {p['text_disabled']}; background: {p['panel']};
    border-color: {p['border']}; }}
QPushButton#primary {{ background: {p['accent']}; border: none;
    color: {p['on_accent']}; }}
QPushButton#primary:hover {{ background: {p['accent_hover']}; }}
QPushButton#primary:pressed {{ background: {p['accent_press']}; }}
QPushButton#primary:disabled {{ background: {p['border']};
    color: {p['text_disabled']}; }}
QPushButton#danger {{ color: {p['error']}; border-color: {p['error']};
    background: transparent; }}
QPushButton#danger:hover {{ background: {p['error']}; color: {p['on_accent']}; }}

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser {{
    background: {p['input_bg']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {p['selection']};
    selection-color: {p['selection_text']}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {p['accent']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {p['text_disabled']}; background: {p['panel']}; }}

/* ComboBox + popup */
QComboBox {{ background: {p['input_bg']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 10px; padding: 8px 12px;
    min-height: 20px; }}
QComboBox:focus {{ border: 1px solid {p['accent']}; }}
QComboBox:disabled {{ color: {p['text_disabled']}; background: {p['panel']} }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid {p['text_dim']};
    margin-right: 8px; width: 0; height: 0; }}
QComboBox QAbstractItemView {{ background: {p['panel']}; color: {p['text']};
    border: 1px solid {p['border']};
    selection-background-color: {p['accent']};
    selection-color: {p['on_accent']}; outline: none; }}
QComboBox QAbstractItemView::item {{ padding: 6px 10px; min-height: 22px; }}

/* SpinBox */
QSpinBox {{ background: {p['input_bg']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 10px; padding: 7px 10px; }}
QSpinBox:focus {{ border: 1px solid {p['accent']}; }}
QSpinBox:disabled {{ color: {p['text_disabled']}; background: {p['panel']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ background: {p['card']};
    border: none; width: 18px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {p['card_hover']}; }}

/* CheckBox / Radio */
QCheckBox, QRadioButton {{ color: {p['text']}; spacing: 6px;
    background: transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {p['text_disabled']}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; border: 1px solid {p['border']};
    background: {p['input_bg']}; border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {p['accent']}; border-color: {p['accent']}; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {p['accent']}; }}

/* Tabs */
QTabWidget::pane {{ border: none; background: {p['bg']}; }}
QTabBar::tab {{ background: {p['panel']}; color: {p['text_dim']};
    padding: 8px 16px; border: 1px solid {p['border']};
    border-bottom: none; border-top-left-radius: 8px;
    border-top-right-radius: 8px; margin-right: 4px; font-weight: 600; }}
QTabBar::tab:selected {{ background: {p['card']}; color: {p['accent_hover']}; }}
QTabBar::tab:hover:!selected {{ color: {p['text']}; }}

/* Tabelas, listas e GRID de capas */
QTableWidget, QTableView, QListWidget, QListView, QTreeView, QTreeWidget {{
    background: {p['card']}; color: {p['text']};
    border: 1px solid {p['border']}; border-radius: 12px;
    gridline-color: transparent;
    alternate-background-color: {p['card_hover']}; }}
QTableView::item, QTableWidget::item {{ color: {p['text']}; padding: 6px;
    border-bottom: 1px solid {p['bg']}; }}
QTableView::item:selected, QTableWidget::item:selected,
QListWidget::item:selected, QListView::item:selected,
QTreeView::item:selected {{
    background: {p['accent_soft']}; color: {p['text']};
    border: 1px solid {p['accent']}; border-radius: 10px; }}
QListView::item:hover, QTableView::item:hover, QListWidget::item:hover,
QTableWidget::item:hover {{ background: {p['card_hover']}; }}
QHeaderView::section {{ background: {p['card']}; color: {p['text_dim']};
    border: none; border-bottom: 1px solid {p['border']}; padding: 8px;
    font-weight: 600; }}
QTableCornerButton::section {{ background: {p['card']};
    border: 1px solid {p['border']}; }}

/* Menus */
QMenu {{ background: {p['panel']}; color: {p['text']};
    border: 1px solid {p['border']}; padding: 4px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['accent']}; color: {p['on_accent']}; }}
QMenu::item:disabled {{ color: {p['text_disabled']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 4px 8px; }}
QMenuBar {{ background: {p['panel']}; color: {p['text']}; }}
QMenuBar::item:selected {{ background: {p['accent']}; color: {p['on_accent']}; }}

/* Progresso (vermelho; verde só no sucesso) */
QProgressBar {{ background: {p['input_bg']}; border: none; border-radius: 6px;
    height: 12px; text-align: center; color: {p['text_dim']};
    font-size: 10px; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 6px; }}
QProgressBar#done::chunk {{ background: {p['success']}; }}
QProgressBar#error::chunk {{ background: {p['error']}; }}
QProgressBar#paused::chunk {{ background: {p['warning']}; }}

/* Scrollbars */
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px;
    min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {p['text_dim']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p['border']};
    border-radius: 5px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: {p['text_dim']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* Toast */
QFrame#toast {{ border-radius: 10px; padding: 12px 16px; }}
QLabel#toastText {{ color: {p['on_accent']}; font-weight: 600; }}

/* Badge de status */
QLabel#badge {{ border-radius: 9px; padding: 2px 10px; font-size: 11px;
    font-weight: 700; color: #FFFFFF; }}

/* Tooltip */
QToolTip {{ background: {p['panel']}; color: {p['text']};
    border: 1px solid {p['border']}; padding: 6px; }}

/* Foco visível (acessibilidade) */
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTableWidget:focus,
QTableView:focus, QListView:focus, QSpinBox:focus, QCheckBox:focus,
QRadioButton:focus {{
    border: 2px solid {p['accent']};
}}
"""
