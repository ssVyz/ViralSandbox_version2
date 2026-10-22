"""The genome map: genes drawn to scale with ORF brackets and terminators.

A drawlist with an item handler: hovering a gene shows its name in a
tooltip, clicking selects it in the builder.
"""
import dearpygui.dearpygui as dpg

from game_api import ItemKind
from . import theme


class GenomeMap:
    HEIGHT = 118
    MARGIN = 56

    def __init__(self, view, parent):
        self.view = view
        self.blocks: list = []  # (x0, x1, key, text)
        self.width = 800
        with dpg.child_window(parent=parent, height=self.HEIGHT + 18, border=True,
                              no_scrollbar=True) as self.frame:
            self.drawlist = dpg.add_drawlist(width=self.width, height=self.HEIGHT)
        with dpg.item_handler_registry() as handlers:
            dpg.add_item_hover_handler(callback=self._on_hover)
            dpg.add_item_clicked_handler(dpg.mvMouseButton_Left, callback=self._on_click)
        dpg.bind_item_handler_registry(self.drawlist, handlers)
        with dpg.tooltip(self.frame):  # drawlists can't own tooltips; their frame can
            self.tooltip_text = dpg.add_text("")

    def _block_at(self, x: float):
        for x0, x1, key, text in self.blocks:
            if x0 <= x <= x1:
                return key, text
        return None, None

    def _on_hover(self, sender, app_data, user_data):
        x, _ = dpg.get_drawing_mouse_pos()
        _, text = self._block_at(x)
        dpg.set_value(self.tooltip_text, text or "Click a gene to select it")

    def _on_click(self, sender, app_data, user_data):
        x, _ = dpg.get_drawing_mouse_pos()
        key, _ = self._block_at(x)
        if key is not None:
            self.view.select(("gene", key))

    def redraw(self, width: int):
        builder = self.view.builder
        config = builder.config()
        items = builder.installed()
        spans = builder.orf_spans()
        selected = self.view.selected

        self.width = max(300, width)
        dpg.configure_item(self.drawlist, width=self.width)
        dpg.delete_item(self.drawlist, children_only=True)
        self.blocks = []
        draw = self.drawlist
        w, h = self.width, self.HEIGHT
        center_y = 70
        left, right = self.MARGIN, w - self.MARGIN
        span_w = right - left

        dpg.draw_text((10, h - 18), f"{config.genome_string}  ·  {config.virion_type}",
                      color=theme.TEXT_DIM, size=14, parent=draw)

        total = sum(i.gene.length for i in items if i.kind is ItemKind.GENE)
        if total == 0:
            dpg.draw_text((w / 2 - 150, center_y - 10), "Drag genes from your hand onto the genome",
                          color=theme.TEXT_DIM, size=17, parent=draw)
            return

        # 5'/3' ends: DNA and negative-sense RNA are drawn as the template strand
        flipped = config.nucleic_acid == "DNA" or (config.polarity_applies and config.polarity == "negative")
        dpg.draw_text((left - 30, center_y - 10), "3'" if flipped else "5'", color=theme.TEXT, size=17, parent=draw)
        dpg.draw_text((right + 10, center_y - 10), "5'" if flipped else "3'", color=theme.TEXT, size=17, parent=draw)

        strand = theme.CATEGORY_COLORS["DNA"] if config.nucleic_acid == "DNA" else theme.CATEGORY_COLORS["RNA"]
        double = config.strandedness == "double"
        offsets = (-13, 13) if double else (0,)
        for dy in offsets:
            dpg.draw_line((left, center_y + dy), (right, center_y + dy), color=strand, thickness=3, parent=draw)

        gene_x = {}
        terminators = []
        x = left
        color_index = 0
        block_h = 11 if double else 9
        for item in items:
            if item.kind is ItemKind.TERMINATOR:
                terminators.append((item.key, x))
                continue
            if item.kind is not ItemKind.GENE:
                continue
            gene = item.gene
            gw = max(10, gene.length / total * span_w)
            color = theme.GENE_BLOCK_COLORS[color_index % len(theme.GENE_BLOCK_COLORS)]
            if not item.is_active:
                color = theme.with_alpha(color, 90)
            is_selected = selected == ("gene", item.key)
            dpg.draw_rectangle((x, center_y - block_h), (x + gw, center_y + block_h), fill=color,
                               color=theme.GOLD if is_selected else theme.with_alpha((0, 0, 0, 255), 160),
                               thickness=3 if is_selected else 1, rounding=3, parent=draw)
            if gw > 46:
                name = gene.get_display_name(use_abbreviation=True)
                name = name if len(name) <= max(3, int(gw / 8)) else name[:max(3, int(gw / 8)) - 1] + "…"
                dpg.draw_text((x + 5, center_y - 8), name, color=(10, 12, 18, 255), size=14, parent=draw)
            if item.is_active:
                status = ""
            elif not item.genome_compatible:
                status = (f"  — inactive: needs {gene.required_genome_type}" if config.is_locked
                          else f"  — inactive until a {gene.required_genome_type} genome is locked")
            else:
                status = f"  — inactive: no adjacent {item.domain_partner}"
            self.blocks.append((x, x + gw, item.key, f"{gene.name}  ({gene.length:,} bp){status}"))
            gene_x[item.key] = (x, x + gw)
            x += gw
            color_index += 1

        # ORF brackets above the genome; dashed where only readthrough reaches
        for index, span in enumerate(spans):
            color = theme.ORF_COLORS[index % len(theme.ORF_COLORS)]
            y = 18 + (index % 2) * 13
            thick = 4 if selected == ("orf", span.name) else 2
            solid = [gene_x[g] for g in span.gene_ids if g in gene_x]
            if solid:
                x0, x1 = min(s[0] for s in solid), max(s[1] for s in solid)
                dpg.draw_line((x0, y), (x1, y), color=color, thickness=thick, parent=draw)
                dpg.draw_line((x0, y - 4), (x0, y + 4), color=color, thickness=thick, parent=draw)
                dpg.draw_line((x1, y - 4), (x1, y + 4), color=color, thickness=thick, parent=draw)
                dpg.draw_text((x0 + 3, y - 15), span.name, color=color, size=13, parent=draw)
            extra = [gene_x[g] for g in span.readthrough_gene_ids if g in gene_x]
            if extra:
                start = max(s[1] for s in solid) if solid else min(s[0] for s in extra)
                end = max(s[1] for s in extra)
                _dashed_line(draw, (start, y), (end, y), color)

        for key, tx in terminators:
            thick = 4 if selected == ("terminator", key) else 2
            dpg.draw_line((tx, center_y - 18), (tx, center_y + 18), color=theme.TERMINATOR_COLOR,
                          thickness=thick, parent=draw)
            dpg.draw_text((tx - 4, center_y + 20), "T", color=theme.TERMINATOR_COLOR, size=13, parent=draw)

        dpg.draw_text((w / 2 - 30, h - 18), f"{total:,} bp", color=theme.TEXT_DIM, size=14, parent=draw)


def _dashed_line(parent, p0, p1, color, dash: float = 6, gap: float = 5):
    x0, y = p0
    x1, _ = p1
    x = x0
    while x < x1:
        dpg.draw_line((x, y), (min(x + dash, x1), y), color=color, thickness=1, parent=parent)
        x += dash + gap
