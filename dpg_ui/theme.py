"""Colors, fonts and themes of the DearPyGui UI."""
import os
from dataclasses import dataclass
from typing import Optional

import dearpygui.dearpygui as dpg

# ---- palette (RGBA) ---------------------------------------------------------

BG = (16, 20, 28, 255)
PANEL = (24, 29, 40, 255)
PANEL_HI = (34, 41, 56, 255)
FRAME = (38, 46, 62, 255)
BORDER = (52, 62, 82, 255)
TEXT = (226, 231, 240, 255)
TEXT_DIM = (138, 149, 168, 255)
ACCENT = (58, 196, 160, 255)
GOOD = (104, 214, 120, 255)
WARN = (242, 178, 64, 255)
BAD = (236, 92, 88, 255)
INFO = (104, 168, 255, 255)
GOLD = (246, 206, 92, 255)

CATEGORY_COLORS = {
    "Virion": (186, 120, 255, 255),
    "Viral complex": (232, 138, 255, 255),
    "RNA": (96, 222, 128, 255),
    "DNA": (96, 158, 255, 255),
    "Protein": (255, 168, 64, 255),
}
UNKNOWN_COLOR = (150, 150, 160, 255)
POLYPROTEIN_COLOR = (255, 128, 0, 255)

GROUP_COLORS = {
    "Virion": CATEGORY_COLORS["Virion"],
    "RNA": CATEGORY_COLORS["RNA"],
    "DNA": CATEGORY_COLORS["DNA"],
    "Protein": CATEGORY_COLORS["Protein"],
    "Antibodies": BAD,
}

GENE_CATEGORY_COLORS = {
    "Replication": (112, 214, 124, 255),
    "Capsid": (112, 172, 255, 255),
    "Surface": (240, 200, 90, 255),
    "Regulatory": (204, 142, 255, 255),
}
DEFAULT_GENE_COLOR = (200, 212, 230, 255)

# Gene blocks in the genome map, in genome order
GENE_BLOCK_COLORS = [
    (236, 112, 76, 255), (164, 98, 220, 255), (56, 188, 210, 255), (232, 204, 72, 255),
    (232, 86, 140, 255), (140, 200, 80, 255), (250, 150, 40, 255), (96, 112, 220, 255),
    (40, 170, 150, 255), (220, 70, 70, 255),
]
ORF_COLORS = [(255, 140, 60, 255), (90, 160, 255, 255), (80, 220, 140, 255),
              (255, 96, 160, 255), (180, 120, 255, 255)]
TERMINATOR_COLOR = (236, 72, 72, 255)

# Node title colors in the life-cycle graph, per reaction kind
REACTION_COLORS = {
    "Transition": (40, 140, 120, 255),
    "Change location": (52, 104, 180, 255),
    "Translation": (196, 120, 36, 255),
    "Self-cleavage": (170, 70, 130, 255),
}

# Compartments in the cell view
COMPARTMENT_FILL = {
    "Extracellular": (14, 26, 44, 255),
    "Cytosol": (30, 46, 58, 255),
    "Nucleus": (52, 44, 78, 255),
    "Endosome": (36, 64, 66, 255),
}
MEMBRANE_COLOR = (226, 170, 96, 255)
ER_COLOR = (150, 128, 210, 255)


def with_alpha(color, alpha: int):
    return (color[0], color[1], color[2], alpha)


def lighten(color, amount: float = 0.18):
    return tuple(min(255, int(c + (255 - c) * amount)) for c in color[:3]) + (color[3] if len(color) > 3 else 255,)


def darken(color, amount: float = 0.3):
    return tuple(int(c * (1 - amount)) for c in color[:3]) + (color[3] if len(color) > 3 else 255,)


def category_color(category: str):
    return CATEGORY_COLORS.get(category, UNKNOWN_COLOR)


def gene_color(gene):
    return GENE_CATEGORY_COLORS.get(gene.color_category, DEFAULT_GENE_COLOR)


# ---- fonts ------------------------------------------------------------------

@dataclass
class Fonts:
    regular: Optional[int] = None
    bold: Optional[int] = None
    large: Optional[int] = None
    title: Optional[int] = None
    mono: Optional[int] = None


def _font_dirs():
    windir = os.environ.get("WINDIR", "C:/Windows")
    return [os.path.join(windir, "Fonts"), "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/TTF", "/System/Library/Fonts/Supplemental", "/Library/Fonts"]


def _find_font(*names) -> Optional[str]:
    for folder in _font_dirs():
        for name in names:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    return None


