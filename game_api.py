"""
Application layer for Viral Sandbox: the one module a user interface talks to.

A UI imports this module (plus :mod:`models` for the content dataclasses and
enums) and nothing else from the game - never game_state, simulation, session,
database or settings. Everything a player can do, and everything a UI needs to
draw, goes through:

* :class:`GameAPI` - settings, version, starting and ending a game, the round
  loop and the gene offers between rounds. One per application run.
* :class:`Builder` - the genome editor of the current game (``api.builder``).
* :class:`Round` - the play round in progress (``api.current_round``).

Conventions:

* Player-facing problems (not enough EP, ...) come back as ``(ok, message)``
  tuples or result enums for the UI to present.
* Calls made in the wrong :class:`GamePhase` raise :class:`GameFlowError`;
  they are bugs in the caller.
* Model objects (Gene, Effect, ViralEntity, Milestone) are shared with the
  game: read them, never modify them. Everything else handed out is an
  immutable snapshot.

ui_interface.md documents every touch point. This module must never import
tkinter.
"""
import copy
import os
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import settings as app_settings
from database import GameDatabase
from game_state import GameState, GenomeFit, RoundReadiness, VirusConfig
from models import CellLocation, EntityCategory, Effect, EffectType, Gene, Milestone, ViralEntity
from session import GameFlowError, GamePhase, GameSession, RoundOutcome, StartResult
from simulation import (INTERFERON_MAX, POPULATION_GROUPS, SimulationEngine,
                        effect_modifiers, modified_chance)

__all__ = [
    "GameAPI", "Builder", "Round", "get_version",
    # Enums and errors
    "GamePhase", "StartResult", "RoundOutcome", "RoundReadiness", "GenomeFit",
    "ItemKind", "GameFlowError",
    # Snapshots
    "GameStatus", "ConfigView", "InstalledItem", "OrfSpan", "Blueprint",
    "PathwayState", "PathwayFlow", "PathwayReaction", "Pathway",
    "GeneOffer", "PopulationEntry", "RoundSnapshot", "MilestoneStatus",
    "TurnResult", "RoundSummary",
    # Content editing
    "GameDatabase",
    # Constants
    "WINDOW_MODES", "HAND_SIZE_MIN", "HAND_SIZE_MAX",
    "NUCLEIC_ACIDS", "STRANDEDNESS_OPTIONS", "POLARITIES", "VIRION_TYPES",
    "TERMINATOR_CHANCE_MIN", "TERMINATOR_CHANCE_MAX",
    "INTERFERON_MAX", "POPULATION_GROUPS",
]

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
PYPROJECT_FILE = os.path.join(APP_ROOT, "pyproject.toml")

WINDOW_MODES = app_settings.WINDOW_MODES
HAND_SIZE_MIN = app_settings.HAND_SIZE_MIN
HAND_SIZE_MAX = app_settings.HAND_SIZE_MAX

NUCLEIC_ACIDS = VirusConfig.NUCLEIC_ACIDS
STRANDEDNESS_OPTIONS = VirusConfig.STRANDEDNESS_OPTIONS
POLARITIES = VirusConfig.POLARITIES
VIRION_TYPES = VirusConfig.VIRION_TYPES

TERMINATOR_CHANCE_MIN = GameState.TERMINATOR_CHANCE_MIN
TERMINATOR_CHANCE_MAX = GameState.TERMINATOR_CHANCE_MAX


