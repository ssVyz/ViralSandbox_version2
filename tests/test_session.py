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
from game_state import RoundReadiness
from session import GameFlowError, GamePhase, GameSession, StartResult, RoundOutcome


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
    assert session.phase is GamePhase.NO_GAME
    assert session.start(DEFAULT_DB) is StartResult.OK
    assert session.is_active
    assert session.phase is GamePhase.BUILDING
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
    gs = s.game_state
    affordable = next(gid for gid in gs.available_genes if gs.can_install_gene(gid)[0])
    assert gs.install_gene(affordable)[0]
    assert gs.lock_config()[0]
    return s


def _play_round(session, victory=False):
    """Run a round to its end without simulating it; optionally as a victory."""
    engine = session.start_round()
    if victory:
        engine.sim_state.is_ended = True
        engine.sim_state.is_victory = True
    return session.finish_round()


def test_round_needs_a_ready_virus():
    s = GameSession(starting_hand_size=7)
    s.start(DEFAULT_DB)
    assert s.game_state.round_readiness() is RoundReadiness.NO_GENES
    with pytest.raises(GameFlowError):
        s.start_round()
    assert s.phase is GamePhase.BUILDING


def test_round_cannot_start_twice(session):
    session.start_round()
    assert session.phase is GamePhase.PLAYING
    with pytest.raises(GameFlowError):
        session.start_round()


def test_finish_round_needs_a_round(session):
    with pytest.raises(GameFlowError):
        session.finish_round()


def test_victory_ends_the_game_without_advancing_the_round(session):
    before = session.game_state.current_round
    assert _play_round(session, victory=True) is RoundOutcome.VICTORY
    assert session.game_state.current_round == before
    assert session.game_state.game_won
    assert session.phase is GamePhase.GAME_OVER


def test_ordinary_round_advances_and_offers_genes(session):
    before = session.game_state.current_round
    assert _play_round(session) is RoundOutcome.CONTINUE
    assert session.game_state.current_round == before + 1
    assert not session.game_state.game_over
    assert session.phase is GamePhase.GENE_OFFER
    assert session.offer


def test_unfinished_round_is_ended_early(session):
    engine = session.start_round()
    session.finish_round()
    assert engine.sim_state.is_ended
    assert "Round ended early" in engine.sim_state.log[-1]


def test_running_out_of_rounds_ends_the_game(session):
    max_rounds = session.game_state.max_rounds
    outcomes = []
    for _ in range(max_rounds):
        outcomes.append(_play_round(session))
        if session.phase is GamePhase.GENE_OFFER:
            session.decline_offer()

    assert outcomes[-1] is RoundOutcome.OUT_OF_ROUNDS
    assert all(o is RoundOutcome.CONTINUE for o in outcomes[:-1])
    assert session.game_state.game_over
    assert session.phase is GamePhase.GAME_OVER


def test_end_discards_the_game(session):
    session.end()
    assert not session.is_active
    assert session.game_state is None
    assert session.database is None
    assert session.phase is GamePhase.NO_GAME


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
    _play_round(session)
    offered = list(session.offer)
    before = len(session.game_state.available_genes)

    session.accept_gene(offered[0])

    assert len(session.game_state.available_genes) == before + 1
    assert offered[0] in session.game_state.available_genes
    assert session.phase is GamePhase.BUILDING
    assert session.offer == []


def test_only_offered_genes_can_be_accepted(session):
    _play_round(session)
    not_offered = next(gid for gid in session.game_state.database.genes
                       if gid not in session.offer)
    with pytest.raises(ValueError):
        session.accept_gene(not_offered)
    assert session.phase is GamePhase.GENE_OFFER


def test_declining_returns_to_building(session):
    _play_round(session)
    hand = list(session.game_state.available_genes)
    session.decline_offer()
    assert session.phase is GamePhase.BUILDING
    assert session.game_state.available_genes == hand


def test_no_offer_when_every_gene_is_held(session):
    gs = session.game_state
    gs.available_genes = [gid for gid in gs.database.genes if gid not in gs.installed_genes]
    assert _play_round(session) is RoundOutcome.CONTINUE
    assert session.phase is GamePhase.BUILDING, "nothing to offer, straight back to building"


def test_offers_are_reproducible_with_a_seeded_rng():
    def run(seed):
        random.seed(seed)
        s = GameSession(starting_hand_size=7, rng=random.Random(seed))
        s.start(DEFAULT_DB)
        return s.draw_gene_offer()

    assert run(5) == run(5)
    assert run(5) != run(6), "the rng must actually be used"
