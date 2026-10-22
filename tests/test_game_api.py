"""Headless tests for game_api, the layer every UI talks to.

They drive a whole playthrough the way a UI would, and guard the boundary:
UI modules may only reach the game through game_api (and models).
"""
import ast
import glob
import os
import random
import re
import subprocess
import sys

import pytest

import settings
from conftest import ROOT, DEFAULT_DB
from game_api import (GameAPI, GameFlowError, GamePhase, GenomeFit, ItemKind, Round,
                      RoundOutcome, RoundReadiness, StartResult, get_version)
from simulation import SimulationEngine

UI_MODULES = (["main.py", "main_menu.py", "builder.py", "play_module.py", "database_editor.py"]
              + sorted(os.path.relpath(path, ROOT) for path in glob.glob(os.path.join(ROOT, "dpg_ui", "*.py"))))
LOGIC_MODULES = {"game_state", "simulation", "session", "database", "settings"}


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never read or write the real settings.json."""
    monkeypatch.setattr(settings, "SETTINGS_FILE", str(tmp_path / "settings.json"))


@pytest.fixture
def api():
    random.seed(21)
    a = GameAPI(rng=random.Random(21))
    assert a.new_game(DEFAULT_DB) is StartResult.OK
    return a


def _make_ready(api):
    builder = api.builder
    gene = next(g for g in builder.hand() if builder.can_install_gene(g.id)[0])
    assert builder.install_gene(gene.id)[0]
    assert builder.lock_config()[0]
    return gene


# --------------------------------------------------------------------------
# The boundary itself
# --------------------------------------------------------------------------

def _imported_modules(path):
    """Top-level modules a file imports (relative imports within a UI package excluded)."""
    tree = ast.parse(open(os.path.join(ROOT, path), encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("module", UI_MODULES)
def test_ui_reaches_the_game_only_through_game_api(module):
    leaked = _imported_modules(module) & LOGIC_MODULES
    assert not leaked, f"{module} imports {leaked}; use game_api instead"


def test_game_api_does_not_import_tkinter():
    code = (
        "import sys; import game_api; "
        "assert 'tkinter' not in sys.modules, 'game_api.py pulled in tkinter'; "
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def test_version_comes_from_pyproject():
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    declared = re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)
    assert get_version() == declared
    assert GameAPI().version == declared


def test_invalid_settings_are_rejected_and_not_saved():
    a = GameAPI()
    bad = a.settings
    bad["game"]["starting_hand_size"] = 99
    saved, message = a.save_settings(bad)
    assert not saved and "Starting Hand Size" in message
    assert not os.path.exists(settings.SETTINGS_FILE)

    bad["game"]["starting_hand_size"] = None  # what a UI passes for unparsable text
    assert not a.save_settings(bad)[0]


def test_valid_settings_are_saved_and_used_for_the_next_game():
    a = GameAPI()
    new = a.settings
    new["game"]["starting_hand_size"] = 4
    assert a.save_settings(new)[0]
    assert a.settings["game"]["starting_hand_size"] == 4

    assert a.new_game(DEFAULT_DB) is StartResult.OK
    assert len(a.builder.hand()) == 4


def test_settings_copy_cannot_change_the_api():
    a = GameAPI()
    a.settings["game"]["starting_hand_size"] = 1
    assert a.settings["game"]["starting_hand_size"] != 1


def test_default_database_path_resolves_the_shipped_database():
    assert os.path.samefile(GameAPI().default_database_path(), DEFAULT_DB)


def test_content_database_for_an_editor():
    db = GameAPI().create_content_database()
    db.new_database()
    assert db.entities, "a new database comes with the protected starter entities"


# --------------------------------------------------------------------------
# Game lifecycle and phases
# --------------------------------------------------------------------------

def test_no_game_means_no_game_calls():
    a = GameAPI()
    assert a.phase is GamePhase.NO_GAME
    with pytest.raises(GameFlowError):
        a.status()
    with pytest.raises(GameFlowError):
        a.builder


def test_full_round_trip(api):
    assert api.round_readiness() is RoundReadiness.NO_GENES
    _make_ready(api)
    assert api.round_readiness() is RoundReadiness.READY

    rnd = api.start_round()
    assert api.phase is GamePhase.PLAYING
    assert api.current_round is rnd
    for _ in range(5):
        rnd.step()
    assert rnd.turn == 5

    assert api.finish_round() is RoundOutcome.CONTINUE
    assert api.current_round is None
    assert api.phase is GamePhase.GENE_OFFER

    offer = api.gene_offer
    assert offer.completed_round == 1
    assert offer.max_rounds == api.status().max_rounds
    api.accept_offered_gene(offer.genes[0].id)
    assert api.phase is GamePhase.BUILDING
    assert api.builder.in_hand(offer.genes[0].id)

    api.end_game()
    assert api.phase is GamePhase.NO_GAME
    assert not api.is_game_active


def test_declining_an_offer(api):
    _make_ready(api)
    api.start_round()
    api.finish_round()
    hand = [g.id for g in api.builder.hand()]
    api.decline_gene_offer()
    assert api.phase is GamePhase.BUILDING
    assert [g.id for g in api.builder.hand()] == hand


def test_round_refused_until_ready(api):
    with pytest.raises(GameFlowError):
        api.start_round()


def test_genome_is_frozen_outside_building(api):
    gene = _make_ready(api)
    api.start_round()
    with pytest.raises(GameFlowError):
        api.builder.remove_item(gene.id)
    with pytest.raises(GameFlowError):
        api.builder.set_config(nucleic_acid="DNA")


def test_builder_of_an_ended_game_refuses_changes(api):
    old = api.builder
    api.new_game(DEFAULT_DB)
    with pytest.raises(GameFlowError):
        old.add_orf()


# --------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------

def test_config_changes_and_validation(api):
    builder = api.builder
    assert builder.set_config(strandedness="double")[0]
    config = builder.config()
    assert config.strandedness == "double"
    assert not config.polarity_applies
    assert config.genome_string == "dsRNA"
    assert config.needs_lock and config.lock_cost == 0

    ok, message = builder.set_config(nucleic_acid="XNA", strandedness="single")
    assert not ok and "nucleic acid" in message
    assert builder.config().strandedness == "double", "a rejected change changes nothing"

    builder.lock_config()
    assert builder.config().is_locked
    builder.set_config(virion_type="Unenveloped")
    assert api.round_readiness() in (RoundReadiness.NO_GENES,
                                     RoundReadiness.CONFIG_CHANGES_PENDING)
    builder.reset_config()
    assert not builder.config().has_pending_changes


def test_pending_changes_block_a_round(api):
    _make_ready(api)
    api.builder.set_config(virion_type="Unenveloped")
    assert api.round_readiness() is RoundReadiness.CONFIG_CHANGES_PENDING


def test_markers_alone_are_not_a_playable_virus(api):
    api.builder.add_orf()
    api.builder.lock_config()
    assert api.round_readiness() is RoundReadiness.NO_GENES


def test_terminator_chance_is_clamped(api):
    assert api.builder.set_terminator_chance(250) == 100
    assert api.builder.set_terminator_chance(0) == 1
    assert api.builder.terminator_chance == 1


def test_installed_items_describe_the_genome(api):
    builder = api.builder
    builder.add_orf()
    gene = _make_ready(api)
    builder.add_terminator()

    items = builder.installed()
    kinds = [item.kind for item in items]
    assert ItemKind.ORF in kinds and ItemKind.GENE in kinds and ItemKind.TERMINATOR in kinds

    orf = next(item for item in items if item.kind is ItemKind.ORF)
    gene_item = next(item for item in items if item.kind is ItemKind.GENE)
    assert gene_item.gene.id == gene.id and gene_item.key == gene.id
    if gene_item.position > orf.position:
        assert gene.id in orf.orf_gene_ids

    for item in items:
        assert builder.remove_item(item.key)[0]
    assert builder.installed() == []
    assert builder.in_hand(gene.id), "a removed gene goes back to the hand"


def test_orf_spans_show_terminator_readthrough(api):
    builder = api.builder
    builder.add_orf()
    affordable = [g for g in builder.hand() if g.install_cost <= 40 and not g.is_utr]
    first, second = affordable[:2]
    builder.install_gene(first.id)
    builder.add_terminator()
    builder.install_gene(second.id)

    span = builder.orf_spans()[0]
    assert span.gene_ids == (first.id,)
    assert span.readthrough_gene_ids == ()

    builder.set_terminator_chance(50)
    span = builder.orf_spans()[0]
    assert span.readthrough_gene_ids == (second.id,)


def _small_genes(builder, count):
    genes = [g for g in builder.hand() if g.install_cost <= 30 and not g.is_utr]
    assert len(genes) >= count, "fixture hand has too few cheap genes"
    return genes[:count]


def test_move_item_to_reorders_in_one_step(api):
    builder = api.builder
    a, b, c = _small_genes(builder, 3)
    for gene in (a, b, c):
        builder.install_gene(gene.id)
    builder.add_orf()                                   # ORF-1 at the end

    moved, renames = builder.move_item_to("ORF-1", 0)
    assert moved and renames == {}
    assert [i.key for i in builder.installed()] == ["ORF-1", a.id, b.id, c.id]

    moved, _ = builder.move_item_to(a.id, 99)           # clamped to the end
    assert moved
    assert [i.key for i in builder.installed()][-1] == a.id
    assert builder.move_item_to(a.id, 3) == (False, {}), "already there"


def test_move_item_to_renames_markers(api):
    builder = api.builder
    builder.add_orf()                                   # ORF-1
    gene, = _small_genes(builder, 1)
    builder.install_gene(gene.id)
    builder.add_orf()                                   # ORF-2 after the gene

    moved, renames = builder.move_item_to("ORF-2", 0)
    assert moved
    assert renames == {"ORF-2": "ORF-1", "ORF-1": "ORF-2"}


def test_nothing_moves_in_front_of_a_utr(bare_game):
    utr = next(g for g in bare_game.database.genes.values() if g.is_utr)
    plain = next(g for g in bare_game.database.genes.values() if not g.is_utr)
    bare_game.evolution_points = 1000
    bare_game.available_genes = [utr.id, plain.id]
    bare_game.install_gene(plain.id)
    bare_game.install_gene(utr.id)
    assert bare_game.installed_genes[0] == utr.id

    assert bare_game.move_item_to(plain.id, 0) == (False, {})
    assert bare_game.move_item_to(utr.id, 1) == (False, {})


def test_install_gene_at_a_position(api):
    builder = api.builder
    a, b = _small_genes(builder, 2)
    builder.add_orf()
    builder.install_gene(a.id)
    assert builder.install_gene(b.id, position=1)[0]
    assert [i.key for i in builder.installed()] == ["ORF-1", b.id, a.id]


def test_pathway_of_a_loaded_virus(loaded_game):
    from session import GameSession
    from game_api import Builder
    session = GameSession()
    session.game_state, session.database = loaded_game, loaded_game.database
    pathway = Builder(session).pathway()

    states = {s.key: s for s in pathway.states}
    start = [s for s in pathway.states if s.is_start]
    assert len(start) == 1 and start[0].location == "Extracellular"
    assert start[0].entity_id == loaded_game.get_starting_virion_id()

    for reaction in pathway.reactions:
        assert 0 <= reaction.chance <= 100
        for flow in reaction.inputs + reaction.outputs:
            assert flow.state in states, f"{reaction.name} refers to an unknown state"

    kinds = {r.kind for r in pathway.reactions}
    assert {"Transition", "Change location", "Translation"} <= kinds
    assert not any(r.kind == "Modify effect" for r in pathway.reactions)

    # Genome unpacking produces the locked genome type
    genome_ids = set(loaded_game.virus_config.get_genome_entity_ids())
    unpacked = {states[f.state].entity_id for r in pathway.reactions
                if r.effect_id and any(o.get('is_unpack_genome') for o in
                                       loaded_game.get_effect(r.effect_id).outputs)
                for f in r.outputs}
    assert genome_ids <= unpacked

    # Modify effects show up in the chance of what they target
    modified = [r for r in pathway.reactions if r.modified_by]
    assert modified and any(r.chance != r.base_chance for r in modified)

    # A multi-protein ORF is translated into a polyprotein that is cleaved
    polys = [s for s in pathway.states if s.key.startswith("poly:")]
    assert polys
    cleavages = [r for r in pathway.reactions if r.kind == "Self-cleavage"]
    assert {r.inputs[0].state for r in cleavages} == {p.key for p in polys}


def test_genome_fit(bare_game):
    needy = next(g for g in bare_game.database.genes.values() if g.required_genome_type)
    plain = next(g for g in bare_game.database.genes.values() if not g.required_genome_type)
    assert bare_game.genome_fit(plain) is GenomeFit.ANY
    assert bare_game.genome_fit(needy) is GenomeFit.UNLOCKED

    bare_game.lock_config()
    expected = (GenomeFit.MATCH
                if needy.required_genome_type == bare_game.virus_config.get_genome_string()
                else GenomeFit.MISMATCH)
    assert bare_game.genome_fit(needy) is expected


def test_blueprint_reports_the_locked_virus(api):
    gene = _make_ready(api)
    bp = api.builder.blueprint()
    assert bp.is_locked
    assert bp.gene_count == 1
    assert bp.total_length == gene.length
    assert bp.genome_entity_names


# --------------------------------------------------------------------------
# Rounds
# --------------------------------------------------------------------------

def test_snapshot_population_adds_up(api):
    _make_ready(api)
    rnd = api.start_round()
    snapshot = rnd.snapshot()
    assert snapshot.turn == 0
    assert snapshot.total_entities == 10 == snapshot.virion_count
    assert sum(e.count for e in snapshot.population) == snapshot.total_entities
    assert all(e.location == "Extracellular" for e in snapshot.population)

    for _ in range(10):
        result = rnd.step()
        snap = result.snapshot
        assert sum(e.count for e in snap.population) == snap.total_entities
        if result.ended:
            break


def test_steps_report_milestones_and_end(loaded_game):
    """A fully-loaded virus wins; each milestone and the end are reported once."""
    rnd = Round(SimulationEngine(loaded_game, rng=random.Random(7)), loaded_game)
    achieved, ends = [], 0
    for _ in range(400):
        result = rnd.step()
        achieved.extend(result.milestones_achieved)
        ends += result.ended
        if result.snapshot.is_over:
            break

    assert ends == 1
    assert result.snapshot.is_victory
    assert result.snapshot.virion_count >= rnd.win_threshold
    assert achieved and len(achieved) == len(set(achieved))
    assert {m.id for m in rnd.summary().milestones_achieved} == set(achieved)
    turn = rnd.turn
    assert rnd.step().ended is False, "stepping a finished round does nothing"
    assert rnd.turn == turn


def test_history_window_and_tracked_milestones(api):
    _make_ready(api)
    rnd = api.start_round()
    for _ in range(8):
        rnd.step()
    assert len(rnd.history()) == rnd.turn + 1
    assert [t for t, _ in rnd.history(3)] == [rnd.turn - 2, rnd.turn - 1, rnd.turn]
    assert set(rnd.history()[0][1]) == set(rnd.population_groups)

    tracked = rnd.tracked_milestones()
    assert tracked == sorted(tracked, key=lambda s: s.milestone.id)
    # First round: everything achieved so far was achieved in this round
    achieved_now = {m.id for m in rnd.summary().milestones_achieved}
    assert {s.milestone.id for s in tracked if s.achieved} == achieved_now


def test_ending_a_round_early(api):
    _make_ready(api)
    rnd = api.start_round()
    rnd.step()
    rnd.end_early()
    assert rnd.is_over
    assert rnd.summary().ended_early
    assert "Round ended early" in rnd.log()[-1]
    assert api.finish_round() is RoundOutcome.CONTINUE