def get_version() -> str:
    """The game version, read from pyproject.toml - its single source of truth."""
    try:
        with open(PYPROJECT_FILE, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


# --------------------------------------------------------------------------
# Snapshots handed to the UI
# --------------------------------------------------------------------------

class ItemKind(Enum):
    """What an entry in the installed genome is."""
    GENE = "gene"
    ORF = "orf"
    TERMINATOR = "terminator"


@dataclass(frozen=True)
class GameStatus:
    """Headline numbers of the current game."""
    phase: GamePhase
    evolution_points: int
    current_round: int
    max_rounds: int
    genome_length: int  # bp of installed genes


@dataclass(frozen=True)
class ConfigView:
    """The virus configuration as the builder shows it.

    The four option fields are the pending (editable) values; the ``locked_*``
    and lock fields describe what is locked in for play.
    """
    nucleic_acid: str
    strandedness: str
    polarity: str
    virion_type: str
    genome_string: str          # of the pending config, e.g. "(+)ssRNA"
    polarity_applies: bool      # polarity only matters for single-stranded genomes
    is_locked: bool             # a configuration has been locked at least once
    locked_genome_string: str
    has_pending_changes: bool
    needs_lock: bool            # lock (or discard changes) before a round can start
    lock_cost: int              # EP; the first lock is free


@dataclass(frozen=True)
class InstalledItem:
    """One entry of the installed genome, in order."""
    kind: ItemKind
    key: object                 # pass back to Builder calls: gene ID, or marker name ("ORF-1", "Term-1")
    name: str                   # gene name or marker name
    position: int
    gene: Optional[Gene] = None
    genome_compatible: bool = True   # False: gene needs a different (or a locked) genome type
    domain_active: bool = True       # False: domain gene without its partner next to it
    domain_partner: str = ""         # entity name a domain gene needs next to it
    orf_gene_ids: tuple = ()         # ORFs only: the genes it translates

    @property
    def is_active(self) -> bool:
        """Whether this gene's effects will apply."""
        return self.genome_compatible and self.domain_active


@dataclass(frozen=True)
class OrfSpan:
    """The genes an ORF covers."""
    name: str
    gene_ids: tuple             # translated when every terminator stops translation
    readthrough_gene_ids: tuple  # reached only by reading through a terminator (terminator chance < 100%)


@dataclass(frozen=True)
class Blueprint:
    """A full read-only report of the virus as it will play (locked config)."""
    genome_string: str
    virion_type: str
    genome_entity_names: tuple
    is_locked: bool
    total_length: int
    gene_count: int
    orf_count: int
    terminator_count: int
    orf_spans: tuple            # OrfSpan, only those with genes
    items: tuple                # InstalledItem
    enabled_types: tuple        # protein type names, sorted
    gene_effects: tuple         # Effect, active effects of installed genes
    global_effects: tuple       # Effect, active global effects


@dataclass(frozen=True)
class PathwayState:
    """A node of the life-cycle graph: one entity (or polyprotein) in one location."""
    key: str                    # unique; PathwayFlow.state refers to it
    name: str
    location: str               # CellLocation value
    category: str               # EntityCategory value ("" for "any entity")
    entity_id: Optional[int]    # None for polyproteins and "any entity"
    is_start: bool = False      # every round starts with 10 of these


@dataclass(frozen=True)
class PathwayFlow:
    """An input or output of a reaction."""
    state: str                  # PathwayState.key
    amount: int = 1
    consumed: bool = True       # inputs only; False: needed but kept (templates, catalysts)


@dataclass(frozen=True)
class PathwayReaction:
    """Something that turns or moves entities, with its per-turn chance."""
    name: str
    kind: str                   # EffectType value: Transition, Change location, Translation, Self-cleavage
    inputs: tuple               # PathwayFlow
    outputs: tuple              # PathwayFlow
    base_chance: float          # %, as defined
    chance: float               # %, after Modify effects (clamped 0-100)
    modified_by: tuple          # names of the Modify effects changing it
    is_global: bool             # a global effect, active for every virus
    effect_id: Optional[int]    # None for polyprotein cleavage (built from Self-cleavage genes)


@dataclass(frozen=True)
class Pathway:
    """The virus's reaction network as it will play."""
    states: tuple               # PathwayState
    reactions: tuple            # PathwayReaction


@dataclass(frozen=True)
class GeneOffer:
    """The genes offered after a round; take one or none."""
    genes: tuple                # Gene
    completed_round: int
    max_rounds: int


@dataclass(frozen=True)
class PopulationEntry:
    """How many of one entity (or polyprotein) are in one location."""
    location: str               # CellLocation value
    name: str
    category: str               # EntityCategory value ("" if the entity is unknown)
    count: int
    is_polyprotein: bool = False


@dataclass(frozen=True)
class RoundSnapshot:
    """Everything a play screen shows, as of the latest turn."""
    turn: int
    total_entities: int
    virion_count: int
    interferon_level: float
    antibodies_active: int
    antibodies_stored: float
    population: tuple           # PopulationEntry
    is_over: bool
    is_victory: bool
    is_extinct: bool


@dataclass(frozen=True)
class MilestoneStatus:
    """A milestone worth showing during play."""
    milestone: Milestone
    achieved: bool              # False: active, i.e. its prerequisite is met


@dataclass(frozen=True)
class TurnResult:
    """What one call to Round.step() did."""
    snapshot: RoundSnapshot
    milestones_achieved: tuple  # IDs achieved this turn
    milestones_changed: bool    # the tracked milestone list changed; redraw it
    ended: bool                 # this turn ended the round (victory or extinction)


@dataclass(frozen=True)
class RoundSummary:
    """The result of a round, for an end-of-round screen."""
    is_victory: bool
    is_extinct: bool
    ended_early: bool
    turns: int
    milestones_achieved: tuple  # Milestone, achieved during this round
    evolution_points: int       # total after the round


# --------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------

class Builder:
    """The genome editor of the current game. Get it from ``GameAPI.builder``.

    Reads work in any phase; changes need the BUILDING phase.
    """

    def __init__(self, session: GameSession):
        self._session = session
        self._gs = session.game_state

    def _require_building(self):
        if self._session.game_state is not self._gs:
            raise GameFlowError("this builder belongs to a game that has ended")
        if self._session.phase is not GamePhase.BUILDING:
            raise GameFlowError(f"the genome can only change while BUILDING, "
                                f"not {self._session.phase.name}")

    # ---- reading

    def hand(self) -> list[Gene]:
        """Genes in hand, available to install."""
        return [gene for gene in map(self._gs.get_gene, self._gs.available_genes) if gene]

    def in_hand(self, gene_id: int) -> bool:
        return gene_id in self._gs.available_genes

    def installed(self) -> list[InstalledItem]:
        """The installed genome in order: genes, ORFs and terminators."""
        gs = self._gs
        orf_genes = {s['orf']: tuple(s['genes']) for s in gs.get_orf_structure()}
        items = []
        for position, key in enumerate(gs.installed_genes):
            if gs.is_orf(key):
                items.append(InstalledItem(ItemKind.ORF, key, key, position,
                                           orf_gene_ids=orf_genes.get(key, ())))
            elif gs.is_terminator(key):
                items.append(InstalledItem(ItemKind.TERMINATOR, key, key, position))
            else:
                gene = gs.get_gene(key)
                if gene is None:
                    continue
                partner = ""
                if gene.domain_entity_id is not None:
                    entity = gs.database.get_entity(gene.domain_entity_id)
                    partner = entity.name if entity else "Unknown"
                items.append(InstalledItem(
                    ItemKind.GENE, key, gene.name, position, gene=gene,
                    genome_compatible=gs.is_gene_genome_compatible(gene),
                    domain_active=gs.is_domain_gene_active_at(position),
                    domain_partner=partner,
                ))
        return items

    def is_installed(self, key) -> bool:
        return key in self._gs.installed_genes

    def orf_spans(self) -> list[OrfSpan]:
        """ORFs that cover at least one gene, in genome order."""
        gs = self._gs
        stopped = {s['orf']: tuple(s['genes']) for s in gs.get_orf_structure()}
        readthrough = gs.terminator_chance < GameState.TERMINATOR_CHANCE_MAX
        spans = []
        for s in gs.get_orf_ghost_structure():
            genes = stopped.get(s['orf'], ())
            extra = tuple(g for g in s['genes'] if g not in genes) if readthrough else ()
            if genes or extra:
                spans.append(OrfSpan(s['orf'], genes, extra))
        return spans

    def config(self) -> ConfigView:
        gs = self._gs
        pending = gs.pending_config
        return ConfigView(
            nucleic_acid=pending.nucleic_acid,
            strandedness=pending.strandedness,
            polarity=pending.polarity,
            virion_type=pending.virion_type,
            genome_string=pending.get_genome_string(),
            polarity_applies=pending.polarity_applies,
            is_locked=gs.virus_config.is_locked,
            locked_genome_string=gs.virus_config.get_genome_string(),
            has_pending_changes=gs.has_pending_changes(),
            needs_lock=gs.needs_config_lock(),
            lock_cost=gs.get_lock_cost(),
        )

    def blueprint(self) -> Blueprint:
        gs = self._gs
        config = gs.virus_config
        genome_names = []
        for entity_id in config.get_genome_entity_ids():
            entity = gs.database.get_entity(entity_id)
            if entity:
                genome_names.append(entity.name)
        return Blueprint(
            genome_string=config.get_genome_string(),
            virion_type=config.virion_type,
            genome_entity_names=tuple(genome_names),
            is_locked=config.is_locked,
            total_length=gs.get_total_genome_length(),
            gene_count=gs.get_installed_gene_count(),
            orf_count=gs.get_installed_orf_count(),
            terminator_count=gs.get_installed_terminator_count(),
            orf_spans=tuple(span for span in self.orf_spans() if span.gene_ids),
            items=tuple(self.installed()),
            enabled_types=tuple(sorted(gs.get_enabled_types())),
            gene_effects=tuple(gs.get_all_effects()),
            global_effects=tuple(gs.get_global_effects()),
        )

    def pathway(self) -> Pathway:
        """The reaction network of the virus as it will play (locked config).

        Built from the active effects: what each one consumes and produces, and
        where. Translation outputs the proteins of the ORFs it can target;
        multi-protein ORFs produce a polyprotein that a cleavage reaction (from
        the ORF's Self-cleavage genes) splits up. Modify effects show up as
        ``modified_by`` and in ``chance``, not as reactions of their own.
        """
        return _PathwayBuilder(self._gs, self.orf_spans()).build()

    @property
    def terminator_chance(self) -> int:
        return self._gs.terminator_chance

    @property
    def terminator_cost(self) -> int:
        return self._gs.terminator_cost

    def orf_cost(self) -> int:
        """EP cost of the next ORF (the first one is free)."""
        return self._gs.get_orf_cost()

    def can_afford(self, gene_id: int) -> bool:
        gene = self._gs.get_gene(gene_id)
        return gene is not None and gene.install_cost <= self._gs.evolution_points

    def can_install_gene(self, gene_id: int) -> tuple[bool, str]:
        return self._gs.can_install_gene(gene_id)

    def genome_fit(self, gene_id: int) -> GenomeFit:
        gene = self._gs.get_gene(gene_id)
        return self._gs.genome_fit(gene) if gene else GenomeFit.ANY

    def is_movable(self, key) -> bool:
        """Whether an installed item can be reordered (UTR genes stay at the 5' end)."""
        return self._gs.can_move_item(key)

    def can_lock_config(self) -> tuple[bool, str]:
        return self._gs.can_lock_config()

    def can_add_orf(self) -> tuple[bool, str]:
        return self._gs.can_install_orf()

    def can_add_terminator(self) -> tuple[bool, str]:
        return self._gs.can_install_terminator()

    # ---- changing (BUILDING only)

    def set_config(self, nucleic_acid: Optional[str] = None,
                   strandedness: Optional[str] = None,
                   polarity: Optional[str] = None,
                   virion_type: Optional[str] = None) -> tuple[bool, str]:
        """Change the pending configuration; omitted fields stay as they are."""
        self._require_building()
        return self._gs.set_pending_config(nucleic_acid=nucleic_acid,
                                           strandedness=strandedness,
                                           polarity=polarity,
                                           virion_type=virion_type)

    def lock_config(self) -> tuple[bool, str]:
        """Lock the pending configuration in for play (costs ``config().lock_cost``)."""
        self._require_building()
        return self._gs.lock_config()

    def reset_config(self) -> None:
        """Discard pending configuration changes."""
        self._require_building()
        self._gs.reset_pending_config()

    def set_terminator_chance(self, value: int) -> int:
        """Set the terminator chance (clamped to its range). Returns the value applied."""
        self._require_building()
        return self._gs.set_terminator_chance(value)

    def install_gene(self, gene_id: int, position: Optional[int] = None) -> tuple[bool, str]:
        """Install a gene from the hand: appended, or moved to ``position``
        (as move_item_to). UTR genes always go to the 5' end."""
        self._require_building()
        success, message = self._gs.install_gene(gene_id)
        if success and position is not None:
            self._gs.move_item_to(gene_id, position)
        return success, message

    def remove_item(self, key) -> tuple[bool, str]:
        """Remove an installed gene (back to the hand), ORF or terminator."""
        self._require_building()
        success, message, _rename_map = self._gs.remove_item(key)
        return success, message

    def add_orf(self) -> tuple[bool, str]:
        self._require_building()
        return self._gs.install_orf()

    def add_terminator(self) -> tuple[bool, str]:
        self._require_building()
        return self._gs.install_terminator()

    def move_item_up(self, key) -> tuple[bool, dict]:
        """Move an item toward the 5' end. Returns (moved, rename_map).

        Markers are renumbered by position, so a move can rename them;
        rename_map maps old marker keys to new ones.
        """
        self._require_building()
        return self._gs.move_item_up(key)

    def move_item_down(self, key) -> tuple[bool, dict]:
        """Move an item toward the 3' end. Returns (moved, rename_map)."""
        self._require_building()
        return self._gs.move_item_down(key)

    def move_item_to(self, key, position: int) -> tuple[bool, dict]:
        """Move an item so it ends up at ``position`` (for drag and drop).

        Clamped to the genome; nothing moves in front of a UTR. Returns
        (moved, rename_map) like move_item_up.
        """
        self._require_building()
        return self._gs.move_item_to(key, position)


class _PathwayBuilder:
    """Collects the states and reactions of Builder.pathway()."""

    def __init__(self, game_state: GameState, orf_spans: list):
        self._gs = game_state
        self._db = game_state.database
        self._orf_spans = [span for span in orf_spans if span.gene_ids]  # what translation can pick
        self._states: dict = {}
        self._reactions: list = []
        self._cleavages: set = set()

    def build(self) -> Pathway:
        gs = self._gs
        start = gs.get_starting_virion_id()
        self._entity(start, CellLocation.EXTRACELLULAR.value, is_start=True)

        effects = gs.get_all_effects() + gs.get_global_effects()
        modifiers = effect_modifiers(effects)
        modify_effects = [e for e in effects if e.effect_type == EffectType.MODIFY_EFFECT.value]

        for effect in effects:
            flows = self._flows(effect)
            if flows is None:
                continue
            inputs, outputs, base_chance = flows
            modified_by = tuple(
                m.name for m in modify_effects
                if m.target_effect_id == effect.id
                or (m.target_effect_id is None and m.target_category
                    and m.target_category == effect.category))
            self._reactions.append(PathwayReaction(
                name=effect.name, kind=effect.effect_type,
                inputs=tuple(inputs), outputs=tuple(outputs),
                base_chance=base_chance,
                chance=modified_chance(effect, base_chance, modifiers),
                modified_by=modified_by, is_global=effect.is_global, effect_id=effect.id,
            ))
        return Pathway(states=tuple(self._states.values()), reactions=tuple(self._reactions))

    def _flows(self, effect: Effect):
        """(inputs, outputs, base_chance) of an effect, or None if it moves nothing."""
        kind = effect.effect_type
        if kind == EffectType.TRANSITION.value:
            inputs = [PathwayFlow(self._entity(i.get('entity_id', 0), i.get('location', '')),
                                  i.get('amount', 1), i.get('consumed', True))
                      for i in effect.inputs]
            outputs = []
            for out in effect.outputs:
                if out.get('is_unpack_genome', False):
                    location = out.get('location', CellLocation.CYTOSOL.value)
                    for genome_id in self._gs.virus_config.get_genome_entity_ids():
                        outputs.append(PathwayFlow(self._entity(genome_id, location)))
                elif self._gs.can_entity_exist(out.get('entity_id', 0)):
                    outputs.append(PathwayFlow(self._entity(out.get('entity_id', 0), out.get('location', '')),
                                               out.get('amount', 1)))
            return inputs, outputs, effect.chance

        if kind == EffectType.CHANGE_LOCATION.value:
            if not effect.source_location or not effect.target_location:
                return None
            if effect.affected_entity_id is None:
                source = self._any_entity(effect.source_location)
                target = self._any_entity(effect.target_location)
            else:
                source = self._entity(effect.affected_entity_id, effect.source_location)
                target = self._entity(effect.affected_entity_id, effect.target_location)
            return [PathwayFlow(source)], [PathwayFlow(target)], effect.location_change_chance

        if kind == EffectType.TRANSLATION.value:
            inputs = [PathwayFlow(self._entity(t.get('entity_id', 0), t.get('location', '')), consumed=False)
                      for t in effect.templates]
            outputs = []
            for span in self._orf_spans:
                if effect.orf_targeting == "ORF-1 only" and span.name != "ORF-1":
                    continue
                if effect.orf_targeting == "Not ORF-1" and span.name == "ORF-1":
                    continue
                outputs.extend(self._orf_products(span))
            return inputs, _unique(outputs), effect.translation_chance

        return None  # Modify effects and Self-cleavage don't move entities themselves

    def _orf_products(self, span: OrfSpan) -> list:
        """What translating an ORF yields: a protein, or a polyprotein to cleave.

        With terminator readthrough an ORF can also yield its longer variant.
        """
        variants = [span.gene_ids]
        if span.readthrough_gene_ids:
            variants.append(span.gene_ids + span.readthrough_gene_ids)

        products = []
        for index, variant in enumerate(variants):
            genes = [g for g in map(self._gs.get_gene, variant) if g]
            proteins = [g.gene_type_entity_id for g in genes if g.gene_type_entity_id is not None]
            if len(proteins) == 1:
                products.append(PathwayFlow(self._entity(proteins[0], CellLocation.CYTOSOL.value)))
            elif proteins:
                products.append(PathwayFlow(self._polyprotein(span.name, genes, proteins,
                                                              readthrough=index == 1)))
        return products

    def _polyprotein(self, orf_name: str, genes: list, proteins: list, readthrough: bool) -> str:
        key = f"poly:{orf_name}:{'+'.join(map(str, proteins))}"
        if key not in self._states:
            label = f"{orf_name} polyprotein" + (" (readthrough)" if readthrough else "")
            self._states[key] = PathwayState(key, f"{label} ({len(proteins)} proteins)",
                                             CellLocation.CYTOSOL.value,
                                             EntityCategory.PROTEIN.value, None)
        if key not in self._cleavages:
            self._cleavages.add(key)
            chance = 0.0
            for gene in genes:
                for effect in map(self._db.get_effect, gene.effect_ids):
                    if effect and effect.effect_type == EffectType.SELF_CLEAVAGE.value:
                        chance += effect.self_cleavage_chance
            chance = min(100.0, chance)
            outputs = tuple(PathwayFlow(self._entity(p, CellLocation.CYTOSOL.value), n)
                            for p, n in Counter(proteins).items())
            self._reactions.append(PathwayReaction(
                name=f"Cleavage of the {orf_name} polyprotein", kind=EffectType.SELF_CLEAVAGE.value,
                inputs=(PathwayFlow(key),), outputs=outputs, base_chance=chance, chance=chance,
                modified_by=(), is_global=False, effect_id=None,
            ))
        return key

    def _entity(self, entity_id: int, location: str, is_start: bool = False) -> str:
        key = f"{entity_id}@{location}"
        if key not in self._states:
            entity = self._db.get_entity(entity_id)
            self._states[key] = PathwayState(key, self._name(entity_id), location,
                                             entity.category if entity else "", entity_id, is_start)
        return key

    def _any_entity(self, location: str) -> str:
        key = f"any@{location}"
        if key not in self._states:
            self._states[key] = PathwayState(key, "Any entity", location, "", None)
        return key

    def _name(self, entity_id: int) -> str:
        entity = self._db.get_entity(entity_id)
        return entity.name if entity else f"Entity {entity_id}"


def _unique(flows: list) -> list:
    """Drop repeated flows, keeping order."""
    seen = set()
    return [f for f in flows if not (f in seen or seen.add(f))]


# --------------------------------------------------------------------------
# Round
# --------------------------------------------------------------------------

class Round:
    """The play round in progress. Get it from ``GameAPI.start_round()``.

    The UI paces the round: call step() once per turn, as fast as it likes.
    Pausing is simply not calling it.
    """

    interferon_max = INTERFERON_MAX
    population_groups = POPULATION_GROUPS

    def __init__(self, engine: SimulationEngine, game_state: GameState):
        self._engine = engine
        self._gs = game_state
        self.number = game_state.current_round
        self._milestones_at_start = frozenset(game_state.achieved_milestones)

    @property
    def win_threshold(self) -> int:
        """Virions needed for victory."""
        return self._engine.win_threshold

    @property
    def turn(self) -> int:
        return self._engine.sim_state.turn

    @property
    def is_over(self) -> bool:
        return self._engine.sim_state.is_ended

    def step(self) -> TurnResult:
        """Run one turn. Once the round is over this does nothing."""
        sim = self._engine.sim_state
        if sim.is_ended:
            return TurnResult(self.snapshot(), (), False, False)

        achieved_before = set(self._gs.achieved_milestones)
        active_before = set(sim.active_milestone_ids)
        self._engine.run_turn()

        achieved = tuple(sorted(self._gs.achieved_milestones - achieved_before))
        changed = bool(achieved) or sim.active_milestone_ids != active_before
        return TurnResult(self.snapshot(), achieved, changed, sim.is_ended)

    def end_early(self) -> None:
        """Stop the round now. GameAPI.finish_round() does this if needed."""
        self._engine.end_early()

    def snapshot(self) -> RoundSnapshot:
        sim = self._engine.sim_state
        total, virions = self._engine.count_population()
        return RoundSnapshot(
            turn=sim.turn,
            total_entities=total,
            virion_count=virions,
            interferon_level=sim.interferon_level,
            antibodies_active=sim.antibody_active,
            antibodies_stored=sim.antibody_stored,
            population=self._population(),
            is_over=sim.is_ended,
            is_victory=sim.is_victory,
            is_extinct=sim.extinction,
        )

    def _population(self) -> tuple:
        sim = self._engine.sim_state
        database = self._gs.database

        entity_counts = defaultdict(int)
        for entities in (sim.entities, sim.new_entities):
            for key, count in entities.items():
                entity_counts[key] += count

        entries = []
        for (entity_id, location), count in entity_counts.items():
            entity = database.get_entity(entity_id)
            entries.append(PopulationEntry(
                location=location,
                name=entity.name if entity else f"Entity {entity_id}",
                category=entity.category if entity else "",
                count=count,
            ))

        poly_counts = defaultdict(int)
        for polyproteins in (sim.polyproteins, sim.new_polyproteins):
            for poly, count in polyproteins.items():
                poly_counts[poly] += count

        for poly, count in poly_counts.items():
            if count <= 0:
                continue
            names = []
            for entity_id in poly.protein_entity_ids:
                entity = database.get_entity(entity_id)
                names.append(entity.get_display_name(use_abbreviation=True)
                             if entity else f"ID:{entity_id}")
            entries.append(PopulationEntry(
                location=CellLocation.CYTOSOL.value,
                name=f"Poly ({', '.join(names)})",
                category=EntityCategory.PROTEIN.value,
                count=count,
                is_polyprotein=True,
            ))
        return tuple(entries)

    def history(self, last: Optional[int] = None) -> list:
        """Population per turn as ``(turn, {group: count})``, keyed by
        population_groups. ``last`` limits it to the most recent turns.
        The count dicts are shared: read them, don't modify them."""
        history = self._engine.sim_state.history
        return history[:] if last is None else history[-last:]

    def log(self) -> list[str]:
        """The turn-by-turn log lines."""
        return list(self._engine.sim_state.log)

    def tracked_milestones(self) -> list[MilestoneStatus]:
        """Milestones to show: achieved ones, and active ones (prerequisite met)."""
        achieved = self._gs.achieved_milestones
        active = self._engine.sim_state.active_milestone_ids
        shown = [m for m in self._gs.database.milestones.values()
                 if m.id in achieved or m.id in active]
        shown.sort(key=lambda m: m.id)
        return [MilestoneStatus(m, m.id in achieved) for m in shown]

    def summary(self) -> RoundSummary:
        sim = self._engine.sim_state
        new_ids = self._gs.achieved_milestones - self._milestones_at_start
        milestones = sorted(filter(None, map(self._gs.database.get_milestone, new_ids)),
                            key=lambda m: m.id)
        return RoundSummary(
            is_victory=sim.is_victory,
            is_extinct=sim.extinction,
            ended_early=sim.is_ended and not (sim.is_victory or sim.extinction),
            turns=sim.turn,
            milestones_achieved=tuple(milestones),
            evolution_points=self._gs.evolution_points,
        )


# --------------------------------------------------------------------------
# GameAPI
# --------------------------------------------------------------------------

class GameAPI:
    """The entry point for a UI. Create one per application run.

    Phases (``api.phase``) and the calls that move between them::

        NO_GAME --new_game--> BUILDING --start_round--> PLAYING
        PLAYING --finish_round--> GENE_OFFER | BUILDING | GAME_OVER
        GENE_OFFER --accept_offered_gene / decline_gene_offer--> BUILDING
        any phase --end_game--> NO_GAME
    """

    def __init__(self, rng=None):
        self._settings = app_settings.load_settings()
        self._session = GameSession(
            starting_hand_size=self._settings["game"]["starting_hand_size"], rng=rng)
        self._builder: Optional[Builder] = None
        self._round: Optional[Round] = None
        self._version = get_version()

    # ---- application

    @property
    def version(self) -> str:
        return self._version

    @property
    def settings(self) -> dict:
        """A copy of the current settings:
        ``{"display": {"window_mode"}, "game": {"starting_hand_size", "default_database"}}``.
        """
        return copy.deepcopy(self._settings)

    def save_settings(self, settings: dict) -> tuple[bool, str]:
        """Validate and save settings. Nothing is saved if they are invalid."""
        valid, message = app_settings.validate_settings(settings)
        if not valid:
            return False, message
        app_settings.save_settings(settings)
        self._settings = app_settings.load_settings()
        return True, "Settings saved."

    def default_database_path(self) -> Optional[str]:
        """The database named in the settings, or None if that file doesn't exist."""
        path = os.path.join(APP_ROOT, self._settings["game"]["default_database"])
        return path if os.path.isfile(path) else None

    def create_content_database(self) -> GameDatabase:
        """An empty content database for an editor UI (then call new_database() or load())."""
        return GameDatabase()

    # ---- game lifecycle

    @property
    def phase(self) -> GamePhase:
        return self._session.phase

    @property
    def is_game_active(self) -> bool:
        return self._session.is_active

    def new_game(self, database_path: str) -> StartResult:
        """Start a new game on a content database file. Any game in progress is replaced."""
        self._session.starting_hand_size = self._settings["game"]["starting_hand_size"]
        result = self._session.start(database_path)
        if result is StartResult.OK:
            self._builder = Builder(self._session)
            self._round = None
        return result

    def end_game(self) -> None:
        """Discard the current game (any phase)."""
        self._session.end()
        self._builder = None
        self._round = None

    def _require_game(self) -> GameState:
        if self._session.game_state is None:
            raise GameFlowError("no game in progress")
        return self._session.game_state

    def status(self) -> GameStatus:
        gs = self._require_game()
        return GameStatus(
            phase=self._session.phase,
            evolution_points=gs.evolution_points,
            current_round=gs.current_round,
            max_rounds=gs.max_rounds,
            genome_length=gs.get_total_genome_length(),
        )

    # ---- content lookups (shared model objects: read only)

    def get_gene(self, gene_id: int) -> Optional[Gene]:
        return self._require_game().get_gene(gene_id)

    def get_effect(self, effect_id: int) -> Optional[Effect]:
        return self._require_game().get_effect(effect_id)

    def get_entity(self, entity_id: int) -> Optional[ViralEntity]:
        return self._require_game().database.get_entity(entity_id)

    def get_milestone(self, milestone_id: int) -> Optional[Milestone]:
        return self._require_game().database.get_milestone(milestone_id)

    def gene_type_name(self, gene_id: int) -> str:
        """Name of the protein type a gene enables, or "None"."""
        gs = self._require_game()
        gene = gs.get_gene(gene_id)
        return gs.database.get_gene_type_name(gene) if gene else "None"

    # ---- building

    @property
    def builder(self) -> Builder:
        self._require_game()
        return self._builder

    # ---- rounds

    def round_readiness(self) -> RoundReadiness:
        return self._require_game().round_readiness()

    def start_round(self) -> Round:
        """Start a play round. Needs BUILDING and round_readiness() READY."""
        engine = self._session.start_round()
        self._round = Round(engine, self._session.game_state)
        return self._round

    @property
    def current_round(self) -> Optional[Round]:
        """The round in progress, or None outside the PLAYING phase."""
        return self._round

    def finish_round(self) -> RoundOutcome:
        """Close the round in progress (ending it early if it is still running).

        On CONTINUE the phase becomes GENE_OFFER, or BUILDING if there are no
        genes left to offer. VICTORY and OUT_OF_ROUNDS lead to GAME_OVER.
        """
        outcome = self._session.finish_round()
        self._round = None
        return outcome

    # ---- gene offers

    @property
    def gene_offer(self) -> Optional[GeneOffer]:
        """The pending offer in the GENE_OFFER phase, else None."""
        if self._session.phase is not GamePhase.GENE_OFFER:
            return None
        gs = self._session.game_state
        genes = tuple(filter(None, map(gs.get_gene, self._session.offer)))
        return GeneOffer(genes=genes, completed_round=gs.current_round - 1,
                         max_rounds=gs.max_rounds)

    def accept_offered_gene(self, gene_id: int) -> None:
        """Add one offered gene to the hand. Raises ValueError if it wasn't offered."""
        self._session.accept_gene(gene_id)

    def decline_gene_offer(self) -> None:
        self._session.decline_offer()
