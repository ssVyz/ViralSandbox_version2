"""Builder screen: hand, genome, configuration and details, plus the life-cycle
graph and the blueprint in their own tabs.

Genes move by drag and drop: hand → genome installs (at the drop position),
genome → genome reorders, genome → hand removes. Everything goes through
game_api.Builder.
"""
import dearpygui.dearpygui as dpg

from game_api import (GenomeFit, ItemKind, RoundReadiness, NUCLEIC_ACIDS, POLARITIES,
                      STRANDEDNESS_OPTIONS, TERMINATOR_CHANCE_MAX, TERMINATOR_CHANCE_MIN, VIRION_TYPES)
from models import EffectType
from . import theme
from .genome_map import GenomeMap
from .pathway_view import PathwayView

DRAG = "vs_gene"  # one payload type for every gene drag: ("hand", gene_id) or ("genome", key)

OPTION_LABELS = {
    "single": "Single-stranded", "double": "Double-stranded",
    "positive": "Positive (+)", "negative": "Negative (−)",
}
CONFIG_FIELDS = [
    ("nucleic_acid", "Nucleic acid", NUCLEIC_ACIDS),
    ("strandedness", "Strands", STRANDEDNESS_OPTIONS),
    ("polarity", "Polarity", POLARITIES),
    ("virion_type", "Virion", VIRION_TYPES),
]


def _label(value: str) -> str:
    return OPTION_LABELS.get(value, value)


def _tags(gene) -> str:
    tags = []
    if gene.is_utr:
        tags.append("UTR")
    if gene.is_polymerase:
        tags.append("Pol")
    if gene.domain_entity_id is not None:
        tags.append("Dom")
    if gene.required_genome_type:
        tags.append(gene.required_genome_type)
    return " ".join(tags)


