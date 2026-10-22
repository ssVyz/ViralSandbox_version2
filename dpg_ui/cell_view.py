"""The animated cell: every entity is a swarm of particles in its compartment.

Particle positions drift a little every frame (the GPU-drawn drawlist keeps
this cheap); counts follow the round's snapshots. Hovering a compartment
highlights it and lists what is inside.
"""
import random
from collections import defaultdict

import dearpygui.dearpygui as dpg

from models import CellLocation
from . import theme
from .cell_geometry import CellLayout, allocate_dots

LOCATIONS = [loc.value for loc in CellLocation]
PARTICLE_RADIUS = {"Virion": 4.0, "Viral complex": 3.6, "DNA": 3.0, "RNA": 2.6, "Protein": 2.1}
JITTER = 0.9  # pixels per frame


class CellView:
    def __init__(self, parent, width: int, height: int):
        self.parent = parent
        self.rng = random.Random(42)
        self.population = ()
        self.particles: dict = {}  # (name, location) -> list of [item, x, y]
        self.hovered = None
        self._frame = 0
        with dpg.drawlist(width=width, height=height, parent=parent) as self.drawlist:
            self.static_layer = dpg.add_draw_layer()
            self.highlight_layer = dpg.add_draw_layer()
            self.particle_layer = dpg.add_draw_layer()
            self.label_layer = dpg.add_draw_layer()
        with dpg.item_handler_registry() as handlers:
            dpg.add_item_hover_handler(callback=self._on_hover)
        dpg.bind_item_handler_registry(self.drawlist, handlers)
        self.inspector = dpg.add_text("Hover a compartment to see what is inside.", parent=parent,
                                      color=theme.TEXT_DIM, wrap=width)
        self.resize(width, height)

    # ------------------------------------------------------------------ layout

    def resize(self, width: int, height: int):
        self.layout = CellLayout(width, height)
        dpg.configure_item(self.drawlist, width=width, height=height)
        dpg.configure_item(self.inspector, wrap=width)
        self._draw_static()
        dpg.delete_item(self.particle_layer, children_only=True)
        self.particles = {}
        self._sync_particles()
        self._draw_highlight()

    def _draw_static(self):
        layer = self.static_layer
        dpg.delete_item(layer, children_only=True)
        L = self.layout
        dpg.draw_rectangle((0, 0), (L.width, L.height), fill=theme.COMPARTMENT_FILL["Extracellular"],
                           color=theme.BORDER, parent=layer)
        dpg.draw_circle((L.cx, L.cy), L.radius + 9, color=theme.with_alpha(theme.MEMBRANE_COLOR, 40),
                        thickness=8, parent=layer)
        dpg.draw_circle((L.cx, L.cy), L.radius, fill=theme.COMPARTMENT_FILL["Cytosol"],
                        color=theme.MEMBRANE_COLOR, thickness=4, parent=layer)
        for ex, ey, er in L.endosomes:
            dpg.draw_circle((ex, ey), er, fill=theme.COMPARTMENT_FILL["Endosome"],
                            color=theme.with_alpha(theme.MEMBRANE_COLOR, 160), thickness=2, parent=layer)
        for radius in L.er_radii:
            dpg.draw_polyline(L.er_arc_points(radius), color=theme.with_alpha(theme.ER_COLOR, 170),
                              thickness=5, parent=layer)
        nx, ny, nr = L.nucleus
        dpg.draw_circle((nx, ny), nr, fill=theme.COMPARTMENT_FILL["Nucleus"],
                        color=theme.with_alpha(theme.ER_COLOR, 220), thickness=3, parent=layer)
        dpg.draw_circle((nx, ny), nr + 5, color=theme.with_alpha(theme.ER_COLOR, 120), thickness=1.5,
                        parent=layer)

        dpg.delete_item(self.label_layer, children_only=True)
        self.labels = {}
        for location in LOCATIONS:
            x, y = L.label_pos(location)
            self.labels[location] = dpg.draw_text((x, y), location, color=theme.with_alpha(theme.TEXT, 200),
                                                  size=15, parent=self.label_layer)

    # ------------------------------------------------------------------ data

    def update(self, population: tuple):
        """Follow a new snapshot's population."""
        self.population = population
        self._sync_particles()
        totals = defaultdict(int)
        for entry in population:
            totals[entry.location] += entry.count
        for location, label in self.labels.items():
            count = totals.get(location, 0)
            dpg.configure_item(label, text=f"{location}  {count:,}" if count else location)
        if self.hovered:
            self._show_inspector(self.hovered)

    def _sync_particles(self):
        entries = [e for e in self.population if e.count > 0]
        wanted = dict(zip(((e.name, e.location) for e in entries),
                          allocate_dots([e.count for e in entries])))
        meta = {(e.name, e.location): e for e in entries}

        for key in list(self.particles):
            if key not in wanted:
                for item, _, _ in self.particles.pop(key):
                    dpg.delete_item(item)

        for key, count in wanted.items():
            swarm = self.particles.setdefault(key, [])
            entry = meta[key]
            color = theme.POLYPROTEIN_COLOR if entry.is_polyprotein else theme.category_color(entry.category)
            radius = PARTICLE_RADIUS.get(entry.category, 2.4)
            while len(swarm) > count:
                dpg.delete_item(swarm.pop()[0])
            while len(swarm) < count:
                x, y = self.layout.sample(entry.location, self.rng)
                item = dpg.draw_circle((x, y), radius, color=theme.with_alpha(color, 255),
                                       fill=theme.with_alpha(color, 210), parent=self.particle_layer)
                swarm.append([item, x, y])

    def animate(self):
        """Let every particle drift; half of them per frame to keep it cheap."""
        self._frame += 1
        parity = self._frame % 2
        gauss = self.rng.gauss
        contains = self.layout.contains
        for (_, location), swarm in self.particles.items():
            for index in range(parity, len(swarm), 2):
                particle = swarm[index]
                x = particle[1] + gauss(0, JITTER)
                y = particle[2] + gauss(0, JITTER)
                if contains(location, x, y):
                    particle[1], particle[2] = x, y
                    dpg.configure_item(particle[0], center=(x, y))

    # ------------------------------------------------------------------ inspector

    def _on_hover(self, sender, app_data, user_data):
        x, y = dpg.get_drawing_mouse_pos()
        location = self.layout.locate(x, y)
        if location != self.hovered:
            self.hovered = location
            self._draw_highlight()
            self._show_inspector(location)

    def _show_inspector(self, location):
        if location is None:
            return
        entries = sorted((e for e in self.population if e.location == location), key=lambda e: -e.count)
        total = sum(e.count for e in entries)
        if not entries:
            text = f"{location}: empty"
        else:
            parts = ", ".join(f"{e.name} {e.count:,}" for e in entries[:6])
            more = f", +{len(entries) - 6} more" if len(entries) > 6 else ""
            text = f"{location}: {total:,}  —  {parts}{more}"
        dpg.set_value(self.inspector, text)
        dpg.configure_item(self.inspector, color=theme.TEXT)

    def _draw_highlight(self):
        layer = self.highlight_layer
        dpg.delete_item(layer, children_only=True)
        L, location, color = self.layout, self.hovered, theme.with_alpha(theme.GOLD, 200)
        if location is None:
            return
        nx, ny, nr = L.nucleus
        if location == CellLocation.EXTRACELLULAR.value:
            dpg.draw_rectangle((2, 2), (L.width - 2, L.height - 2), color=color, thickness=3, parent=layer)
        elif location == CellLocation.MEMBRANE.value:
            dpg.draw_circle((L.cx, L.cy), L.radius, color=color, thickness=9, parent=layer)
        elif location == CellLocation.CYTOSOL.value:
            dpg.draw_circle((L.cx, L.cy), L.radius - 6, color=color, thickness=3, parent=layer)
        elif location == CellLocation.NUCLEUS.value:
            dpg.draw_circle((nx, ny), nr + 2, color=color, thickness=4, parent=layer)
        elif location == CellLocation.ENDOSOME.value:
            for ex, ey, er in L.endosomes:
                dpg.draw_circle((ex, ey), er + 2, color=color, thickness=3, parent=layer)
        elif location == CellLocation.ER.value:
            for radius in L.er_radii:
                dpg.draw_polyline(L.er_arc_points(radius), color=color, thickness=7, parent=layer)