def _add_font(path: Optional[str], size: int) -> Optional[int]:
    if path is None:
        return None
    return dpg.add_font(path, size)


def load_fonts() -> Fonts:
    """Load a system UI font if there is one; DearPyGui's built-in font otherwise."""
    regular = _find_font("segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf")
    bold = _find_font("segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf") or regular
    mono = _find_font("consola.ttf", "DejaVuSansMono.ttf", "Courier New.ttf") or regular
    with dpg.font_registry():
        fonts = Fonts(regular=_add_font(regular, 17), bold=_add_font(bold, 17),
                      large=_add_font(bold, 22), title=_add_font(bold, 64),
                      mono=_add_font(mono, 15))
    if fonts.regular is not None:
        dpg.bind_font(fonts.regular)
    return fonts


def use_font(item, font: Optional[int]):
    if font is not None:
        dpg.bind_item_font(item, font)


# ---- themes -----------------------------------------------------------------

def apply_global_theme():
    core = dpg.mvThemeCat_Core
    plots = dpg.mvThemeCat_Plots
    nodes = dpg.mvThemeCat_Nodes
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            for slot, color in [
                (dpg.mvThemeCol_WindowBg, BG), (dpg.mvThemeCol_ChildBg, PANEL),
                (dpg.mvThemeCol_PopupBg, PANEL_HI), (dpg.mvThemeCol_Border, BORDER),
                (dpg.mvThemeCol_FrameBg, FRAME), (dpg.mvThemeCol_FrameBgHovered, lighten(FRAME, 0.08)),
                (dpg.mvThemeCol_FrameBgActive, lighten(FRAME, 0.15)),
                (dpg.mvThemeCol_TitleBg, PANEL), (dpg.mvThemeCol_TitleBgActive, PANEL_HI),
                (dpg.mvThemeCol_Button, (44, 56, 76, 255)), (dpg.mvThemeCol_ButtonHovered, (58, 74, 100, 255)),
                (dpg.mvThemeCol_ButtonActive, (70, 90, 122, 255)),
                (dpg.mvThemeCol_Header, (44, 70, 84, 255)), (dpg.mvThemeCol_HeaderHovered, (52, 88, 104, 255)),
                (dpg.mvThemeCol_HeaderActive, (58, 104, 122, 255)),
                (dpg.mvThemeCol_Tab, PANEL), (dpg.mvThemeCol_TabHovered, (52, 88, 104, 255)),
                (dpg.mvThemeCol_TabActive, (40, 78, 92, 255)),
                (dpg.mvThemeCol_Text, TEXT), (dpg.mvThemeCol_TextDisabled, TEXT_DIM),
                (dpg.mvThemeCol_Separator, BORDER), (dpg.mvThemeCol_CheckMark, ACCENT),
                (dpg.mvThemeCol_SliderGrab, ACCENT), (dpg.mvThemeCol_SliderGrabActive, lighten(ACCENT)),
                (dpg.mvThemeCol_ScrollbarBg, PANEL), (dpg.mvThemeCol_TableHeaderBg, PANEL_HI),
                (dpg.mvThemeCol_TableRowBg, (0, 0, 0, 0)), (dpg.mvThemeCol_TableRowBgAlt, (255, 255, 255, 8)),
                (dpg.mvThemeCol_TableBorderStrong, BORDER), (dpg.mvThemeCol_TableBorderLight, (44, 52, 70, 255)),
                (dpg.mvThemeCol_PlotHistogram, ACCENT), (dpg.mvThemeCol_ModalWindowDimBg, (0, 0, 0, 150)),
                (dpg.mvThemeCol_DragDropTarget, GOLD),
            ]:
                dpg.add_theme_color(slot, color, category=core)
            for slot, value in [
                (dpg.mvStyleVar_WindowRounding, 8), (dpg.mvStyleVar_ChildRounding, 8),
                (dpg.mvStyleVar_FrameRounding, 5), (dpg.mvStyleVar_GrabRounding, 5),
                (dpg.mvStyleVar_PopupRounding, 6), (dpg.mvStyleVar_TabRounding, 5),
                (dpg.mvStyleVar_ScrollbarSize, 12), (dpg.mvStyleVar_WindowBorderSize, 1),
                (dpg.mvStyleVar_ChildBorderSize, 1),
            ]:
                dpg.add_theme_style(slot, value, category=core)
            for slot, x, y in [
                (dpg.mvStyleVar_FramePadding, 8, 5), (dpg.mvStyleVar_ItemSpacing, 8, 6),
                (dpg.mvStyleVar_WindowPadding, 12, 10), (dpg.mvStyleVar_CellPadding, 6, 3),
            ]:
                dpg.add_theme_style(slot, x, y, category=core)

            for slot, color in [
                (dpg.mvPlotCol_FrameBg, PANEL), (dpg.mvPlotCol_PlotBg, (12, 16, 24, 255)),
                (dpg.mvPlotCol_PlotBorder, BORDER), (dpg.mvPlotCol_LegendBg, with_alpha(PANEL_HI, 220)),
                (dpg.mvPlotCol_AxisGrid, (255, 255, 255, 22)),
            ]:
                dpg.add_theme_color(slot, color, category=plots)
            dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, 2, category=plots)

            for slot, color in [
                (dpg.mvNodeCol_GridBackground, (14, 18, 26, 255)), (dpg.mvNodeCol_GridLine, (34, 40, 54, 255)),
                (dpg.mvNodeCol_NodeBackground, (30, 36, 50, 255)),
                (dpg.mvNodeCol_NodeBackgroundHovered, (38, 46, 64, 255)),
                (dpg.mvNodeCol_NodeBackgroundSelected, (42, 52, 72, 255)),
                (dpg.mvNodeCol_NodeOutline, BORDER), (dpg.mvNodeCol_Link, (150, 170, 200, 200)),
                (dpg.mvNodeCol_LinkHovered, GOLD), (dpg.mvNodeCol_Pin, (170, 190, 220, 255)),
            ]:
                dpg.add_theme_color(slot, color, category=nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_NodeCornerRounding, 6, category=nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_LinkThickness, 2, category=nodes)

        # Disabled widgets look disabled
        for kind in (dpg.mvButton, dpg.mvRadioButton, dpg.mvSliderInt, dpg.mvSelectable):
            with dpg.theme_component(kind, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_Text, with_alpha(TEXT_DIM, 160), category=core)
                dpg.add_theme_color(dpg.mvThemeCol_Button, (34, 40, 52, 255), category=core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (34, 40, 52, 255), category=core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (34, 40, 52, 255), category=core)
    dpg.bind_theme(theme)


