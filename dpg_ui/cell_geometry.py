"""Geometry of the cell drawing: compartment shapes and where particles go.

Pure Python (no DearPyGui), so it can be tested headlessly. Coordinates are
drawlist pixels, y pointing down.
"""
import math
from typing import Optional

from models import CellLocation

EXTRACELLULAR = CellLocation.EXTRACELLULAR.value
MEMBRANE = CellLocation.MEMBRANE.value
ENDOSOME = CellLocation.ENDOSOME.value
ER = CellLocation.ER.value
CYTOSOL = CellLocation.CYTOSOL.value
NUCLEUS = CellLocation.NUCLEUS.value

MAX_DOTS_PER_ENTRY = 60
DOT_BUDGET = 520  # particles drawn at most, across all entries


def dots_for(count: int) -> int:
    """Particles drawn for ``count`` entities: one each up to 20, then logarithmic."""
    if count <= 0:
        return 0
    if count <= 20:
        return count
    return min(MAX_DOTS_PER_ENTRY, int(20 + 8 * math.log2(count / 20)))


def allocate_dots(counts: list, budget: int = DOT_BUDGET) -> list:
    """Particles per entry, scaled down proportionally if the total exceeds ``budget``.

    Every non-empty entry keeps at least one particle.
    """
    wanted = [dots_for(c) for c in counts]
    total = sum(wanted)
    if total <= budget:
        return wanted
    scale = budget / total
    return [max(1, int(w * scale)) if w else 0 for w in wanted]


class CellLayout:
    """A stylized cell: membrane, cytosol, nucleus, ER around the nucleus, and
    a few endosomes near the membrane, with the extracellular space around."""

    ER_ARC = (math.radians(196), math.radians(344))  # above the nucleus

    def __init__(self, width: float, height: float):
        self.width, self.height = width, height
        self.cx, self.cy = width * 0.5, height * 0.53
        self.radius = min(width, height) * 0.40
        r = self.radius
        self.nucleus = (self.cx + r * 0.14, self.cy + r * 0.12, r * 0.30)
        nr = self.nucleus[2]
        self.er_radii = [nr + r * k for k in (0.07, 0.12, 0.17)]
        self.endosomes = [(self.cx + r * 0.68 * math.cos(a), self.cy + r * 0.68 * math.sin(a), r * 0.09)
                          for a in map(math.radians, (148, 190, 232))]

    # ---- shapes for drawing

    def er_arc_points(self, radius: float, steps: int = 28) -> list:
        nx, ny, _ = self.nucleus
        a0, a1 = self.ER_ARC
        return [(nx + radius * math.cos(a0 + (a1 - a0) * i / steps),
                 ny + radius * math.sin(a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]

    def label_pos(self, location: str) -> tuple:
        """Where a compartment's name is written."""
        r = self.radius
        nx, ny, nr = self.nucleus
        positions = {
            EXTRACELLULAR: (10, 8),
            MEMBRANE: (self.cx + r * 0.62, self.cy - r * 0.98),
            ENDOSOME: (self.endosomes[1][0] - r * 0.02, self.endosomes[1][1] + r * 0.12),
            ER: (nx - r * 0.12, ny - nr - r * 0.30),
            CYTOSOL: (self.cx - r * 0.48, self.cy + r * 0.52),
            NUCLEUS: (nx - r * 0.13, ny + nr * 0.25),
        }
        return positions[location]

    # ---- hit testing

    def _in_nucleus(self, x, y, margin=0.0) -> bool:
        nx, ny, nr = self.nucleus
        return math.hypot(x - nx, y - ny) <= nr - margin

    def _in_er(self, x, y, margin=0.0) -> bool:
        nx, ny, _ = self.nucleus
        d = math.hypot(x - nx, y - ny)
        if not self.er_radii[0] - 6 + margin <= d <= self.er_radii[-1] + 6 - margin:
            return False
        angle = math.atan2(y - ny, x - nx) % (2 * math.pi)
        return self.ER_ARC[0] <= angle <= self.ER_ARC[1]

    def _in_endosome(self, x, y, margin=0.0) -> bool:
        return any(math.hypot(x - ex, y - ey) <= er - margin for ex, ey, er in self.endosomes)

    def _distance_from_center(self, x, y) -> float:
        return math.hypot(x - self.cx, y - self.cy)

    def locate(self, x: float, y: float) -> Optional[str]:
        """The compartment at a point, or None outside the drawing."""
        if not (0 <= x <= self.width and 0 <= y <= self.height):
            return None
        d = self._distance_from_center(x, y)
        if d > self.radius + 7:
            return EXTRACELLULAR
        if d >= self.radius - 7:
            return MEMBRANE
        if self._in_nucleus(x, y):
            return NUCLEUS
        if self._in_er(x, y):
            return ER
        if self._in_endosome(x, y):
            return ENDOSOME
        return CYTOSOL

    def contains(self, location: str, x: float, y: float) -> bool:
        """Whether a particle of ``location`` may sit at (x, y)."""
        d = self._distance_from_center(x, y)
        if location == EXTRACELLULAR:
            return (d > self.radius + 12 and 6 <= x <= self.width - 6 and 6 <= y <= self.height - 6)
        if location == MEMBRANE:
            return abs(d - self.radius) <= 4
        if location == NUCLEUS:
            return self._in_nucleus(x, y, margin=5)
        if location == ER:
            return self._in_er(x, y, margin=3)
        if location == ENDOSOME:
            return self._in_endosome(x, y, margin=3)
        if location == CYTOSOL:
            return (d < self.radius - 10 and not self._in_nucleus(x, y, margin=-6)
                    and not self._in_er(x, y, margin=-4) and not self._in_endosome(x, y, margin=-4))
        return False

    # ---- placing particles

    def sample(self, location: str, rng) -> tuple:
        """A random point inside a compartment."""
        r = self.radius
        if location == MEMBRANE:
            a = rng.uniform(0, 2 * math.pi)
            d = r + rng.uniform(-3, 3)
            return self.cx + d * math.cos(a), self.cy + d * math.sin(a)
        if location == ER:
            nx, ny, _ = self.nucleus
            a = rng.uniform(*self.ER_ARC)
            d = rng.choice(self.er_radii) + rng.uniform(-2, 2)
            return nx + d * math.cos(a), ny + d * math.sin(a)
        if location == NUCLEUS:
            nx, ny, nr = self.nucleus
            a, d = rng.uniform(0, 2 * math.pi), (nr - 6) * math.sqrt(rng.random())
            return nx + d * math.cos(a), ny + d * math.sin(a)
        if location == ENDOSOME:
            ex, ey, er = rng.choice(self.endosomes)
            a, d = rng.uniform(0, 2 * math.pi), (er - 4) * math.sqrt(rng.random())
            return ex + d * math.cos(a), ey + d * math.sin(a)

        # Extracellular and cytosol: rejection sampling within the bounding area
        for _ in range(200):
            if location == CYTOSOL:
                a, d = rng.uniform(0, 2 * math.pi), (r - 10) * math.sqrt(rng.random())
                x, y = self.cx + d * math.cos(a), self.cy + d * math.sin(a)
            else:
                x, y = rng.uniform(6, self.width - 6), rng.uniform(6, self.height - 6)
            if self.contains(location, x, y):
                return x, y
        return self.label_pos(location)
