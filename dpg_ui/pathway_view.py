"""Life-cycle graph: the virus's reaction network in a node editor.

Entity nodes (one per entity and compartment) sit in compartment columns from
outside the cell inward; reaction nodes sit next to the earliest compartment
they touch. Links run from what a reaction uses to what it makes. Nodes can
be dragged around; the minimap shows where you are.
"""
from collections import defaultdict

import dearpygui.dearpygui as dpg

from models import CellLocation
from . import theme

LOCATIONS = [loc.value for loc in CellLocation]
STATE_WIDTH = 270            # room for an entity node
REACTION_WIDTH = 350         # room for a reaction node
REACTIONS_PER_COLUMN = 5     # then reactions wrap into another sub-column
COLUMN_GAP = 40
ROW_GAP = 26
NAME_LIMIT = 36


def _short(text: str, limit: int = NAME_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


class PathwayView:
    def __init__(self, view, parent):
        self.view = view
        self.pathway = None
        with dpg.group(parent=parent):
            with dpg.group(horizontal=True):
                self.show_global = dpg.add_checkbox(label="Global effects", default_value=True,
                                                    callback=self._on_option)
                self.show_kept = dpg.add_checkbox(label="Templates and catalysts", default_value=True,
                                                  callback=self._on_option)
                dpg.add_button(label="Re-arrange", callback=self._on_option)
                dpg.add_spacer(width=12)
                for kind, color in theme.REACTION_COLORS.items():
                    dpg.add_text("■", color=theme.lighten(color, 0.2))
                    dpg.add_text(kind, color=theme.TEXT_DIM)
            dpg.add_text("Your virus's life cycle as it will play: entities per compartment (columns, outside → in) "
                         "and the active effects that turn them into each other, with their chance per turn. "
                         "Drag nodes to untangle; drag the canvas with the middle mouse button.",
                         color=theme.TEXT_DIM, wrap=1100)
            self.editor = dpg.add_node_editor(minimap=True,
                                              minimap_location=dpg.mvNodeMiniMap_Location_BottomRight,
                                              width=-1, height=-1)

    def show(self, pathway):
        """Draw ``pathway``; keeps the current arrangement if nothing changed."""
        if pathway != self.pathway:
            self.pathway = pathway
            self._build()

    def _on_option(self, sender, app_data, user_data):
        self._build()

    def _build(self):
        dpg.delete_item(self.editor, children_only=True)
        if self.pathway is None:
            return
        states = {s.key: s for s in self.pathway.states}
        reactions = [r for r in self.pathway.reactions
                     if dpg.get_value(self.show_global) or not r.is_global]
        show_kept = dpg.get_value(self.show_kept)

        def flows_in(reaction):
            return [f for f in reaction.inputs if show_kept or f.consumed]

        used = {s.key for s in states.values() if s.is_start}
        for r in reactions:
            used.update(f.state for f in flows_in(r) + list(r.outputs))
        column = {key: LOCATIONS.index(states[key].location) if states[key].location in LOCATIONS else 0
                  for key in used}

        # Each reaction sits in the column of the outermost compartment it touches
        anchor = {}
        for reaction in reactions:
            cols = [column[f.state] for f in flows_in(reaction) + list(reaction.outputs) if f.state in column]
            anchor[id(reaction)] = min(cols) if cols else 0

        # Only compartments with something in them get a column; long reaction stacks wrap
        column_x, x = {}, 0
        for index in sorted(set(column.values()) | set(anchor.values())):
            column_x[index] = x
            count = sum(1 for a in anchor.values() if a == index)
            x += STATE_WIDTH + max(1, -(-count // REACTIONS_PER_COLUMN)) * REACTION_WIDTH + COLUMN_GAP
        reactions_placed = defaultdict(int)

        next_y = defaultdict(lambda: 60.0)

        def place(x: float, height: float) -> list:
            y = next_y[x]
            next_y[x] = y + height + ROW_GAP
            return [int(x + 20), int(y)]

        for index, x in column_x.items():
            header = dpg.add_node(label=LOCATIONS[index].upper(), pos=[x + 20, 0],
                                  draggable=False, parent=self.editor)
            dpg.bind_item_theme(header, theme.node_theme(theme.PANEL_HI))

        in_attr, out_attr, links = {}, {}, []
        for key in sorted(used, key=lambda k: (column[k], not states[k].is_start, states[k].name)):
            state = states[key]
            color = theme.GOLD if state.is_start else theme.category_color(state.category)
            label = ("START  " if state.is_start else "") + _short(state.name, 34)
            with dpg.node(label=label, pos=place(column_x[column[key]], 86), parent=self.editor) as node:
                with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input) as a_in:
                    dpg.add_text(state.location, color=theme.TEXT_DIM)
                with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as a_out:
                    dpg.add_text(state.category or "any entity", color=color)
            dpg.bind_item_theme(node, theme.node_theme(theme.darken(color, 0.45)))
            in_attr[key], out_attr[key] = a_in, a_out

        for reaction in reactions:
            inputs = flows_in(reaction)
            index = anchor[id(reaction)]
            sub_column = reactions_placed[index] // REACTIONS_PER_COLUMN
            reactions_placed[index] += 1
            x = column_x[index] + STATE_WIDTH + sub_column * REACTION_WIDTH
            height = 66 + 25 * (len(inputs) + len(reaction.outputs)) + (26 if reaction.modified_by else 0)
            with dpg.node(label=_short(reaction.name), pos=place(x, height), parent=self.editor) as node:
                with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                    chance = f"{reaction.chance:.0f}% per turn"
                    if round(reaction.chance, 1) != round(reaction.base_chance, 1):
                        chance += f"  (base {reaction.base_chance:.0f}%)"
                    scope = "  ·  global" if reaction.is_global else ""
                    dpg.add_text(f"{reaction.kind}  ·  {chance}{scope}",
                                 color=theme.BAD if reaction.chance <= 0 else theme.TEXT_DIM)
                    if reaction.kind == "Self-cleavage" and reaction.chance <= 0:
                        dpg.add_text("Never cleaves: no Self-cleavage gene in this ORF", color=theme.BAD)
                    if reaction.modified_by:
                        dpg.add_text("modified by " + ", ".join(reaction.modified_by),
                                     color=theme.INFO, wrap=300)
                for flow in inputs:
                    with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input) as attr:
                        kept = "  (kept)" if not flow.consumed else ""
                        dpg.add_text(f"{flow.amount}× {_short(states[flow.state].name, 30)}{kept}")
                    links.append((out_attr[flow.state], attr))
                for flow in reaction.outputs:
                    with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output) as attr:
                        dpg.add_text(f"→ {flow.amount}× {_short(states[flow.state].name, 30)}",
                                     color=theme.category_color(states[flow.state].category))
                    links.append((attr, in_attr[flow.state]))
            dpg.bind_item_theme(node, theme.node_theme(theme.REACTION_COLORS.get(reaction.kind, theme.PANEL_HI)))

        for source, target in links:
            dpg.add_node_link(source, target, parent=self.editor)
