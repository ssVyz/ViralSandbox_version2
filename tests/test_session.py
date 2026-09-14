"""Headless tests for the game session flow.

These exercise starting a game, the round loop, and gene offers without
opening the main menu.
"""
import json
import os
import random
import subprocess
import sys

import pytest

from conftest import ROOT, DEFAULT_DB
from session import GameSession, StartResult, RoundOutcome


# --------------------------------------------------------------------------
# The separation itself
# --------------------------------------------------------------------------

def test_session_does_not_import_tkinter():
    code = (
        "import sys; import session; "
        "assert 'tkinter' not in sys.modules, 'session.py pulled in tkinter'; "
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


# --------------------------------------------------------------------------
# Starting a game
# --------------------------------------------------------------------------

def test_start_succeeds_on_the_default_database():
    session = GameSession(starting_hand_size=7)
    assert session.start(DEFAULT_DB) is StartResult.OK
    assert session.is_active
    assert session.game_state is not None
    assert session.database is not None
    assert len(session.game_state.available_genes) == 7
    assert session.game_state.evolution_points == 100


def test_start_reports_a_missing_file(tmp_path):
    session = GameSession()
    assert session.start(str(tmp_path / "nope.json")) is StartResult.LOAD_FAILED
    assert not session.is_active


def test_start_reports_a_database_with_no_genes(tmp_path):
    """A structurally valid database that contains no genes."""
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({
        "entities": [], "effects": [], "genes": [], "milestones": [],
    }))
    session = GameSession()
    assert session.start(str(empty)) is StartResult.NO_GENES
    assert not session.is_active


def test_start_reports_when_no_genes_can_be_drawn():
    session = GameSession(starting_hand_size=0)
    assert session.start(DEFAULT_DB) is StartResult.NOT_ENOUGH_GENES
    assert not session.is_active


def test_failed_start_leaves_an_existing_game_untouched(tmp_path):
    session = GameSession(starting_hand_size=7)
    assert session.start(DEFAULT_DB) is StartResult.OK
    original = session.game_state

    assert session.start(str(tmp_path / "nope.json")) is StartResult.LOAD_FAILED
    assert session.game_state is original, "a failed start must not wipe the game"


# --------------------------------------------------------------------------
# The round loop
# --------------------------------------------------------------------------

@pytest.fixture
def session():
    s = GameSession(starting_hand_size=7, rng=random.Random(11))
    random.seed(11)
    assert s.start(DEFAULT_DB) is StartResult.OK
    return s


def test_victory_ends_the_game_without_advancing_the_round(session):
    before = session.game_state.current_round
    assert session.finish_round(victory=True) is RoundOutcome.VICTORY
    assert session.game_state.current_round == before


def test_ordinary_round_advances_and_continues(session):
    before = session.game_state.current_round
    assert session.finish_round() is RoundOutcome.CONTINUE
    assert session.game_state.current_round == before + 1
    assert not session.game_state.game_over


def test_running_out_of_rounds_ends_the_game(session):
    max_rounds = session.game_state.max_rounds
    outcomes = [session.finish_round() for _ in range(max_rounds)]

    assert outcomes[-1] is RoundOutcome.OUT_OF_ROUNDS
    assert all(o is RoundOutcome.CONTINUE for o in outcomes[:-1])
    assert session.game_state.game_over


def test_end_discards_the_game(session):
    session.end()
    assert not session.is_active
    assert session.game_state is None
    assert session.database is None


# --------------------------------------------------------------------------
# Gene offers
# --------------------------------------------------------------------------

def test_offer_excludes_genes_already_held_or_installed(session):
    gs = session.game_state
    gs.installed_genes.append(sorted(gs.database.genes.keys())[0])

    offered = session.draw_gene_offer()

    assert offered
    assert not set(offered) & set(gs.available_genes)
    assert not set(offered) & set(gs.installed_genes)


def test_offer_size_respects_the_per_round_setting(session):
    session.game_state.genes_offered_per_round = 3
    assert len(session.draw_gene_offer()) == 3


def test_offer_is_empty_once_every_gene_is_held(session):
    gs = session.game_state
    gs.available_genes = list(gs.database.genes.keys())
    assert session.draw_gene_offer() == []


def test_accept_gene_adds_it_to_the_hand(session):
    offered = session.draw_gene_offer()
    before = len(session.game_state.available_genes)

    session.accept_gene(offered[0])

    assert len(session.game_state.available_genes) == before + 1
    assert offered[0] in session.game_state.available_genes


def test_offers_are_reproducible_with_a_seeded_rng():
    def run(seed):
        random.seed(seed)
        s = GameSession(starting_hand_size=7, rng=random.Random(seed))
        s.start(DEFAULT_DB)
        return s.draw_gene_offer()

    assert run(5) == run(5)
    assert run(5) != run(6), "the rng must actually be used"
