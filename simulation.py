"""
Simulation engine for Viral Sandbox.

The complete turn-by-turn rules of the virus simulation, with no UI dependency.
This module must never import tkinter: it is what makes the game runnable
headlessly from tests and balance scripts.

UIs do not drive the engine directly: game_api.Round wraps it and hands the UI
snapshots. Headless callers (tests, simulate.py) use it as::

    engine = SimulationEngine(game_state, rng=random.Random(42))
    engine.run_until_end()
    print(engine.sim_state.turn, engine.sim_state.is_victory)
"""
import random
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Callable, Optional

from game_state import GameState
from models import Effect, EffectType, CellLocation, EntityCategory

# Interferon level is capped here; interferon degradation modifiers scale against it.
INTERFERON_MAX = 100000

# Groups the population is counted in for history, graphs and count milestones.
# "Produce entity count" milestones name one of these as their target category.
POPULATION_GROUPS = ("Virion", "RNA", "DNA", "Protein", "Antibodies")

_CATEGORY_GROUPS = {
    EntityCategory.VIRION.value: "Virion",
    EntityCategory.VIRAL_COMPLEX.value: "Virion",
    EntityCategory.RNA.value: "RNA",
    EntityCategory.DNA.value: "DNA",
    EntityCategory.PROTEIN.value: "Protein",
}


def population_group(category: str) -> Optional[str]:
    """The population group an entity category is counted under, if any."""
    return _CATEGORY_GROUPS.get(category)


@dataclass
class EntityInstance:
    """Represents entities at a specific location."""
    entity_id: int
    location: str
    count: int = 0
    is_new: bool = False  # True if created this turn (no transitions apply)


@dataclass(frozen=True)
class PolyproteinInstance:
    """Represents a polyprotein wrapper containing multiple protein types."""
    orf_name: str  # e.g., "ORF-1"
    protein_entity_ids: tuple  # Tuple of protein entity IDs contained (immutable for hashing)
    self_cleavage_chance: float  # Percentage 0-100 per turn


@dataclass
class SimulationState:
    """State of the current simulation."""
    turn: int = 0
    entities: dict = field(default_factory=dict)  # (entity_id, location) -> count
    new_entities: dict = field(default_factory=dict)  # Same, but created this turn

    # Polyproteins: PolyproteinInstance -> count (always in cytosol)
    polyproteins: dict = field(default_factory=dict)
    new_polyproteins: dict = field(default_factory=dict)

    interferon_level: float = 0.0
    antibody_stored: int = 0
    antibody_active: int = 0
    antibody_manifest_queue: list = field(default_factory=list)  # (manifest_turn, amount)

    # History for graphing
    history: list = field(default_factory=list)  # List of (turn, {category: count})

    # Tracking for milestones
    locations_entered: set = field(default_factory=set)
    categories_produced: set = field(default_factory=set)
    category_counts: dict = field(default_factory=dict)  # category -> max count achieved
    active_milestone_ids: set = field(default_factory=set)  # Milestones currently being tracked

    # Simulation log
    log: list = field(default_factory=list)

    # End state
    is_ended: bool = False
    is_victory: bool = False
    extinction: bool = False