_cache: dict = {}


def text_theme(color, kind=None):
    """A theme that only changes the text color (cached per color)."""
    kind = dpg.mvAll if kind is None else kind
    key = ("text", tuple(color), kind)
    if key not in _cache:
        with dpg.theme() as theme:
            with dpg.theme_component(kind):
                dpg.add_theme_color(dpg.mvThemeCol_Text, color, category=dpg.mvThemeCat_Core)
        _cache[key] = theme
    return _cache[key]


def button_theme(color, text=(255, 255, 255, 255)):
    """A filled, colored button (cached per color)."""
    key = ("button", tuple(color), tuple(text))
    if key not in _cache:
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, color, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, lighten(color, 0.15), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, lighten(color, 0.3), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_Text, text, category=dpg.mvThemeCat_Core)
            with dpg.theme_component(dpg.mvButton, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_Button, darken(color, 0.55), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, darken(color, 0.55), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, darken(color, 0.55), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_Text, with_alpha(TEXT_DIM, 180), category=dpg.mvThemeCat_Core)
        _cache[key] = theme
    return _cache[key]


def series_theme(color, kind=None, weight: float = 2.0, fill_alpha: Optional[int] = None):
    """Color of a plot series (cached)."""
    kind = dpg.mvLineSeries if kind is None else kind
    key = ("series", tuple(color), kind, weight, fill_alpha)
    if key not in _cache:
        with dpg.theme() as theme:
            with dpg.theme_component(kind):
                dpg.add_theme_color(dpg.mvPlotCol_Line, color, category=dpg.mvThemeCat_Plots)
                fill = color if fill_alpha is None else with_alpha(color, fill_alpha)
                dpg.add_theme_color(dpg.mvPlotCol_Fill, fill, category=dpg.mvThemeCat_Plots)
                dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, weight, category=dpg.mvThemeCat_Plots)
        _cache[key] = theme
    return _cache[key]


def node_theme(title_color):
    """Title bar color of a node in the life-cycle graph (cached)."""
    key = ("node", tuple(title_color))
    if key not in _cache:
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvNode):
                nodes = dpg.mvThemeCat_Nodes
                dpg.add_theme_color(dpg.mvNodeCol_TitleBar, title_color, category=nodes)
                dpg.add_theme_color(dpg.mvNodeCol_TitleBarHovered, lighten(title_color, 0.12), category=nodes)
                dpg.add_theme_color(dpg.mvNodeCol_TitleBarSelected, lighten(title_color, 0.22), category=nodes)
        _cache[key] = theme
    return _cache[key]