class BuilderView:
    def __init__(self, app, parent):
        self.app = app
        self.api = app.api
        self.builder = None
        self.selected = None          # ("gene", id) | ("effect", id) | ("orf", key) | ("terminator", key)
        self.hand_sort = ("name", False)
        self.hand_filter = ""
        self.pathway_dirty = True
        self._width = 1200

        with dpg.item_handler_registry() as self.hand_handlers:
            dpg.add_item_double_clicked_handler(callback=self._on_hand_double_click)

        with dpg.group(parent=parent, show=False) as self.root:
            self._build_header()
            with dpg.tab_bar(callback=self._on_tab) as self.tabs:
                with dpg.tab(label="   Genome   ") as self.tab_genome:
                    self.map = GenomeMap(self, self.tab_genome)
                    with dpg.table(header_row=False, resizable=True, policy=dpg.mvTable_SizingStretchProp,
                                   borders_innerV=False, pad_outerX=False):
                        dpg.add_table_column(init_width_or_weight=0.37)
                        dpg.add_table_column(init_width_or_weight=0.31)
                        dpg.add_table_column(init_width_or_weight=0.32)
                        with dpg.table_row():
                            self._build_hand_panel()
                            self._build_genome_panel()
                            self._build_side_panel()
                with dpg.tab(label="   Life cycle   ") as self.tab_pathway:
                    self.pathway = PathwayView(self, self.tab_pathway)
                with dpg.tab(label="   Blueprint   ") as self.tab_blueprint:
                    self.blueprint_area = dpg.add_child_window(border=False)

    # ------------------------------------------------------------------ layout

    def _build_header(self):
        with dpg.child_window(height=60, border=True, no_scrollbar=True) as self.header:
            with dpg.group(horizontal=True):
                self.ep_text = dpg.add_text("")
                theme.use_font(self.ep_text, self.app.fonts.large)
                dpg.add_spacer(width=24)
                self.round_text = dpg.add_text("")
                theme.use_font(self.round_text, self.app.fonts.large)
                dpg.add_spacer(width=24)
                self.genome_text = dpg.add_text("", color=theme.TEXT_DIM)
                dpg.add_spacer(width=24)
                self.ready_text = dpg.add_text("")
            with dpg.group(horizontal=True, pos=(900, 11)) as self.header_buttons:
                self.play_button = dpg.add_button(label="Play round  ►", width=170, height=36,
                                                  callback=self._on_play)
                dpg.bind_item_theme(self.play_button, theme.button_theme(theme.darken(theme.GOOD, 0.25)))
                quit_button = dpg.add_button(label="Quit game", width=110, height=36, callback=self._on_quit)
                dpg.bind_item_theme(quit_button, theme.button_theme(theme.darken(theme.BAD, 0.4)))

    def _build_hand_panel(self):
        with dpg.child_window(border=True, payload_type=DRAG, drop_callback=self._on_drop_on_hand) as self.hand_panel:
            with dpg.group(horizontal=True):
                title = dpg.add_text("HAND")
                theme.use_font(title, self.app.fonts.bold)
                self.hand_count = dpg.add_text("", color=theme.TEXT_DIM)
            dpg.add_input_text(hint="Search name, set or tag", width=-1, callback=self._on_hand_filter)
            with dpg.table(header_row=True, sortable=True, callback=self._on_hand_sort,
                           policy=dpg.mvTable_SizingStretchProp, row_background=True,
                           scrollY=True, height=-86, borders_outerH=True) as self.hand_table:
                self.hand_columns = {
                    dpg.add_table_column(label="Gene", init_width_or_weight=0.44, default_sort=True): "name",
                    dpg.add_table_column(label="Set", init_width_or_weight=0.14): "set",
                    dpg.add_table_column(label="EP", init_width_or_weight=0.10): "cost",
                    dpg.add_table_column(label="bp", init_width_or_weight=0.13): "length",
                    dpg.add_table_column(label="Tags", init_width_or_weight=0.19): "tags",
                }
            self.install_button = dpg.add_button(label="Install selected gene  →", width=-1, height=28,
                                                 callback=self._on_install_selected)
            dpg.add_text("Double-click or drag a gene onto the genome to install it; drag genome genes "
                         "back here to remove them.", color=theme.TEXT_DIM, wrap=0)

    def _build_genome_panel(self):
        with dpg.child_window(border=True) as self.genome_panel:
            with dpg.group(horizontal=True):
                title = dpg.add_text("GENOME")
                theme.use_font(title, self.app.fonts.bold)
                self.genome_count = dpg.add_text("", color=theme.TEXT_DIM)
            dpg.add_text("5' end", color=theme.TEXT_DIM)
            self.genome_list = dpg.add_child_window(border=False, height=-168)
            self.append_zone = dpg.add_button(label="drop here to add at the 3' end", width=-1, height=26,
                                              payload_type=DRAG, drop_callback=self._on_drop_append)
            dpg.bind_item_theme(self.append_zone, theme.button_theme((30, 38, 52, 255), theme.TEXT_DIM))
            with dpg.group(horizontal=True):
                self.orf_button = dpg.add_button(label="+ ORF", width=130, callback=self._on_add_orf)
                self.term_button = dpg.add_button(label="+ Terminator", width=150, callback=self._on_add_terminator)
            with dpg.group(horizontal=True):
                self.remove_button = dpg.add_button(label="Remove", width=90, callback=self._on_remove)
                self.up_button = dpg.add_button(label="▲ Up", width=80, callback=self._on_move, user_data=-1)
                self.down_button = dpg.add_button(label="▼ Down", width=90, callback=self._on_move, user_data=1)
            self.term_slider = dpg.add_slider_int(label="terminator chance", width=180,
                                                  min_value=TERMINATOR_CHANCE_MIN, max_value=TERMINATOR_CHANCE_MAX,
                                                  format="%d %%", clamped=True, callback=self._on_terminator_chance)
            with dpg.tooltip(self.term_slider):
                dpg.add_text("Chance that a terminator stops translation. Below 100 %, ORFs sometimes "
                             "read through into the genes after it (dashed in the map).", wrap=320)

    def _build_side_panel(self):
        with dpg.child_window(border=True) as self.side_panel:
            with dpg.collapsing_header(label="Virus configuration", default_open=True):
                self.config_radios = {}
                with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit):
                    dpg.add_table_column()
                    dpg.add_table_column()
                    for field, label, options in CONFIG_FIELDS:
                        with dpg.table_row():
                            dpg.add_text(label, color=theme.TEXT_DIM)
                            self.config_radios[field] = dpg.add_radio_button(
                                [_label(o) for o in options], horizontal=True,
                                callback=self._on_config, user_data=(field, options))
                self.genome_summary = dpg.add_text("")
                theme.use_font(self.genome_summary, self.app.fonts.large)
                self.config_status = dpg.add_text("", wrap=0)
                with dpg.group(horizontal=True):
                    self.lock_button = dpg.add_button(label="Lock", height=30, callback=self._on_lock)
                    self.reset_button = dpg.add_button(label="Reset changes", height=30, callback=self._on_reset)
            dpg.add_spacer(height=4)
            details_title = dpg.add_text("DETAILS")
            theme.use_font(details_title, self.app.fonts.bold)
            self.details = dpg.add_child_window(border=False)

    # ------------------------------------------------------------------ screen

    def show(self):
        self.builder = self.api.builder
        dpg.configure_item(self.root, show=True)
        dpg.set_value(self.term_slider, self.builder.terminator_chance)
        self.pathway_dirty = True
        self.refresh()

    def hide(self):
        dpg.configure_item(self.root, show=False)

    def on_resize(self, width: int, height: int):
        self._width = width
        dpg.configure_item(self.header_buttons, pos=(max(600, width - 330), 11))
        panel_height = max(320, height - 60 - 44 - (GenomeMap.HEIGHT + 18) - 46)
        for panel in (self.hand_panel, self.genome_panel, self.side_panel):
            dpg.configure_item(panel, height=panel_height)
        if self.builder is not None:
            self.map.redraw(width - 40)

    def on_frame(self, dt: float):
        pass

    def typing(self) -> bool:
        return False

    def refresh(self):
        """Redraw everything from the API (after any change)."""
        if self.builder is None:
            return
        self.pathway_dirty = True
        self._refresh_header()
        self._refresh_hand()
        self._refresh_genome()
        self._refresh_config()
        self._refresh_details()
        self.map.redraw(self._width - 40)
        active = dpg.get_value(self.tabs)
        if active == self.tab_pathway:
            self._show_pathway()
        elif active == self.tab_blueprint:
            self._refresh_blueprint()

    def select(self, selection):
        self.selected = selection
        self.refresh()

    def _on_tab(self, sender, app_data, user_data):
        if app_data == self.tab_pathway:
            self._show_pathway()
        elif app_data == self.tab_blueprint:
            self._refresh_blueprint()

    def _show_pathway(self):
        if self.pathway_dirty:
            self.pathway.show(self.builder.pathway())
            self.pathway_dirty = False

    # ------------------------------------------------------------------ header

    def _refresh_header(self):
        status = self.api.status()
        dpg.set_value(self.ep_text, f"{status.evolution_points} EP")
        dpg.configure_item(self.ep_text, color=theme.GOLD)
        dpg.set_value(self.round_text, f"Round {status.current_round} / {status.max_rounds}")
        dpg.set_value(self.genome_text, f"Genome {status.genome_length:,} bp")
        readiness = self.api.round_readiness()
        text, color = {
            RoundReadiness.READY: ("Ready to play", theme.GOOD),
            RoundReadiness.NO_GENES: ("Install a gene to play", theme.WARN),
            RoundReadiness.CONFIG_NOT_LOCKED: ("Lock the configuration to play", theme.WARN),
            RoundReadiness.CONFIG_CHANGES_PENDING: ("Unlocked configuration changes", theme.WARN),
        }[readiness]
        dpg.set_value(self.ready_text, text)
        dpg.configure_item(self.ready_text, color=color)

    # ------------------------------------------------------------------ hand

    def _hand_genes(self) -> list:
        genes = self.builder.hand()
        needle = self.hand_filter.strip().lower()
        if needle:
            genes = [g for g in genes if needle in g.name.lower() or needle in g.set_name.lower()
                     or needle in _tags(g).lower()]
        key, descending = self.hand_sort
        sort_keys = {
            "name": lambda g: g.name.lower(), "set": lambda g: (g.set_name, g.name.lower()),
            "cost": lambda g: g.install_cost, "length": lambda g: g.length,
            "tags": lambda g: _tags(g),
        }
        return sorted(genes, key=sort_keys[key], reverse=descending)

    def _refresh_hand(self):
        dpg.delete_item(self.hand_table, children_only=True, slot=1)
        genes = self._hand_genes()
        dpg.set_value(self.hand_count, f"{len(self.builder.hand())} genes")
        for gene in genes:
            affordable = self.builder.can_afford(gene.id)
            with dpg.table_row(parent=self.hand_table):
                row = dpg.add_selectable(label=gene.name, span_columns=True, user_data=gene.id,
                                         default_value=self.selected == ("gene", gene.id),
                                         callback=self._on_hand_click)
                dpg.bind_item_theme(row, theme.text_theme(theme.gene_color(gene)))
                dpg.bind_item_handler_registry(row, self.hand_handlers)
                with dpg.drag_payload(parent=row, drag_data=("hand", gene.id), payload_type=DRAG):
                    dpg.add_text(f"Install {gene.name}  ({gene.install_cost} EP)")
                self._gene_tooltip(row, gene)
                dpg.add_text(gene.set_name, color=theme.TEXT_DIM)
                dpg.add_text(str(gene.install_cost), color=theme.GOOD if affordable else theme.BAD)
                dpg.add_text(f"{gene.length:,}", color=theme.TEXT_DIM)
                dpg.add_text(_tags(gene), color=theme.INFO)
        selected_in_hand = self.selected is not None and self.selected[0] == "gene" \
            and self.builder.in_hand(self.selected[1])
        dpg.configure_item(self.install_button, enabled=selected_in_hand)

    def _gene_tooltip(self, item, gene):
        with dpg.tooltip(item, delay=0.35):
            title = dpg.add_text(f"{gene.name}  ({gene.set_name})", color=theme.gene_color(gene))
            theme.use_font(title, self.app.fonts.bold)
            dpg.add_text(f"{gene.install_cost} EP  ·  {gene.length:,} bp  ·  {len(gene.effect_ids)} effects",
                         color=theme.TEXT_DIM)
            if gene.description:
                dpg.add_text(gene.description, wrap=380)
            for effect_id in gene.effect_ids[:8]:
                effect = self.api.get_effect(effect_id)
                if effect:
                    dpg.add_text(f"• {effect.name}  ({effect.effect_type})", color=theme.TEXT_DIM, wrap=380)

    def _on_hand_filter(self, sender, app_data, user_data):
        self.hand_filter = app_data
        self._refresh_hand()

    def _on_hand_sort(self, sender, app_data, user_data):
        if not app_data:
            return
        column, direction = app_data[0]
        self.hand_sort = (self.hand_columns.get(column, "name"), direction < 0)
        self._refresh_hand()

    def _on_hand_click(self, sender, app_data, user_data):
        self.select(("gene", user_data))

    def _on_hand_double_click(self, sender, app_data, user_data):
        item = app_data[1] if isinstance(app_data, (list, tuple)) else app_data
        self.install(dpg.get_item_user_data(item))

    def _on_install_selected(self, sender, app_data, user_data):
        if self.selected and self.selected[0] == "gene":
            self.install(self.selected[1])

    # ------------------------------------------------------------------ genome

    def _item_label(self, item, orf_index: dict) -> tuple:
        if item.kind is ItemKind.ORF:
            color = theme.ORF_COLORS[orf_index.get(item.key, 0) % len(theme.ORF_COLORS)]
            genes = len(item.orf_gene_ids)
            return f"► {item.key}   translates {genes} gene{'s' if genes != 1 else ''}", color
        if item.kind is ItemKind.TERMINATOR:
            return f"■ {item.key}   stop", theme.TERMINATOR_COLOR
        gene = item.gene
        prefix = "5' UTR  " if gene.is_utr else ""
        if not item.genome_compatible:
            reason = (f"needs {gene.required_genome_type}" if self.builder.config().is_locked
                      else f"lock a {gene.required_genome_type} genome")
            return f"× {prefix}{gene.name}   inactive: {reason}", theme.BAD
        if not item.domain_active:
            return f"× {prefix}{gene.name}   inactive: no adjacent {item.domain_partner}", theme.BAD
        return f"{prefix}{gene.name}   {gene.length:,} bp", theme.gene_color(gene)

    def _refresh_genome(self):
        dpg.delete_item(self.genome_list, children_only=True)
        items = self.builder.installed()
        spans = self.builder.orf_spans()
        orf_index = {span.name: i for i, span in enumerate(spans)}
        in_orf = {g for span in spans for g in span.gene_ids}
        genes = sum(1 for i in items if i.kind is ItemKind.GENE)
        dpg.set_value(self.genome_count, f"{genes} genes  ·  {len(items) - genes} markers")

        if not items:
            dpg.add_text("Empty. Drag genes here from your hand, and add an ORF so they get translated.",
                         parent=self.genome_list, color=theme.TEXT_DIM, wrap=0)
        for item in items:
            label, color = self._item_label(item, orf_index)
            kind = item.kind.value
            indent = 18 if item.kind is ItemKind.GENE and item.key in in_orf else 0
            row = dpg.add_selectable(label=label, parent=self.genome_list, indent=indent,
                                     default_value=self.selected == (kind, item.key),
                                     callback=self._on_genome_click, user_data=(kind, item.key, item.position),
                                     payload_type=DRAG, drop_callback=self._on_drop_on_item)
            dpg.bind_item_theme(row, theme.text_theme(color))
            with dpg.drag_payload(parent=row, drag_data=("genome", item.key), payload_type=DRAG):
                dpg.add_text(f"Move {item.name}")
            if item.kind is ItemKind.GENE:
                self._gene_tooltip(row, item.gene)

        kind, key = self.selected if self.selected else (None, None)
        installed = kind in ("gene", "orf", "terminator") and self.builder.is_installed(key)
        dpg.configure_item(self.remove_button, enabled=installed)
        movable = installed and self.builder.is_movable(key)
        dpg.configure_item(self.up_button, enabled=movable)
        dpg.configure_item(self.down_button, enabled=movable)
        orf_cost = self.builder.orf_cost()
        dpg.configure_item(self.orf_button, label=f"+ ORF ({'free' if orf_cost == 0 else f'{orf_cost} EP'})",
                           enabled=self.builder.can_add_orf()[0])
        dpg.configure_item(self.term_button, label=f"+ Terminator ({self.builder.terminator_cost} EP)",
                           enabled=self.builder.can_add_terminator()[0])

    def _on_genome_click(self, sender, app_data, user_data):
        kind, key, _ = user_data
        self.select((kind, key))

    def _on_drop_on_item(self, sender, app_data, user_data):
        # A drop callback gets the target as sender and the payload's drag_data as
        # app_data; its user_data is not the target's, so read that from the target
        _, _, position = dpg.get_item_user_data(sender)
        self._drop(app_data, position)

    def _on_drop_append(self, sender, app_data, user_data):
        self._drop(app_data, None)

    def _on_drop_on_hand(self, sender, app_data, user_data):
        source, key = app_data
        if source == "genome":
            self._apply(self.builder.remove_item(key), selection=None)

    def _drop(self, payload, position):
        source, key = payload
        if source == "hand":
            self.install(key, position)
            return
        if position is None:
            position = len(self.builder.installed()) - 1
        moved, renames = self.builder.move_item_to(key, position)
        if not moved and not self.builder.is_movable(key):
            self.app.toasts.show("UTR genes stay at the 5' end.", theme.WARN)
        if self.selected and self.selected[1] in renames:
            self.selected = (self.selected[0], renames[self.selected[1]])
        self.refresh()

    def _on_add_orf(self, sender, app_data, user_data):
        self._apply(self.builder.add_orf())

    def _on_add_terminator(self, sender, app_data, user_data):
        self._apply(self.builder.add_terminator())

    def _on_remove(self, sender, app_data, user_data):
        if self.selected:
            self._apply(self.builder.remove_item(self.selected[1]), selection=None)

    def _on_move(self, sender, app_data, user_data):
        if not self.selected:
            return
        kind, key = self.selected
        move = self.builder.move_item_up if user_data < 0 else self.builder.move_item_down
        moved, renames = move(key)
        if moved:
            self.selected = (kind, renames.get(key, key))
            self.refresh()

    def _on_terminator_chance(self, sender, app_data, user_data):
        dpg.set_value(self.term_slider, self.builder.set_terminator_chance(app_data))
        self.refresh()

    def _apply(self, result, selection="keep"):
        """Show an API (ok, message) result and redraw."""
        ok, message = result
        if not ok:
            self.app.toasts.show(message, theme.BAD)
        elif selection is None:
            self.selected = None
        self.refresh()
        return ok

    # ------------------------------------------------------------------ installing

    def install(self, gene_id, position=None):
        """Install a gene, asking first when its genome requirement is not met."""
        gene = self.api.get_gene(gene_id)
        if gene is None or not self.builder.in_hand(gene_id):
            return
        can, reason = self.builder.can_install_gene(gene_id)
        if not can:
            self.app.toasts.show(reason, theme.BAD)
            return

        def do_install():
            if self._apply(self.builder.install_gene(gene_id, position)):
                self.app.toasts.show(f"Installed {gene.name}", theme.GOOD, 2.0)

        def lock_then_install():
            if self._apply(self.builder.lock_config()):
                if self.builder.genome_fit(gene_id) is GenomeFit.MISMATCH:
                    self.app.toasts.show(f"{gene.name} needs {gene.required_genome_type}: it stays inactive.",
                                         theme.WARN, 5)
                do_install()

        fit = self.builder.genome_fit(gene_id)
        config = self.builder.config()
        if fit is GenomeFit.UNLOCKED:
            cost = "free" if config.lock_cost == 0 else f"{config.lock_cost} EP"
            self.app.dialogs.choose(
                "Genome type required",
                f"{gene.name} only works with a {gene.required_genome_type} genome, and your genome type "
                f"isn't locked yet.\n\nLock {config.genome_string} now ({cost}) and install, or install it "
                f"inactive for now?",
                [(f"Lock {config.genome_string} and install", lock_then_install, theme.ACCENT),
                 ("Install inactive", do_install, None), ("Cancel", None, None)])
        elif fit is GenomeFit.MISMATCH:
            self.app.dialogs.choose(
                "Genome type mismatch",
                f"{gene.name} needs a {gene.required_genome_type} genome, but yours is locked to "
                f"{config.locked_genome_string}. It can be installed, but its effects stay inactive.",
                [("Install anyway", do_install, theme.WARN), ("Cancel", None, None)])
        else:
            do_install()

    # ------------------------------------------------------------------ configuration

    def _refresh_config(self):
        config = self.builder.config()
        for field, _, options in CONFIG_FIELDS:
            dpg.set_value(self.config_radios[field], _label(getattr(config, field)))
        dpg.configure_item(self.config_radios["polarity"], enabled=config.polarity_applies)
        dpg.set_value(self.genome_summary, f"{config.genome_string}  ·  {config.virion_type}")
        dpg.configure_item(self.genome_summary, color=theme.ACCENT)

        if not config.is_locked:
            status, color = "Not locked yet. The first lock is free.", theme.WARN
        elif config.has_pending_changes:
            status, color = f"Locked: {config.locked_genome_string}. Changes not locked in.", theme.WARN
        else:
            status, color = f"Locked: {config.locked_genome_string}", theme.GOOD
        dpg.set_value(self.config_status, status)
        dpg.configure_item(self.config_status, color=color)

        cost = "free" if config.lock_cost == 0 else f"{config.lock_cost} EP"
        dpg.configure_item(self.lock_button, label=f"Lock configuration ({cost})",
                           enabled=config.needs_lock)
        dpg.bind_item_theme(self.lock_button, theme.button_theme(
            theme.darken(theme.WARN, 0.3) if config.needs_lock else (44, 56, 76, 255)))
        dpg.configure_item(self.reset_button, enabled=config.has_pending_changes)

    def _on_config(self, sender, app_data, user_data):
        field, options = user_data
        value = next(o for o in options if _label(o) == app_data)
        self._apply(self.builder.set_config(**{field: value}))

    def _on_lock(self, sender, app_data, user_data):
        if self._apply(self.builder.lock_config()):
            self.app.toasts.show(f"Locked {self.builder.config().locked_genome_string}", theme.GOOD, 2.5)

    def _on_reset(self, sender, app_data, user_data):
        self.builder.reset_config()
        self.refresh()

    # ------------------------------------------------------------------ details

    def _refresh_details(self):
        dpg.delete_item(self.details, children_only=True)
        parent = self.details
        if self.selected is None:
            dpg.add_text("Select a gene, ORF, terminator or effect to see its details. Hover genes for a "
                         "quick summary.", parent=parent, color=theme.TEXT_DIM, wrap=0)
            return
        kind, key = self.selected
        if kind == "gene":
            gene = self.api.get_gene(key)
            if gene:
                self._gene_details(parent, gene)
        elif kind == "effect":
            effect = self.api.get_effect(key)
            if effect:
                self._effect_details(parent, effect)
        elif kind == "orf":
            item = next((i for i in self.builder.installed() if i.key == key), None)
            self._heading(parent, key, theme.ORF_COLORS[0])
            dpg.add_text("Open reading frame: everything after it is translated together, up to the next "
                         "terminator. Several typed genes make a polyprotein that needs a Self-cleavage "
                         "gene to split.", parent=parent, wrap=0, color=theme.TEXT_DIM)
            if item is not None:
                for gene_id in item.orf_gene_ids:
                    gene = self.api.get_gene(gene_id)
                    if gene:
                        dpg.add_text(f"• {gene.name}  ({gene.length:,} bp)", parent=parent)
        elif kind == "terminator":
            self._heading(parent, key, theme.TERMINATOR_COLOR)
            dpg.add_text("Stops translation of the ORFs before it (at the terminator chance). Removing it is "
                         "free.", parent=parent, wrap=0, color=theme.TEXT_DIM)

    def _heading(self, parent, text, color):
        heading = dpg.add_text(text, parent=parent, color=color, wrap=0)
        theme.use_font(heading, self.app.fonts.large)

    def _row(self, parent, label, value, color=None):
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_text(f"{label}:", color=theme.TEXT_DIM)
            dpg.add_text(str(value), color=color or theme.TEXT, wrap=0)

    def _gene_details(self, parent, gene):
        self._heading(parent, gene.name, theme.gene_color(gene))
        self._row(parent, "Set", gene.set_name)
        self._row(parent, "Cost", f"{gene.install_cost} EP",
                  theme.GOOD if self.builder.can_afford(gene.id) else theme.BAD)
        self._row(parent, "Length", f"{gene.length:,} bp")
        type_name = self.api.gene_type_name(gene.id)
        if type_name != "None":
            self._row(parent, "Makes protein", type_name, theme.CATEGORY_COLORS["Protein"])
        if gene.is_utr:
            self._row(parent, "UTR", "fixed at the 5' end, one per genome")
        if gene.is_polymerase:
            self._row(parent, "Polymerase", "one per genome")
        if gene.required_genome_type:
            fit = self.builder.genome_fit(gene.id)
            color = {GenomeFit.MATCH: theme.GOOD, GenomeFit.MISMATCH: theme.BAD}.get(fit, theme.WARN)
            self._row(parent, "Needs genome", f"{gene.required_genome_type}  ({fit.value})", color)
        if gene.description:
            dpg.add_text(gene.description, parent=parent, wrap=0)
        dpg.add_spacer(height=4, parent=parent)
        dpg.add_text(f"Effects ({len(gene.effect_ids)})", parent=parent, color=theme.TEXT_DIM)
        for effect_id in gene.effect_ids:
            effect = self.api.get_effect(effect_id)
            if effect:
                dpg.add_selectable(label=f"• {effect.name}  ({effect.effect_type})", parent=parent,
                                   callback=self._on_effect_click, user_data=effect.id)

    def _on_effect_click(self, sender, app_data, user_data):
        self.select(("effect", user_data))

    def _entity_name(self, entity_id):
        entity = self.api.get_entity(entity_id) if entity_id is not None else None
        return entity.name if entity else f"ID {entity_id}"

    def _effect_details(self, parent, effect):
        self._heading(parent, effect.name, theme.REACTION_COLORS.get(effect.effect_type, theme.INFO))
        self._row(parent, "Type", effect.effect_type + ("  (global)" if effect.is_global else ""))
        if effect.category:
            self._row(parent, "Category", effect.category)
        if effect.description:
            dpg.add_text(effect.description, parent=parent, wrap=0)
        kind = effect.effect_type
        if kind == EffectType.TRANSITION.value:
            self._row(parent, "Chance", f"{effect.chance}% per turn")
            for inp in effect.inputs:
                kept = "" if inp.get("consumed", True) else "  (kept)"
                dpg.add_text(f"in:  {inp.get('amount', 1)}× {self._entity_name(inp.get('entity_id'))} "
                             f"@ {inp.get('location')}{kept}", parent=parent, wrap=0)
            for out in effect.outputs:
                name = "genome" if out.get("is_unpack_genome") else self._entity_name(out.get("entity_id"))
                dpg.add_text(f"out: {out.get('amount', 1)}× {name} @ {out.get('location')}",
                             parent=parent, wrap=0, color=theme.GOOD)
            if effect.interferon_production:
                self._row(parent, "Interferon", effect.interferon_production, theme.WARN)
            if effect.antibody_response:
                self._row(parent, "Antibody response", effect.antibody_response, theme.BAD)
        elif kind == EffectType.CHANGE_LOCATION.value:
            what = self._entity_name(effect.affected_entity_id) if effect.affected_entity_id else "any entity"
            self._row(parent, "Moves", f"{what}: {effect.source_location} → {effect.target_location}")
            self._row(parent, "Chance", f"{effect.location_change_chance}% per turn")
        elif kind == EffectType.TRANSLATION.value:
            templates = ", ".join(f"{self._entity_name(t.get('entity_id'))} @ {t.get('location')}"
                                  for t in effect.templates)
            self._row(parent, "Template", templates)
            self._row(parent, "Chance", f"{effect.translation_chance}% per template and turn")
            self._row(parent, "ORFs", effect.orf_targeting)
        elif kind == EffectType.MODIFY_EFFECT.value:
            target = (self.api.get_effect(effect.target_effect_id).name
                      if effect.target_effect_id and self.api.get_effect(effect.target_effect_id)
                      else f"category {effect.target_category}")
            self._row(parent, "Modifies", target)
            self._row(parent, "Chance ×", f"{effect.chance_modifier / 100:.2f}")
        elif kind == EffectType.SELF_CLEAVAGE.value:
            self._row(parent, "Cleavage", f"{effect.self_cleavage_chance}% per polyprotein and turn")

    # ------------------------------------------------------------------ blueprint

    def _refresh_blueprint(self):
        bp = self.builder.blueprint()
        area = self.blueprint_area
        dpg.delete_item(area, children_only=True)
        self._heading(area, f"{bp.genome_string}  ·  {bp.virion_type}", theme.ACCENT)
        dpg.add_text("The virus as it will play (locked configuration)." if bp.is_locked
                     else "The configuration is not locked yet; this shows the defaults.",
                     parent=area, color=theme.TEXT_DIM)
        with dpg.collapsing_header(label=f"Genome  ·  {bp.total_length:,} bp  ·  {bp.gene_count} genes, "
                                         f"{bp.orf_count} ORFs, {bp.terminator_count} terminators",
                                   parent=area, default_open=True):
            dpg.add_text("Genome entities: " + ", ".join(bp.genome_entity_names))
            genes = {i.key: i.gene for i in bp.items if i.kind is ItemKind.GENE}
            for index, span in enumerate(bp.orf_spans):
                color = theme.ORF_COLORS[index % len(theme.ORF_COLORS)]
                with dpg.tree_node(label=f"{span.name}  ({sum(genes[g].length for g in span.gene_ids if g in genes):,} bp)",
                                   default_open=True):
                    for gene_id in span.gene_ids:
                        if gene_id in genes:
                            dpg.add_text(f"{genes[gene_id].name}", color=color)
        with dpg.collapsing_header(label=f"Protein types  ·  {len(bp.enabled_types)}", parent=area,
                                   default_open=True):
            dpg.add_text(", ".join(bp.enabled_types) or "none", wrap=0,
                         color=theme.CATEGORY_COLORS["Protein"])
        for title, effects in (("Gene effects", bp.gene_effects), ("Global effects", bp.global_effects)):
            with dpg.collapsing_header(label=f"{title}  ·  {len(effects)} active", parent=area,
                                       default_open=True):
                with dpg.table(header_row=True, policy=dpg.mvTable_SizingStretchProp, row_background=True):
                    dpg.add_table_column(label="Effect", init_width_or_weight=0.6)
                    dpg.add_table_column(label="Type", init_width_or_weight=0.4)
                    for effect in effects:
                        with dpg.table_row():
                            dpg.add_text(effect.name)
                            dpg.add_text(effect.effect_type,
                                         color=theme.lighten(theme.REACTION_COLORS.get(effect.effect_type,
                                                                                       theme.INFO), 0.3))

    # ------------------------------------------------------------------ actions

    def _on_play(self, sender, app_data, user_data):
        readiness = self.api.round_readiness()
        config = self.builder.config()
        cost = "free" if config.lock_cost == 0 else f"{config.lock_cost} EP"

        def lock_and_play():
            if self._apply(self.builder.lock_config()):
                self.app.start_round()

        def discard_and_play():
            self.builder.reset_config()
            self.app.start_round()

        if readiness is RoundReadiness.NO_GENES:
            self.app.toasts.show("Install at least one gene before playing.", theme.WARN)
        elif readiness is RoundReadiness.CONFIG_NOT_LOCKED:
            self.app.dialogs.choose(
                "Lock configuration",
                f"Your genome and virion type must be locked before playing.\n\n"
                f"Lock {config.genome_string} · {config.virion_type} ({cost})?",
                [("Lock and play", lock_and_play, theme.darken(theme.GOOD, 0.25)), ("Cancel", None, None)])
        elif readiness is RoundReadiness.CONFIG_CHANGES_PENDING:
            self.app.dialogs.choose(
                "Unlocked changes",
                f"You changed the configuration since locking {config.locked_genome_string}.",
                [(f"Lock changes ({cost}) and play", lock_and_play, theme.darken(theme.WARN, 0.25)),
                 ("Discard changes and play", discard_and_play, None), ("Cancel", None, None)])
        else:
            self.app.start_round()

    def _on_quit(self, sender, app_data, user_data):
        self.app.dialogs.choose("Quit game", "Quit this game and return to the main menu? Progress is lost.",
                                [("Quit game", self.app.quit_game, theme.darken(theme.BAD, 0.3)),
                                 ("Keep playing", None, None)])