class SimulationEngine:
    """Runs the virus simulation. Pure logic - no widgets, no timers.

    Observers may assign the ``on_*`` attributes to be notified as the run
    progresses; each is optional and defaults to doing nothing.
    """

    def __init__(self, game_state: GameState, rng=None):
        self.game_state = game_state
        # Defaults to the ``random`` module itself so behaviour matches the
        # original in-window simulation exactly; pass a ``random.Random(seed)``
        # for reproducible runs in tests.
        self.rng = rng if rng is not None else random

        # Observer hooks (set by the UI; ignored when running headless).
        self.on_turn_complete: Optional[Callable] = None
        self.on_game_end: Optional[Callable] = None
        self.on_milestone_achieved: Optional[Callable] = None
        self.on_active_milestones_changed: Optional[Callable] = None

        # Build virus blueprint
        self.effects = self._build_effects_list()
        self.global_effects = self.game_state.get_global_effects(filter_invalid=True)

        # Initialize simulation state
        self.sim_state = SimulationState()
        self._initialize_simulation()

    def _emit(self, callback, *args):
        """Fire an observer callback if one is registered."""
        if callback is not None:
            callback(*args)

    @property
    def win_threshold(self) -> int:
        """Virions needed for victory."""
        return self.game_state.win_threshold

    def run_until_end(self, max_turns: int = 10000) -> SimulationState:
        """Run turns headlessly until the simulation ends or ``max_turns``.

        Returns the final simulation state.
        """
        while not self.sim_state.is_ended and self.sim_state.turn < max_turns:
            self.run_turn()
        return self.sim_state

    def end_early(self):
        """End the run before victory or extinction (the player stopped it)."""
        if self.sim_state.is_ended:
            return
        self.sim_state.is_ended = True
        self.sim_state.log.append("\n=== Round ended early ===")

    def count_population(self) -> tuple[int, int]:
        """Return ``(total, virions)``: every entity and polyprotein, and the
        virion-group entities among them."""
        total = 0
        virions = 0
        for entities in (self.sim_state.entities, self.sim_state.new_entities):
            for (entity_id, location), count in entities.items():
                total += count
                entity = self.game_state.database.get_entity(entity_id)
                if entity and population_group(entity.category) == "Virion":
                    virions += count
        total += sum(self.sim_state.polyproteins.values())
        total += sum(self.sim_state.new_polyproteins.values())
        return total, virions

    def _build_effects_list(self) -> list[Effect]:
        """Build the list of effects from installed genes."""
        return self.game_state.get_all_effects(filter_invalid=True)

    def _initialize_simulation(self):
        """Initialize the simulation with starting entities."""
        self.sim_state = SimulationState()

        # Determine starting virion based on virus config
        config = self.game_state.virus_config
        if config.virion_type == "Enveloped":
            starter_entity_id = self.game_state.database.ENVELOPED_VIRION_ID
        else:
            starter_entity_id = self.game_state.database.UNENVELOPED_VIRION_ID

        # Start with 10 virions extracellularly
        key = (starter_entity_id, CellLocation.EXTRACELLULAR.value)
        self.sim_state.entities[key] = 10

        # Log initial state
        entity = self.game_state.database.get_entity(starter_entity_id)
        entity_name = entity.name if entity else f"Entity {starter_entity_id}"
        self.sim_state.log.append(f"=== Simulation Start ===")
        self.sim_state.log.append(f"Starting with 10 {entity_name} (Extracellular)")

        # Track initial location
        self.sim_state.locations_entered.add(CellLocation.EXTRACELLULAR.value)

        # Calculate initial active milestones (those with no prerequisites or met prerequisites)
        self._update_active_milestones()

        # Record initial history
        self._record_history()

    def run_turn(self):
        """Run a single simulation turn. Does nothing once the run has ended."""
        if self.sim_state.is_ended:
            return

        self.sim_state.turn += 1
        self.sim_state.log.append(f"\n--- Turn {self.sim_state.turn} ---")

        # Clear new entities/polyproteins from last turn (they're now regular)
        self._merge_new_entities()

        # Process effects in order
        self._process_transitions()
        self._process_translations()
        self._process_location_changes()
        self._process_polyprotein_cleavage()
        self._process_degradation()
        self._process_polyprotein_degradation()
        self._process_interferon_decay()
        self._process_antibodies()

        # Merge new entities/polyproteins created this turn
        self._merge_new_entities()

        # Record history
        self._record_history()

        # Check win/loss conditions
        self._check_conditions()

        # Notify observers (the UI redraws here)
        self._emit(self.on_turn_complete)

        # Check milestones
        self._check_milestones()

    def _merge_new_entities(self):
        """Merge new entities and polyproteins into the main dicts."""
        for key, count in self.sim_state.new_entities.items():
            if key in self.sim_state.entities:
                self.sim_state.entities[key] += count
            else:
                self.sim_state.entities[key] = count
        self.sim_state.new_entities.clear()

        # Merge new polyproteins
        for poly, count in self.sim_state.new_polyproteins.items():
            if poly in self.sim_state.polyproteins:
                self.sim_state.polyproteins[poly] += count
            else:
                self.sim_state.polyproteins[poly] = count
        self.sim_state.new_polyproteins.clear()

    def _process_transitions(self):
        """Process all transition effects."""
        all_effects = self.effects + self.global_effects
        transition_effects = [e for e in all_effects
                             if e.effect_type == EffectType.TRANSITION.value]

        # Sort by effect ID for consistent ordering
        transition_effects.sort(key=lambda e: e.id)

        # Get modifiers
        modifiers = self._get_effect_modifiers()

        for effect in transition_effects:
            self._apply_transition(effect, modifiers)

    def _get_effect_modifiers(self) -> dict:
        """Get all effect modifiers keyed by effect ID and category.

        Modifiers are stored as percentage multipliers (100 = no change, 150 = 1.5x).
        Multiple modifiers targeting the same effect/category are multiplied together.
        Applies to Transition, Translation, and Change location effects.
        """
        modifiers = defaultdict(lambda: {'chance': 100, 'interferon': 100, 'antibody': 100})

        all_effects = self.effects + self.global_effects
        modify_effects = [e for e in all_effects
                         if e.effect_type == EffectType.MODIFY_EFFECT.value]

        for effect in modify_effects:
            if effect.target_effect_id is not None:
                key = ('id', effect.target_effect_id)
            elif effect.target_category:
                key = ('category', effect.target_category)
            else:
                continue

            # Multiply modifiers together (150 * 150 / 100 = 225, meaning 2.25x total)
            modifiers[key]['chance'] = modifiers[key]['chance'] * effect.chance_modifier / 100
            modifiers[key]['interferon'] = modifiers[key]['interferon'] * effect.interferon_modifier / 100
            modifiers[key]['antibody'] = modifiers[key]['antibody'] * effect.antibody_modifier / 100

        return modifiers

    def _apply_transition(self, effect: Effect, modifiers: dict):
        """Apply a single transition effect."""
        # Check if all inputs are available
        inputs_available = True
        min_possible = float('inf')

        for inp in effect.inputs:
            entity_id = inp.get('entity_id', 0)
            location = inp.get('location', '')
            amount = inp.get('amount', 1)

            key = (entity_id, location)
            available = self.sim_state.entities.get(key, 0)

            if available < amount:
                inputs_available = False
                break

            # How many times can this transition fire?
            possible = available // amount
            min_possible = min(min_possible, possible)

        if not inputs_available or min_possible == 0:
            return

        # Calculate modified chance using multiplicative modifiers
        base_chance = effect.chance
        modifier = modifiers.get(('id', effect.id), {'chance': 100, 'interferon': 100, 'antibody': 100})
        cat_modifier = modifiers.get(('category', effect.category), {'chance': 100, 'interferon': 100, 'antibody': 100})

        # Apply modifiers multiplicatively (modifier values are percentages: 100 = no change, 150 = 1.5x)
        total_chance = base_chance * (modifier['chance'] / 100) * (cat_modifier['chance'] / 100)
        total_chance = max(0, min(100, total_chance))

        if total_chance <= 0:
            return

        # Apply transition for each possible occurrence
        successes = 0
        for _ in range(int(min_possible)):
            if self.rng.random() * 100 < total_chance:
                successes += 1

        if successes == 0:
            return

        # Consume inputs
        for inp in effect.inputs:
            if inp.get('consumed', True):
                entity_id = inp.get('entity_id', 0)
                location = inp.get('location', '')
                amount = inp.get('amount', 1)
                key = (entity_id, location)
                self.sim_state.entities[key] -= amount * successes
                if self.sim_state.entities[key] <= 0:
                    del self.sim_state.entities[key]

        # Produce outputs
        for out in effect.outputs:
            if out.get('is_unpack_genome', False):
                # Unpack genome - spawn genome entities
                self._spawn_genome_entities(out.get('location', 'Cytosol'), successes)
            else:
                entity_id = out.get('entity_id', 0)
                location = out.get('location', '')
                amount = out.get('amount', 1)

                # Check if entity can exist
                if not self.game_state.can_entity_exist(entity_id):
                    continue

                key = (entity_id, location)
                if key in self.sim_state.new_entities:
                    self.sim_state.new_entities[key] += amount * successes
                else:
                    self.sim_state.new_entities[key] = amount * successes

                # Track location and category
                self.sim_state.locations_entered.add(location)
                entity = self.game_state.database.get_entity(entity_id)
                if entity:
                    self.sim_state.categories_produced.add(entity.category)

        # Apply interferon production with multiplicative modifiers
        ifn_prod = effect.interferon_production
        ifn_prod = ifn_prod * (modifier.get('interferon', 100) / 100) * (cat_modifier.get('interferon', 100) / 100)
        if ifn_prod > 0:
            self.sim_state.interferon_level += ifn_prod * successes
            self.sim_state.interferon_level = min(INTERFERON_MAX, self.sim_state.interferon_level)

        # Apply antibody response with multiplicative modifiers
        ab_resp = effect.antibody_response
        ab_resp = ab_resp * (modifier.get('antibody', 100) / 100) * (cat_modifier.get('antibody', 100) / 100)
        ab_amount = int(ab_resp * successes)
        if ab_amount > 0:
            self.sim_state.antibody_stored += ab_amount
            # Queue antibody manifestation
            delay = self.game_state.database.get_antibody_manifest_delay()
            manifest_turn = self.sim_state.turn + delay
            self.sim_state.antibody_manifest_queue.append((manifest_turn, ab_amount))

        # Log
        self.sim_state.log.append(
            f"  {effect.name}: {successes}x (chance: {total_chance:.1f}%)")

    def _spawn_genome_entities(self, location: str, count: int):
        """Spawn genome entities based on virus configuration."""
        genome_ids = self.game_state.virus_config.get_genome_entity_ids()

        for entity_id in genome_ids:
            key = (entity_id, location)
            if key in self.sim_state.new_entities:
                self.sim_state.new_entities[key] += count
            else:
                self.sim_state.new_entities[key] = count

            self.sim_state.locations_entered.add(location)
            entity = self.game_state.database.get_entity(entity_id)
            if entity:
                self.sim_state.categories_produced.add(entity.category)

    def _process_translations(self):
        """Process all translation effects."""
        all_effects = self.effects + self.global_effects
        translation_effects = [e for e in all_effects
                              if e.effect_type == EffectType.TRANSLATION.value]

        translation_effects.sort(key=lambda e: e.id)

        modifiers = self._get_effect_modifiers()

        for effect in translation_effects:
            self._apply_translation(effect, modifiers)

    def _apply_translation(self, effect: Effect, modifiers: dict):
        """Apply a single translation effect."""
        # Check if templates are available
        templates_available = True
        min_possible = float('inf')

        for tmpl in effect.templates:
            entity_id = tmpl.get('entity_id', 0)
            location = tmpl.get('location', '')

            key = (entity_id, location)
            available = self.sim_state.entities.get(key, 0)

            if available <= 0:
                templates_available = False
                break

            min_possible = min(min_possible, available)

        if not templates_available or min_possible == 0:
            return

        # Get ORF structure
        orf_structure = self.game_state.get_orf_structure()
        if not orf_structure:
            return

        # Filter ORFs based on targeting
        targeting = effect.orf_targeting
        valid_orfs = []

        for orf_info in orf_structure:
            orf_name = orf_info['orf']
            if targeting == "ORF-1 only" and orf_name != "ORF-1":
                continue
            if targeting == "Not ORF-1" and orf_name == "ORF-1":
                continue
            valid_orfs.append(orf_info)

        if not valid_orfs:
            return

        # Calculate modified chance using modifiers
        base_chance = effect.translation_chance
        modifier = modifiers.get(('id', effect.id), {'chance': 100, 'interferon': 100, 'antibody': 100})
        cat_modifier = modifiers.get(('category', effect.category), {'chance': 100, 'interferon': 100, 'antibody': 100})

        total_chance = base_chance * (modifier['chance'] / 100) * (cat_modifier['chance'] / 100)
        total_chance = max(0, min(100, total_chance))

        if total_chance <= 0:
            return

        # For each template, attempt translation
        successes = 0
        for _ in range(int(min_possible)):
            if self.rng.random() * 100 < total_chance:
                successes += 1

        if successes == 0:
            return

        # For each success, pick an ORF and produce protein
        for _ in range(successes):
            orf_info = self.rng.choice(valid_orfs)
            self._translate_orf(orf_info)

        self.sim_state.log.append(
            f"  {effect.name}: {successes}x translation events (chance: {total_chance:.1f}%)")

    def _translate_orf(self, orf_info: dict):
        """Translate an ORF, producing appropriate protein or polyprotein."""
        orf_name = orf_info['orf']

        # Dynamically resolve genes with terminator readthrough rolls
        if self.game_state.terminator_chance < 100:
            genes = self.game_state.resolve_orf_translation(orf_info['start_idx'])
        else:
            genes = orf_info['genes']

        # Get protein types from genes in this ORF
        protein_entity_ids = []
        for gene_id in genes:
            gene = self.game_state.get_gene(gene_id)
            if gene and gene.gene_type_entity_id is not None:
                protein_entity_ids.append(gene.gene_type_entity_id)

        if not protein_entity_ids:
            # No typed genes - produce nothing
            return

        location = CellLocation.CYTOSOL.value

        if len(protein_entity_ids) == 1:
            # Single type - produce that protein directly
            entity_id = protein_entity_ids[0]
            key = (entity_id, location)
            if key in self.sim_state.new_entities:
                self.sim_state.new_entities[key] += 1
            else:
                self.sim_state.new_entities[key] = 1
        else:
            # Multiple types - create a polyprotein wrapper
            # Calculate self-cleavage chance from Self-cleavage effects in this ORF's genes
            cleavage_chance = 0.0
            for gene_id in genes:
                gene = self.game_state.get_gene(gene_id)
                if gene:
                    for effect_id in gene.effect_ids:
                        effect = self.game_state.database.get_effect(effect_id)
                        if effect and effect.effect_type == EffectType.SELF_CLEAVAGE.value:
                            cleavage_chance += effect.self_cleavage_chance

            # Create polyprotein instance (use tuple for hashability)
            poly = PolyproteinInstance(
                orf_name=orf_name,
                protein_entity_ids=tuple(protein_entity_ids),
                self_cleavage_chance=cleavage_chance
            )

            if poly in self.sim_state.new_polyproteins:
                self.sim_state.new_polyproteins[poly] += 1
            else:
                self.sim_state.new_polyproteins[poly] = 1

        self.sim_state.locations_entered.add(location)
        self.sim_state.categories_produced.add(EntityCategory.PROTEIN.value)

    def _process_location_changes(self):
        """Process all change location effects."""
        all_effects = self.effects + self.global_effects
        location_effects = [e for e in all_effects
                           if e.effect_type == EffectType.CHANGE_LOCATION.value]

        location_effects.sort(key=lambda e: e.id)

        modifiers = self._get_effect_modifiers()

        for effect in location_effects:
            self._apply_location_change(effect, modifiers)

    def _apply_location_change(self, effect: Effect, modifiers: dict):
        """Apply a single location change effect."""
        source = effect.source_location
        target = effect.target_location

        # Calculate modified chance using modifiers
        base_chance = effect.location_change_chance
        modifier = modifiers.get(('id', effect.id), {'chance': 100, 'interferon': 100, 'antibody': 100})
        cat_modifier = modifiers.get(('category', effect.category), {'chance': 100, 'interferon': 100, 'antibody': 100})

        chance = base_chance * (modifier['chance'] / 100) * (cat_modifier['chance'] / 100)
        chance = max(0, min(100, chance))

        if not source or not target or chance <= 0:
            return

        # Find entities to move
        entities_to_move = []

        for (entity_id, location), count in list(self.sim_state.entities.items()):
            if location != source:
                continue

            if effect.affected_entity_id is not None:
                if entity_id != effect.affected_entity_id:
                    continue

            # Check if entity can exist
            if not self.game_state.can_entity_exist(entity_id):
                continue

            entities_to_move.append((entity_id, count))

        for entity_id, count in entities_to_move:
            moves = 0
            for _ in range(count):
                if self.rng.random() * 100 < chance:
                    moves += 1

            if moves > 0:
                source_key = (entity_id, source)
                target_key = (entity_id, target)

                self.sim_state.entities[source_key] -= moves
                if self.sim_state.entities[source_key] <= 0:
                    del self.sim_state.entities[source_key]

                if target_key in self.sim_state.entities:
                    self.sim_state.entities[target_key] += moves
                else:
                    self.sim_state.entities[target_key] = moves

                self.sim_state.locations_entered.add(target)

                entity = self.game_state.database.get_entity(entity_id)
                entity_name = entity.name if entity else f"Entity {entity_id}"
                self.sim_state.log.append(
                    f"  {moves}x {entity_name}: {source} -> {target}")

    def _process_degradation(self):
        """Process entity degradation."""
        total_degraded = 0
        cytoplasm_proteins_degraded = 0
        interferon_level = self.sim_state.interferon_level

        for (entity_id, location), count in list(self.sim_state.entities.items()):
            entity = self.game_state.database.get_entity(entity_id)
            if not entity:
                continue

            category = entity.category
            base_chance = self.game_state.database.get_degradation_chance(category, location)

            # Apply entity-specific degradation modifier before other modifiers
            base_chance = base_chance * (entity.degradation_modifier / 100.0)
            base_chance = min(100.0, base_chance)

            # Apply interferon effect (only affects intracellular locations)
            if location != CellLocation.EXTRACELLULAR.value and interferon_level > 0:
                # Get per-category interferon modifier (% increase at max interferon)
                ifn_modifier_percent = self.game_state.database.get_interferon_modifier(category)
                # Calculate actual modifier: scales linearly with interferon level
                # At INTERFERON_MAX and modifier 100%, this equals 1.0 (doubles the chance)
                actual_modifier = (ifn_modifier_percent / 100.0) * (interferon_level / INTERFERON_MAX)
                adjusted_chance = base_chance * (1 + actual_modifier)
                # Cap at 100%
                adjusted_chance = min(100.0, adjusted_chance)
            else:
                adjusted_chance = base_chance

            # Calculate degradation
            degraded = 0
            for _ in range(count):
                if self.rng.random() * 100 < adjusted_chance:
                    degraded += 1

            if degraded > 0:
                self.sim_state.entities[(entity_id, location)] -= degraded
                if self.sim_state.entities[(entity_id, location)] <= 0:
                    del self.sim_state.entities[(entity_id, location)]
                total_degraded += degraded

                # Track proteins degraded in cytoplasm for antibody generation
                if category == EntityCategory.PROTEIN.value and location == CellLocation.CYTOSOL.value:
                    cytoplasm_proteins_degraded += degraded

        # Also degrade new entities
        for (entity_id, location), count in list(self.sim_state.new_entities.items()):
            entity = self.game_state.database.get_entity(entity_id)
            if not entity:
                continue

            category = entity.category
            base_chance = self.game_state.database.get_degradation_chance(category, location)

            # Apply entity-specific degradation modifier before other modifiers
            base_chance = base_chance * (entity.degradation_modifier / 100.0)
            base_chance = min(100.0, base_chance)

            # Apply interferon effect (only affects intracellular locations)
            if location != CellLocation.EXTRACELLULAR.value and interferon_level > 0:
                ifn_modifier_percent = self.game_state.database.get_interferon_modifier(category)
                actual_modifier = (ifn_modifier_percent / 100.0) * (interferon_level / INTERFERON_MAX)
                adjusted_chance = base_chance * (1 + actual_modifier)
                adjusted_chance = min(100.0, adjusted_chance)
            else:
                adjusted_chance = base_chance

            degraded = 0
            for _ in range(count):
                if self.rng.random() * 100 < adjusted_chance:
                    degraded += 1

            if degraded > 0:
                self.sim_state.new_entities[(entity_id, location)] -= degraded
                if self.sim_state.new_entities[(entity_id, location)] <= 0:
                    del self.sim_state.new_entities[(entity_id, location)]
                total_degraded += degraded

                # Track proteins degraded in cytoplasm for antibody generation
                if category == EntityCategory.PROTEIN.value and location == CellLocation.CYTOSOL.value:
                    cytoplasm_proteins_degraded += degraded

        if total_degraded > 0:
            self.sim_state.log.append(f"  Degradation: {total_degraded} entities")

        # Generate antibodies from cytoplasm protein degradation
        # Fires for every 10 proteins degraded; fewer than 10 generates nothing
        if cytoplasm_proteins_degraded >= 10:
            ab_per_10 = self.game_state.database.get_antibody_per_10_degraded()
            fires = cytoplasm_proteins_degraded // 10
            ab_amount = fires * ab_per_10
            if ab_amount > 0:
                self.sim_state.antibody_stored += ab_amount
                delay = self.game_state.database.get_antibody_manifest_delay()
                manifest_turn = self.sim_state.turn + delay
                self.sim_state.antibody_manifest_queue.append((manifest_turn, ab_amount))
                self.sim_state.log.append(
                    f"  Antibody response: {cytoplasm_proteins_degraded} proteins degraded in cytoplasm -> {ab_amount} antibodies stored (manifest turn {manifest_turn})")

    def _process_interferon_decay(self):
        """Process interferon decay."""
        if self.sim_state.interferon_level > 0:
            decay_rate = self.game_state.database.get_interferon_decay()
            self.sim_state.interferon_level -= decay_rate
            self.sim_state.interferon_level = max(0, self.sim_state.interferon_level)

    def _process_polyprotein_cleavage(self):
        """Process polyprotein self-cleavage into individual proteins."""
        total_cleaved = 0
        location = CellLocation.CYTOSOL.value

        for poly, count in list(self.sim_state.polyproteins.items()):
            if count <= 0:
                continue

            if poly.self_cleavage_chance <= 0:
                continue

            # Roll for each polyprotein
            cleaved = 0
            for _ in range(count):
                if self.rng.random() * 100 < poly.self_cleavage_chance:
                    cleaved += 1

            if cleaved > 0:
                # Remove cleaved polyproteins
                self.sim_state.polyproteins[poly] -= cleaved
                if self.sim_state.polyproteins[poly] <= 0:
                    del self.sim_state.polyproteins[poly]

                # Add individual proteins
                for entity_id in poly.protein_entity_ids:
                    key = (entity_id, location)
                    if key in self.sim_state.new_entities:
                        self.sim_state.new_entities[key] += cleaved
                    else:
                        self.sim_state.new_entities[key] = cleaved

                total_cleaved += cleaved

        if total_cleaved > 0:
            self.sim_state.log.append(f"  Polyprotein cleavage: {total_cleaved} cleaved")

    def _process_polyprotein_degradation(self):
        """Process polyprotein degradation (same as proteins in cytosol)."""
        location = CellLocation.CYTOSOL.value
        category = EntityCategory.PROTEIN.value
        interferon_level = self.sim_state.interferon_level

        base_chance = self.game_state.database.get_degradation_chance(category, location)

        # Apply interferon effect
        if interferon_level > 0:
            ifn_modifier_percent = self.game_state.database.get_interferon_modifier(category)
            actual_modifier = (ifn_modifier_percent / 100.0) * (interferon_level / INTERFERON_MAX)
            adjusted_chance = base_chance * (1 + actual_modifier)
            adjusted_chance = min(100.0, adjusted_chance)
        else:
            adjusted_chance = base_chance

        total_degraded = 0

        for poly, count in list(self.sim_state.polyproteins.items()):
            if count <= 0:
                continue

            degraded = 0
            for _ in range(count):
                if self.rng.random() * 100 < adjusted_chance:
                    degraded += 1

            if degraded > 0:
                self.sim_state.polyproteins[poly] -= degraded
                if self.sim_state.polyproteins[poly] <= 0:
                    del self.sim_state.polyproteins[poly]
                total_degraded += degraded

        # Also degrade new polyproteins
        for poly, count in list(self.sim_state.new_polyproteins.items()):
            if count <= 0:
                continue

            degraded = 0
            for _ in range(count):
                if self.rng.random() * 100 < adjusted_chance:
                    degraded += 1

            if degraded > 0:
                self.sim_state.new_polyproteins[poly] -= degraded
                if self.sim_state.new_polyproteins[poly] <= 0:
                    del self.sim_state.new_polyproteins[poly]
                total_degraded += degraded

        if total_degraded > 0:
            self.sim_state.log.append(f"  Polyprotein degradation: {total_degraded}")

    def _process_antibodies(self):
        """Process antibody manifestation and elimination."""
        # Check for manifesting antibodies
        current_turn = self.sim_state.turn
        new_queue = []

        for manifest_turn, amount in self.sim_state.antibody_manifest_queue:
            if manifest_turn <= current_turn:
                self.sim_state.antibody_active += int(amount)
            else:
                new_queue.append((manifest_turn, amount))

        self.sim_state.antibody_manifest_queue = new_queue

        # Antibodies eliminate extracellular entities
        if self.sim_state.antibody_active > 0:
            extracellular_count = 0
            extracellular_entities = []

            for (entity_id, location), count in self.sim_state.entities.items():
                if location == CellLocation.EXTRACELLULAR.value:
                    extracellular_count += count
                    extracellular_entities.append((entity_id, count))

            if extracellular_count > 0 and self.sim_state.antibody_active > 0:
                # Eliminate proportionally
                eliminated = min(extracellular_count, self.sim_state.antibody_active)

                # Remove antibodies used
                self.sim_state.antibody_active -= eliminated

                # Remove entities proportionally
                remaining_to_eliminate = eliminated
                for entity_id, count in extracellular_entities:
                    if remaining_to_eliminate <= 0:
                        break

                    key = (entity_id, CellLocation.EXTRACELLULAR.value)
                    to_remove = min(count, remaining_to_eliminate)

                    self.sim_state.entities[key] -= to_remove
                    if self.sim_state.entities[key] <= 0:
                        del self.sim_state.entities[key]

                    remaining_to_eliminate -= to_remove

                if eliminated > 0:
                    self.sim_state.log.append(
                        f"  Antibodies eliminated {eliminated} extracellular entities")

    def _record_history(self):
        """Record current state for graphing."""
        counts = {group: 0 for group in POPULATION_GROUPS}
        counts['Antibodies'] = self.sim_state.antibody_active

        for (entity_id, location), count in self.sim_state.entities.items():
            entity = self.game_state.database.get_entity(entity_id)
            if entity:
                group = population_group(entity.category)
                if group:
                    counts[group] += count

        # Count polyproteins as proteins
        for poly, count in self.sim_state.polyproteins.items():
            counts['Protein'] += count
        for poly, count in self.sim_state.new_polyproteins.items():
            counts['Protein'] += count

        self.sim_state.history.append((self.sim_state.turn, counts.copy()))

        # Track max counts for milestones
        for cat, count in counts.items():
            if cat not in self.sim_state.category_counts:
                self.sim_state.category_counts[cat] = 0
            self.sim_state.category_counts[cat] = max(
                self.sim_state.category_counts[cat], count)

    def _check_conditions(self):
        """Check win/loss conditions."""
        total, virions = self.count_population()

        # Check extinction
        if total == 0:
            self.sim_state.is_ended = True
            self.sim_state.extinction = True
            self.sim_state.log.append("\n=== EXTINCTION ===")
            self._emit(self.on_game_end)
            return

        # Check victory
        if virions >= self.win_threshold:
            self.sim_state.is_ended = True
            self.sim_state.is_victory = True
            self.sim_state.log.append(f"\n=== VICTORY === ({virions} virions)")
            self._emit(self.on_game_end)
            return

    def _update_active_milestones(self):
        """Update the set of active milestones based on prerequisites.

        A milestone is active if:
        - It has not been achieved yet
        - It has no prerequisite, OR its prerequisite has been achieved
        """
        new_active = set()
        for milestone in self.game_state.database.milestones.values():
            # Skip already achieved milestones
            if milestone.id in self.game_state.achieved_milestones:
                continue

            # Check if prerequisite is met
            if milestone.prerequisite_id is None:
                # No prerequisite - always active
                new_active.add(milestone.id)
            elif milestone.prerequisite_id in self.game_state.achieved_milestones:
                # Prerequisite has been achieved - now active
                new_active.add(milestone.id)

        # Check if any new milestones became active
        newly_activated = new_active - self.sim_state.active_milestone_ids
        if newly_activated:
            for milestone_id in newly_activated:
                milestone = self.game_state.database.get_milestone(milestone_id)
                if milestone:
                    self.sim_state.log.append(
                        f"  >> Milestone unlocked: {milestone.name}")

        self.sim_state.active_milestone_ids = new_active

    def _check_milestones(self):
        """Check and award milestones (only checks active milestones)."""
        milestones_achieved = False

        # Only check milestones that are currently active
        for milestone_id in list(self.sim_state.active_milestone_ids):
            milestone = self.game_state.database.get_milestone(milestone_id)
            if not milestone:
                continue

            if milestone.id in self.game_state.achieved_milestones:
                continue

            achieved = False

            if milestone.milestone_type == "Enter compartment":
                if milestone.target_compartment in self.sim_state.locations_entered:
                    achieved = True

            elif milestone.milestone_type == "Produce first entity":
                if milestone.target_entity_category in self.sim_state.categories_produced:
                    achieved = True

            elif milestone.milestone_type == "Produce entity count":
                cat = milestone.target_entity_category
                count = self.sim_state.category_counts.get(cat, 0)
                if count >= milestone.target_count:
                    achieved = True

            elif milestone.milestone_type == "Survive turns":
                if self.sim_state.turn >= milestone.target_turns:
                    achieved = True

            if achieved:
                self.game_state.achieve_milestone(milestone.id)
                self.sim_state.log.append(
                    f"  *** Milestone achieved: {milestone.name} (+{milestone.reward_ep} EP) ***")
                self._emit(self.on_milestone_achieved, milestone.id)
                milestones_achieved = True

        # If any milestones were achieved, update active milestones to unlock new ones
        if milestones_achieved:
            self._update_active_milestones()
            self._emit(self.on_active_milestones_changed)
