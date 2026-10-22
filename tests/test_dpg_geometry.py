"""Headless tests for the DearPyGui UI's cell geometry (no window needed)."""
import random

import pytest

from dpg_ui.cell_geometry import (DOT_BUDGET, MAX_DOTS_PER_ENTRY, CellLayout, allocate_dots,
                                  dots_for)
from models import CellLocation

LOCATIONS = [loc.value for loc in CellLocation]


def test_one_dot_per_entity_while_few():
    assert [dots_for(n) for n in (0, 1, 7, 20)] == [0, 1, 7, 20]


def test_dots_grow_slowly_and_are_capped():
    counts = [21, 100, 1_000, 10_000, 1_000_000]
    dots = [dots_for(n) for n in counts]
    assert dots == sorted(dots)
    assert all(20 <= d <= MAX_DOTS_PER_ENTRY for d in dots)
    assert dots_for(10**9) == MAX_DOTS_PER_ENTRY


def test_allocation_respects_the_budget_and_keeps_every_entry_visible():
    counts = [10_000] * 40 + [1]
    dots = allocate_dots(counts)
    assert sum(dots) <= DOT_BUDGET + len(counts)   # rounding up to one dot each at most
    assert all(d >= 1 for d in dots)
    assert allocate_dots([3, 0, 5]) == [3, 0, 5]


@pytest.mark.parametrize("location", LOCATIONS)
def test_sampled_points_lie_in_their_compartment(location):
    layout = CellLayout(560, 500)
    rng = random.Random(1)
    for _ in range(200):
        x, y = layout.sample(location, rng)
        assert 0 <= x <= layout.width and 0 <= y <= layout.height
        if location not in (CellLocation.MEMBRANE.value,):
            assert layout.contains(location, x, y), (location, x, y)


@pytest.mark.parametrize("location", LOCATIONS)
def test_hit_testing_agrees_with_sampling(location):
    layout = CellLayout(560, 500)
    rng = random.Random(2)
    hits = [layout.locate(*layout.sample(location, rng)) for _ in range(200)]
    assert hits.count(location) / len(hits) > 0.9, (location, set(hits))


def test_points_outside_the_drawing_are_nowhere():
    layout = CellLayout(400, 300)
    assert layout.locate(-5, 10) is None
    assert layout.locate(10, 999) is None
