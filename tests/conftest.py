"""Shared fixtures for headless simulation tests."""
import os
import random
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database import GameDatabase          # noqa: E402
from game_state import GameState           # noqa: E402

DEFAULT_DB = os.path.join(ROOT, "default_database.json")


@pytest.fixture
def database():
    db = GameDatabase()
    assert db.load(DEFAULT_DB), "failed to load default_database.json"
    return db


@pytest.fixture
def bare_game(database):
    """A virus with no genes installed - it can do nothing but sit there."""
    random.seed(0)
    return GameState.new_game(database=database, starting_ep=100, starting_hand_size=5)


def build_loaded_game(database, seed=1234, ep=100000, hand=40):
    """A heavily-loaded virus: two ORFs and every gene we can afford.

    Deterministic for a given seed, so tests can assert on exact outcomes.
    """
    random.seed(seed)
    gs = GameState.new_game(database=database, starting_ep=ep, starting_hand_size=hand)
    gs.install_orf()
    for gid in sorted(gs.available_genes):
        can, _ = gs.can_install_gene(gid)
        if can:
            gs.install_gene(gid)
    gs.install_orf()
    if gs.needs_config_lock():
        gs.lock_config()
    return gs


@pytest.fixture
def loaded_game(database):
    return build_loaded_game(database)
