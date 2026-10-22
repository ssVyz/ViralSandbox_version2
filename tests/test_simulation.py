"""Headless tests for the simulation engine.

These run the real game rules with no window and no display, which is the
whole point of simulation.py being separate from play_module.py.
"""
import random
import subprocess
import sys

import pytest

from conftest import ROOT, build_loaded_game
from simulation import SimulationEngine, SimulationState


# --------------------------------------------------------------------------
# The separation itself
# --------------------------------------------------------------------------

def test_engine_does_not_import_tkinter():
    """simulation.py must stay importable on a machine with no display."""
    code = (
        "import sys; import simulation; "
        "assert 'tkinter' not in sys.modules, 'simulation.py pulled in tkinter'; "
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


def test_engine_runs_without_any_tk_objects(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(1))
    engine.run_until_end(max_turns=10)
    assert engine.sim_state.turn == 10
    assert "tkinter" not in sys.modules


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def _final(game, seed, turns=25):
    engine = SimulationEngine(game, rng=random.Random(seed))
    for _ in range(turns):
        if engine.sim_state.is_ended:
            break
        engine.run_turn()
    return engine.sim_state


def test_same_seed_gives_identical_run(database):
    a = _final(build_loaded_game(database), seed=42)
    b = _final(build_loaded_game(database), seed=42)
    assert a.turn == b.turn
    assert a.entities == b.entities
    assert a.log == b.log
    assert a.interferon_level == b.interferon_level


def test_different_seeds_diverge(database):
    """Guards against the rng being accidentally ignored."""
    a = _final(build_loaded_game(database), seed=1)
    b = _final(build_loaded_game(database), seed=2)
    assert a.log != b.log


# --------------------------------------------------------------------------
# Behaviour
# --------------------------------------------------------------------------

def test_starts_with_ten_extracellular_virions(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(0))
    assert sum(engine.sim_state.entities.values()) == 10
    assert engine.sim_state.turn == 0
    assert not engine.sim_state.is_ended
    assert "Extracellular" in engine.sim_state.locations_entered


def test_loaded_virus_replicates_and_wins(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    state = engine.run_until_end(max_turns=400)
    assert state.is_ended
    assert state.is_victory, "a fully-loaded virus should reach the win threshold"
    assert not state.extinction
    assert state.turn > 1


def test_bare_virus_only_decays(bare_game):
    """With no genes installed there are no replication effects.

    Global effects (degradation) still apply, so the starting virions decay
    rather than holding steady - but the population can never grow.
    """
    engine = SimulationEngine(bare_game, rng=random.Random(3))
    start = sum(engine.sim_state.entities.values())

    peak = start
    for _ in range(30):
        engine.run_turn()
        peak = max(peak, sum(engine.sim_state.entities.values()))

    state = engine.sim_state
    assert peak <= start, "a gene-less virus must never replicate"
    assert sum(state.entities.values()) <= start
    assert not state.is_victory
    assert state.categories_produced == set() or "Virion" in state.categories_produced


def test_history_records_one_entry_per_turn(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(5))
    engine.run_until_end(max_turns=12)
    turns = [t for t, _ in engine.sim_state.history]
    assert turns == list(range(0, engine.sim_state.turn + 1))


def test_win_threshold_is_respected(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    state = engine.run_until_end(max_turns=400)
    virions = sum(
        c for (eid, _), c in state.entities.items()
        if (e := loaded_game.database.get_entity(eid))
        and e.category in ("Virion", "Viral complex")
    )
    assert virions >= loaded_game.win_threshold


def test_count_population_matches_the_win_check(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    state = engine.run_until_end(max_turns=400)
    total, virions = engine.count_population()
    assert state.is_victory
    assert virions >= loaded_game.win_threshold
    assert total >= virions


def test_end_early_stops_the_run(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    engine.run_turn()
    engine.end_early()
    turn = engine.sim_state.turn

    engine.run_turn()

    assert engine.sim_state.is_ended
    assert not engine.sim_state.is_victory and not engine.sim_state.extinction
    assert engine.sim_state.turn == turn, "an ended run must not advance"
    assert "Round ended early" in engine.sim_state.log[-1]


def test_history_uses_the_population_groups(loaded_game):
    from simulation import POPULATION_GROUPS
    engine = SimulationEngine(loaded_game, rng=random.Random(5))
    engine.run_until_end(max_turns=5)
    for _, counts in engine.sim_state.history:
        assert tuple(counts) == POPULATION_GROUPS


# --------------------------------------------------------------------------
# The observer seam the UI relies on
# --------------------------------------------------------------------------

def test_callbacks_fire_the_way_the_ui_expects(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    turns, ends, milestones, refreshes = [], [], [], []

    engine.on_turn_complete = lambda: turns.append(engine.sim_state.turn)
    engine.on_game_end = lambda: ends.append(engine.sim_state.turn)
    engine.on_milestone_achieved = milestones.append
    engine.on_active_milestones_changed = lambda: refreshes.append(1)

    state = engine.run_until_end(max_turns=400)

    assert len(turns) == state.turn, "one redraw per turn"
    assert turns == sorted(turns)
    assert len(ends) == 1, "game end reported exactly once"
    assert milestones, "milestones should be achieved on a winning run"
    assert len(milestones) == len(set(milestones)), "no milestone awarded twice"
    assert refreshes


def test_engine_runs_fine_with_no_callbacks_registered(loaded_game):
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    assert engine.on_turn_complete is None
    engine.run_until_end(max_turns=50)   # must not raise


def test_milestones_award_evolution_points(loaded_game):
    before = loaded_game.evolution_points
    engine = SimulationEngine(loaded_game, rng=random.Random(7))
    engine.run_until_end(max_turns=400)
    assert loaded_game.achieved_milestones
    assert loaded_game.evolution_points > before
