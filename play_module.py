"""
Play Module for Viral Sandbox.
Where the virus simulation runs and players observe their virus infecting a cell.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import random

from game_state import GameState
from models import Effect, EffectType, CellLocation, EntityCategory


# Antibody system constants
ANTIBODY_MANIFEST_DELAY = 100  # Turns before antibodies manifest


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
    antibody_stored: float = 0.0
    antibody_active: int = 0
    antibody_manifest_queue: list = field(default_factory=list)  # (manifest_turn, amount)

    # History for graphing
    history: list = field(default_factory=list)  # List of (turn, {category: count})

    # Tracking for milestones
    locations_entered: set = field(default_factory=set)
    categories_produced: set = field(default_factory=set)
    category_counts: dict = field(default_factory=dict)  # category -> max count achieved

    # Simulation log
    log: list = field(default_factory=list)

    # Running state
    is_running: bool = False
    speed: str = "normal"  # "paused", "normal", "fast", "max"

    # End state
    is_ended: bool = False
    is_victory: bool = False
    extinction: bool = False


class PlayModule(tk.Toplevel):
    """Play module window where simulation runs."""

    WIN_THRESHOLD = 10000

    def __init__(self, parent, game_state: GameState,
                 on_return: Optional[Callable] = None):
        super().__init__(parent)

        self.game_state = game_state
        self.on_return_callback = on_return

        self.title("Viral Sandbox - Play Module")
        self.geometry("1400x900")
        self.minsize(1200, 700)

        # Build virus blueprint
        self.effects = self._build_effects_list()
        self.global_effects = self.game_state.get_global_effects(filter_invalid=True)

        # Initialize simulation state
        self.sim_state = SimulationState()
        self._initialize_simulation()

        # Simulation timer
        self.sim_timer = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._create_ui()
        self._update_display()

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

        # Record initial history
        self._record_history()

    def _on_close(self):
        """Handle window close."""
        if self.sim_timer:
            self.after_cancel(self.sim_timer)

        if not self.sim_state.is_ended:
            if messagebox.askyesno("End Round",
                                   "End this play round and return to Builder?"):
                self._end_round(early_exit=True)
        else:
            self._return_to_builder()

    def _create_ui(self):
        """Create the main UI layout."""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Top section - Turn info and status bars
        self._create_top_section(main_frame)

        # Main content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Left side - Entity display and graph
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._create_entity_display(left_frame)
        self._create_graph_display(left_frame)

        # Right side - Controls and milestones
        right_frame = ttk.Frame(content_frame, width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_frame.pack_propagate(False)

        self._create_controls(right_frame)
        self._create_milestone_tracker(right_frame)

    def _create_top_section(self, parent):
        """Create the top section with turn info and status bars."""
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=tk.X, pady=(0, 5))

        # Turn counter
        turn_frame = ttk.Frame(top_frame)
        turn_frame.pack(side=tk.LEFT, padx=10)

        ttk.Label(turn_frame, text="Turn:", font=('TkDefaultFont', 12)).pack(side=tk.LEFT)
        self.turn_var = tk.StringVar(value="0")
        ttk.Label(turn_frame, textvariable=self.turn_var,
                  font=('TkDefaultFont', 14, 'bold')).pack(side=tk.LEFT, padx=5)

        # Entity count
        count_frame = ttk.Frame(top_frame)
        count_frame.pack(side=tk.LEFT, padx=20)

        ttk.Label(count_frame, text="Total Entities:").pack(side=tk.LEFT)
        self.entity_count_var = tk.StringVar(value="10")
        ttk.Label(count_frame, textvariable=self.entity_count_var,
                  font=('TkDefaultFont', 11, 'bold')).pack(side=tk.LEFT, padx=5)

        # Virion count (for win condition)
        virion_frame = ttk.Frame(top_frame)
        virion_frame.pack(side=tk.LEFT, padx=20)

        ttk.Label(virion_frame, text="Virions:").pack(side=tk.LEFT)
        self.virion_count_var = tk.StringVar(value="10")
        ttk.Label(virion_frame, textvariable=self.virion_count_var,
                  font=('TkDefaultFont', 11, 'bold'), foreground='purple').pack(side=tk.LEFT, padx=5)
        ttk.Label(virion_frame, text=f"/ {self.WIN_THRESHOLD}").pack(side=tk.LEFT)

        # Status bars frame
        bars_frame = ttk.Frame(top_frame)
        bars_frame.pack(side=tk.RIGHT, padx=10)

        # Interferon bar
        ifn_frame = ttk.Frame(bars_frame)
        ifn_frame.pack(fill=tk.X, pady=2)

        ttk.Label(ifn_frame, text="Interferon:", width=12).pack(side=tk.LEFT)
        self.ifn_var = tk.StringVar(value="0.0")
        self.ifn_bar = ttk.Progressbar(ifn_frame, length=200, maximum=100)
        self.ifn_bar.pack(side=tk.LEFT, padx=5)
        ttk.Label(ifn_frame, textvariable=self.ifn_var, width=8).pack(side=tk.LEFT)

        # Antibody bar
        ab_frame = ttk.Frame(bars_frame)
        ab_frame.pack(fill=tk.X, pady=2)

        ttk.Label(ab_frame, text="Antibodies:", width=12).pack(side=tk.LEFT)
        self.ab_var = tk.StringVar(value="0 (0 stored)")
        self.ab_bar = ttk.Progressbar(ab_frame, length=200, maximum=100)
        self.ab_bar.pack(side=tk.LEFT, padx=5)
        ttk.Label(ab_frame, textvariable=self.ab_var, width=15).pack(side=tk.LEFT)

    def _create_entity_display(self, parent):
        """Create the entity display section."""
        frame = ttk.LabelFrame(parent, text="Entities by Location")
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # Canvas with scrollbar for entity bars
        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.entity_canvas = tk.Canvas(canvas_frame, bg='white')
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                                   command=self.entity_canvas.yview)

        self.entity_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.entity_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bind resize
        self.entity_canvas.bind('<Configure>', lambda e: self._draw_entity_bars())

    def _create_graph_display(self, parent):
        """Create the graph display section."""
        frame = ttk.LabelFrame(parent, text="Population Over Time")
        frame.pack(fill=tk.X, pady=(0, 5))

        self.graph_canvas = tk.Canvas(frame, height=200, bg='white')
        self.graph_canvas.pack(fill=tk.X, padx=5, pady=5)

        # Legend
        legend_frame = ttk.Frame(frame)
        legend_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        colors = [('Virion', 'purple'), ('RNA', 'green'),
                  ('DNA', 'blue'), ('Protein', 'orange')]
        for name, color in colors:
            ttk.Label(legend_frame, text="■", foreground=color).pack(side=tk.LEFT)
            ttk.Label(legend_frame, text=name).pack(side=tk.LEFT, padx=(0, 10))

    def _create_controls(self, parent):
        """Create the simulation control section."""
        frame = ttk.LabelFrame(parent, text="Simulation Controls")
        frame.pack(fill=tk.X, pady=(0, 5))

        # Speed controls
        speed_frame = ttk.Frame(frame)
        speed_frame.pack(fill=tk.X, padx=5, pady=5)

        self.speed_var = tk.StringVar(value="paused")

        speeds = [("⏸ Pause", "paused"), ("▶ Normal", "normal"),
                  ("▶▶ Fast", "fast"), ("⏩ Max", "max")]

        for text, value in speeds:
            ttk.Radiobutton(speed_frame, text=text, variable=self.speed_var,
                           value=value, command=self._on_speed_change).pack(side=tk.LEFT, padx=2)

        # Action buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="View Log",
                   command=self._show_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="End Round",
                   command=self._request_end_round).pack(side=tk.LEFT, padx=2)

        # Status
        self.status_var = tk.StringVar(value="Paused - Select speed to start")
        ttk.Label(frame, textvariable=self.status_var,
                  font=('TkDefaultFont', 10, 'italic')).pack(padx=5, pady=5)

    def _create_milestone_tracker(self, parent):
        """Create the milestone tracking section."""
        frame = ttk.LabelFrame(parent, text="Milestones")
        frame.pack(fill=tk.BOTH, expand=True)

        # Scrollable list of milestones
        canvas = tk.Canvas(frame, bg='white')
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        self.milestone_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas.create_window((0, 0), window=self.milestone_frame, anchor='nw')
        self.milestone_frame.bind('<Configure>',
                                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        self.milestone_canvas = canvas
        self._populate_milestones()

    def _populate_milestones(self):
        """Populate the milestone list."""
        for widget in self.milestone_frame.winfo_children():
            widget.destroy()

        self.milestone_labels = {}

        for milestone in self.game_state.database.milestones.values():
            frame = ttk.Frame(self.milestone_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)

            # Check if already achieved
            achieved = milestone.id in self.game_state.achieved_milestones

            # Checkbox-style indicator
            indicator = "✓" if achieved else "○"
            color = "green" if achieved else "gray"

            lbl = ttk.Label(frame, text=indicator, foreground=color, width=2)
            lbl.pack(side=tk.LEFT)

            name_lbl = ttk.Label(frame, text=f"{milestone.name} (+{milestone.reward_ep} EP)")
            name_lbl.pack(side=tk.LEFT)

            self.milestone_labels[milestone.id] = (lbl, name_lbl)

    def _on_speed_change(self):
        """Handle speed control change."""
        speed = self.speed_var.get()
        self.sim_state.speed = speed

        if self.sim_timer:
            self.after_cancel(self.sim_timer)
            self.sim_timer = None

        if speed == "paused":
            self.status_var.set("Paused")
            self.sim_state.is_running = False
        else:
            self.sim_state.is_running = True
            self._schedule_next_turn()

    def _schedule_next_turn(self):
        """Schedule the next simulation turn."""
        if not self.sim_state.is_running or self.sim_state.is_ended:
            return

        speed = self.sim_state.speed
        if speed == "normal":
            delay = 500  # ms
        elif speed == "fast":
            delay = 100
        elif speed == "max":
            delay = 1
        else:
            return

        self.sim_timer = self.after(delay, self._run_turn)

    def _run_turn(self):
        """Run a single simulation turn."""
        if not self.sim_state.is_running or self.sim_state.is_ended:
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

        # Update display
        self._update_display()

        # Check milestones
        self._check_milestones()

        # Schedule next turn
        if not self.sim_state.is_ended:
            self._schedule_next_turn()

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

        # Get modifiers for transitions
        modifiers = self._get_transition_modifiers()

        for effect in transition_effects:
            self._apply_transition(effect, modifiers)

    def _get_transition_modifiers(self) -> dict:
        """Get all transition modifiers keyed by effect ID and category.

        Modifiers are stored as percentage multipliers (100 = no change, 150 = 1.5x).
        Multiple modifiers targeting the same effect/category are multiplied together.
        """
        modifiers = defaultdict(lambda: {'chance': 100, 'interferon': 100, 'antibody': 100})

        all_effects = self.effects + self.global_effects
        modify_effects = [e for e in all_effects
                         if e.effect_type == EffectType.MODIFY_TRANSITION.value]

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
            if random.random() * 100 < total_chance:
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
            self.sim_state.interferon_level = min(100, self.sim_state.interferon_level)

        # Apply antibody response with multiplicative modifiers
        ab_resp = effect.antibody_response
        ab_resp = ab_resp * (modifier.get('antibody', 100) / 100) * (cat_modifier.get('antibody', 100) / 100)
        if ab_resp > 0:
            self.sim_state.antibody_stored += ab_resp * successes
            # Queue antibody manifestation
            manifest_turn = self.sim_state.turn + ANTIBODY_MANIFEST_DELAY
            self.sim_state.antibody_manifest_queue.append((manifest_turn, ab_resp * successes))

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

        for effect in translation_effects:
            self._apply_translation(effect)

    def _apply_translation(self, effect: Effect):
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

        # Calculate chance
        chance = effect.translation_chance
        if chance <= 0:
            return

        # For each template, attempt translation
        successes = 0
        for _ in range(int(min_possible)):
            if random.random() * 100 < chance:
                successes += 1

        if successes == 0:
            return

        # For each success, pick an ORF and produce protein
        for _ in range(successes):
            orf_info = random.choice(valid_orfs)
            self._translate_orf(orf_info)

        self.sim_state.log.append(
            f"  {effect.name}: {successes}x translation events")

    def _translate_orf(self, orf_info: dict):
        """Translate an ORF, producing appropriate protein or polyprotein."""
        genes = orf_info['genes']
        orf_name = orf_info['orf']

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

        for effect in location_effects:
            self._apply_location_change(effect)

    def _apply_location_change(self, effect: Effect):
        """Apply a single location change effect."""
        source = effect.source_location
        target = effect.target_location
        chance = effect.location_change_chance

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
                if random.random() * 100 < chance:
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
        interferon_level = self.sim_state.interferon_level

        for (entity_id, location), count in list(self.sim_state.entities.items()):
            entity = self.game_state.database.get_entity(entity_id)
            if not entity:
                continue

            category = entity.category
            base_chance = self.game_state.database.get_degradation_chance(category, location)

            # Apply interferon effect (only affects intracellular locations)
            if location != CellLocation.EXTRACELLULAR.value and interferon_level > 0:
                # Get per-category interferon modifier (% increase at max interferon)
                ifn_modifier_percent = self.game_state.database.get_interferon_modifier(category)
                # Calculate actual modifier: scales linearly with interferon level
                # At interferon 100 and modifier 100%, this equals 1.0 (doubles the chance)
                actual_modifier = (ifn_modifier_percent / 100.0) * (interferon_level / 100.0)
                adjusted_chance = base_chance * (1 + actual_modifier)
                # Cap at 100%
                adjusted_chance = min(100.0, adjusted_chance)
            else:
                adjusted_chance = base_chance

            # Calculate degradation
            degraded = 0
            for _ in range(count):
                if random.random() * 100 < adjusted_chance:
                    degraded += 1

            if degraded > 0:
                self.sim_state.entities[(entity_id, location)] -= degraded
                if self.sim_state.entities[(entity_id, location)] <= 0:
                    del self.sim_state.entities[(entity_id, location)]
                total_degraded += degraded

        # Also degrade new entities
        for (entity_id, location), count in list(self.sim_state.new_entities.items()):
            entity = self.game_state.database.get_entity(entity_id)
            if not entity:
                continue

            category = entity.category
            base_chance = self.game_state.database.get_degradation_chance(category, location)

            # Apply interferon effect (only affects intracellular locations)
            if location != CellLocation.EXTRACELLULAR.value and interferon_level > 0:
                ifn_modifier_percent = self.game_state.database.get_interferon_modifier(category)
                actual_modifier = (ifn_modifier_percent / 100.0) * (interferon_level / 100.0)
                adjusted_chance = base_chance * (1 + actual_modifier)
                adjusted_chance = min(100.0, adjusted_chance)
            else:
                adjusted_chance = base_chance

            degraded = 0
            for _ in range(count):
                if random.random() * 100 < adjusted_chance:
                    degraded += 1

            if degraded > 0:
                self.sim_state.new_entities[(entity_id, location)] -= degraded
                if self.sim_state.new_entities[(entity_id, location)] <= 0:
                    del self.sim_state.new_entities[(entity_id, location)]
                total_degraded += degraded

        if total_degraded > 0:
            self.sim_state.log.append(f"  Degradation: {total_degraded} entities")

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
                if random.random() * 100 < poly.self_cleavage_chance:
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
            actual_modifier = (ifn_modifier_percent / 100.0) * (interferon_level / 100.0)
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
                if random.random() * 100 < adjusted_chance:
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
                if random.random() * 100 < adjusted_chance:
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
        counts = {
            'Virion': 0,
            'RNA': 0,
            'DNA': 0,
            'Protein': 0
        }

        for (entity_id, location), count in self.sim_state.entities.items():
            entity = self.game_state.database.get_entity(entity_id)
            if entity:
                cat = entity.category
                if cat == EntityCategory.VIRION.value or cat == EntityCategory.VIRAL_COMPLEX.value:
                    counts['Virion'] += count
                elif cat == EntityCategory.RNA.value:
                    counts['RNA'] += count
                elif cat == EntityCategory.DNA.value:
                    counts['DNA'] += count
                elif cat == EntityCategory.PROTEIN.value:
                    counts['Protein'] += count

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
        # Count total entities and virions
        total = 0
        virions = 0

        for (entity_id, location), count in self.sim_state.entities.items():
            total += count
            entity = self.game_state.database.get_entity(entity_id)
            if entity and entity.category in [EntityCategory.VIRION.value,
                                               EntityCategory.VIRAL_COMPLEX.value]:
                virions += count

        # Also count new entities
        for (entity_id, location), count in self.sim_state.new_entities.items():
            total += count
            entity = self.game_state.database.get_entity(entity_id)
            if entity and entity.category in [EntityCategory.VIRION.value,
                                               EntityCategory.VIRAL_COMPLEX.value]:
                virions += count

        # Also count polyproteins
        total += sum(self.sim_state.polyproteins.values())
        total += sum(self.sim_state.new_polyproteins.values())

        # Check extinction
        if total == 0:
            self.sim_state.is_ended = True
            self.sim_state.extinction = True
            self.sim_state.is_running = False
            self.sim_state.log.append("\n=== EXTINCTION ===")
            self.status_var.set("Virus Extinct!")
            self._show_end_dialog()
            return

        # Check victory
        if virions >= self.WIN_THRESHOLD:
            self.sim_state.is_ended = True
            self.sim_state.is_victory = True
            self.sim_state.is_running = False
            self.sim_state.log.append(f"\n=== VICTORY === ({virions} virions)")
            self.status_var.set("VICTORY!")
            self._show_end_dialog()
            return

    def _check_milestones(self):
        """Check and award milestones."""
        for milestone in self.game_state.database.milestones.values():
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
                self._update_milestone_display(milestone.id)

    def _update_milestone_display(self, milestone_id: int):
        """Update milestone display when achieved."""
        if milestone_id in self.milestone_labels:
            lbl, name_lbl = self.milestone_labels[milestone_id]
            lbl.configure(text="✓", foreground="green")

    def _update_display(self):
        """Update all display elements."""
        self.turn_var.set(str(self.sim_state.turn))

        # Count entities (including polyproteins)
        total = (sum(self.sim_state.entities.values()) +
                 sum(self.sim_state.new_entities.values()) +
                 sum(self.sim_state.polyproteins.values()) +
                 sum(self.sim_state.new_polyproteins.values()))
        self.entity_count_var.set(str(total))

        # Count virions
        virions = 0
        for (entity_id, location), count in self.sim_state.entities.items():
            entity = self.game_state.database.get_entity(entity_id)
            if entity and entity.category in [EntityCategory.VIRION.value,
                                               EntityCategory.VIRAL_COMPLEX.value]:
                virions += count
        for (entity_id, location), count in self.sim_state.new_entities.items():
            entity = self.game_state.database.get_entity(entity_id)
            if entity and entity.category in [EntityCategory.VIRION.value,
                                               EntityCategory.VIRAL_COMPLEX.value]:
                virions += count
        self.virion_count_var.set(str(virions))

        # Update status bars
        self.ifn_bar['value'] = self.sim_state.interferon_level
        self.ifn_var.set(f"{self.sim_state.interferon_level:.1f}")

        stored = self.sim_state.antibody_stored
        active = self.sim_state.antibody_active
        self.ab_bar['value'] = min(100, active)
        self.ab_var.set(f"{active} ({stored:.0f} stored)")

        # Draw entity bars
        self._draw_entity_bars()

        # Draw graph
        self._draw_graph()

    def _draw_entity_bars(self):
        """Draw entity bars on the canvas."""
        self.entity_canvas.delete("all")

        width = self.entity_canvas.winfo_width()
        if width < 10:
            width = 400

        # Group entities by location
        location_order = [
            CellLocation.EXTRACELLULAR.value,
            CellLocation.MEMBRANE.value,
            CellLocation.ENDOSOME.value,
            CellLocation.ER.value,
            CellLocation.CYTOSOL.value,
            CellLocation.NUCLEUS.value
        ]

        entities_by_location = defaultdict(list)
        all_entities = dict(self.sim_state.entities)
        for key, count in self.sim_state.new_entities.items():
            if key in all_entities:
                all_entities[key] += count
            else:
                all_entities[key] = count

        for (entity_id, location), count in all_entities.items():
            entities_by_location[location].append((entity_id, count, False))  # False = not polyprotein

        # Add polyproteins to cytosol
        all_polyproteins = dict(self.sim_state.polyproteins)
        for poly, count in self.sim_state.new_polyproteins.items():
            if poly in all_polyproteins:
                all_polyproteins[poly] += count
            else:
                all_polyproteins[poly] = count

        for poly, count in all_polyproteins.items():
            if count > 0:
                entities_by_location[CellLocation.CYTOSOL.value].append((poly, count, True))  # True = polyprotein

        # Find max count for scaling
        all_counts = [c for c in all_entities.values()] + [c for c in all_polyproteins.values()] + [10]
        max_count = max(all_counts)

        y = 10
        bar_height = 18
        text_area_width = 155  # Space reserved for entity names
        bar_start_x = 160  # Where bars begin

        for location in location_order:
            # Always show location header (even if empty)
            self.entity_canvas.create_text(10, y, text=location, anchor='w',
                                           font=('TkDefaultFont', 10, 'bold'))
            y += 20

            # Entity bars (if any entities in this location)
            if location in entities_by_location:
                for item, count, is_poly in sorted(entities_by_location[location],
                                                   key=lambda x: -x[1]):
                    if is_poly:
                        # Polyprotein - build display name using abbreviations if available
                        poly = item
                        protein_names = []
                        for eid in poly.protein_entity_ids:
                            entity = self.game_state.database.get_entity(eid)
                            if entity:
                                protein_names.append(entity.get_display_name(use_abbreviation=True))
                            else:
                                protein_names.append(f"ID:{eid}")
                        name = f"Poly ({', '.join(protein_names)})"
                        color = '#FF8C00'  # Dark orange for polyproteins
                    else:
                        entity_id = item
                        entity = self.game_state.database.get_entity(entity_id)
                        name = entity.name if entity else f"Entity {entity_id}"

                        # Category color
                        color = '#888888'
                        if entity:
                            cat = entity.category
                            if cat == EntityCategory.VIRION.value or cat == EntityCategory.VIRAL_COMPLEX.value:
                                color = 'purple'
                            elif cat == EntityCategory.RNA.value:
                                color = 'green'
                            elif cat == EntityCategory.DNA.value:
                                color = 'blue'
                            elif cat == EntityCategory.PROTEIN.value:
                                color = 'orange'

                    # Draw bar (compressed to leave more space for text)
                    max_bar_width = width - bar_start_x - 50  # Leave space for count text
                    bar_width = int((count / max_count) * max_bar_width)
                    bar_width = max(5, bar_width)

                    self.entity_canvas.create_rectangle(
                        bar_start_x, y, bar_start_x + bar_width, y + bar_height,
                        fill=color, outline=color)

                    # Entity name (truncate if needed)
                    display_name = name[:22] if len(name) > 22 else name
                    self.entity_canvas.create_text(
                        15, y + bar_height // 2, text=display_name, anchor='w',
                        font=('TkDefaultFont', 9))

                    # Count
                    self.entity_canvas.create_text(
                        bar_start_x + bar_width + 5, y + bar_height // 2, text=str(count),
                        anchor='w', font=('TkDefaultFont', 9))

                    y += bar_height + 2
            else:
                # Show "(empty)" for locations with no entities
                self.entity_canvas.create_text(15, y, text="(empty)", anchor='w',
                                               font=('TkDefaultFont', 9, 'italic'),
                                               fill='#888888')
                y += 18

            y += 8  # Space between locations

        # Update scroll region
        self.entity_canvas.configure(scrollregion=(0, 0, width, y + 20))

    def _draw_graph(self):
        """Draw the population graph."""
        self.graph_canvas.delete("all")

        width = self.graph_canvas.winfo_width()
        height = self.graph_canvas.winfo_height()

        if width < 10 or height < 10:
            width = 400
            height = 200

        margin_left = 45
        margin_right = 20
        margin_top = 15
        margin_bottom = 35  # More space for x-axis labels
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom

        if len(self.sim_state.history) < 2:
            return

        # Get last 50 turns of history
        history = self.sim_state.history[-50:]

        # Find max value and add 5% padding so lines don't touch the top
        max_val = 10
        for turn, counts in history:
            for cat, count in counts.items():
                max_val = max(max_val, count)
        max_val = int(max_val * 1.05) + 1  # Add 5% padding

        # Get turn range for x-axis labels
        first_turn = history[0][0]
        last_turn = history[-1][0]

        # Draw axes
        self.graph_canvas.create_line(margin_left, height - margin_bottom,
                                       width - margin_right, height - margin_bottom, fill='gray')
        self.graph_canvas.create_line(margin_left, height - margin_bottom,
                                       margin_left, margin_top, fill='gray')

        # Draw Y-axis scale labels
        self.graph_canvas.create_text(margin_left - 5, height - margin_bottom,
                                       text="0", anchor='e', font=('TkDefaultFont', 8))
        self.graph_canvas.create_text(margin_left - 5, margin_top,
                                       text=str(max_val), anchor='e', font=('TkDefaultFont', 8))
        # Middle Y label
        self.graph_canvas.create_text(margin_left - 5, margin_top + graph_height // 2,
                                       text=str(max_val // 2), anchor='e', font=('TkDefaultFont', 8))

        # Draw X-axis labels (turn numbers in 5-turn increments)
        if last_turn > first_turn:
            # Find first turn that's a multiple of 5
            start_label = ((first_turn // 5) + 1) * 5
            for turn_label in range(start_label, last_turn + 1, 5):
                # Calculate x position for this turn
                turn_index = turn_label - first_turn
                if turn_index >= 0 and turn_index <= (last_turn - first_turn):
                    x = margin_left + (turn_index / max(1, last_turn - first_turn)) * graph_width
                    self.graph_canvas.create_text(x, height - margin_bottom + 12,
                                                   text=str(turn_label), anchor='n',
                                                   font=('TkDefaultFont', 8))
                    # Small tick mark
                    self.graph_canvas.create_line(x, height - margin_bottom,
                                                   x, height - margin_bottom + 3, fill='gray')

        # X-axis label
        self.graph_canvas.create_text(margin_left + graph_width // 2, height - 5,
                                       text="Turn", anchor='n', font=('TkDefaultFont', 8))

        # Draw lines for each category
        colors = {'Virion': 'purple', 'RNA': 'green', 'DNA': 'blue', 'Protein': 'orange'}

        for category, color in colors.items():
            points = []
            for i, (turn, counts) in enumerate(history):
                x = margin_left + (i / max(1, len(history) - 1)) * graph_width
                y = height - margin_bottom - (counts.get(category, 0) / max_val) * graph_height
                points.append((x, y))

            if len(points) >= 2:
                for i in range(len(points) - 1):
                    self.graph_canvas.create_line(
                        points[i][0], points[i][1],
                        points[i+1][0], points[i+1][1],
                        fill=color, width=2)

    def _show_log(self):
        """Show the simulation log in a new window."""
        log_window = tk.Toplevel(self)
        log_window.title("Simulation Log")
        log_window.geometry("600x500")

        text = tk.Text(log_window, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_window, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        text.insert('1.0', '\n'.join(self.sim_state.log))
        text.configure(state='disabled')

    def _request_end_round(self):
        """Request to end the current round early."""
        if messagebox.askyesno("End Round",
                               "End this play round and return to Builder?"):
            self._end_round(early_exit=True)

    def _show_end_dialog(self):
        """Show the end-of-round dialog."""
        if self.sim_timer:
            self.after_cancel(self.sim_timer)

        dialog = tk.Toplevel(self)
        dialog.title("Round Complete")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()

        # Handle window close button
        def on_dialog_close():
            dialog.destroy()
            self._end_round()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Result
        if self.sim_state.is_victory:
            result_text = "VICTORY!"
            result_color = "green"
        elif self.sim_state.extinction:
            result_text = "Virus Extinct"
            result_color = "red"
        else:
            result_text = "Round Ended"
            result_color = "black"

        ttk.Label(frame, text=result_text,
                  font=('TkDefaultFont', 16, 'bold'),
                  foreground=result_color).pack(pady=10)

        # Stats
        ttk.Label(frame, text=f"Turns survived: {self.sim_state.turn}").pack()

        # Milestones earned this round
        milestones_earned = [m for m in self.game_state.database.milestones.values()
                           if m.id in self.game_state.achieved_milestones]
        if milestones_earned:
            ttk.Label(frame, text="\nMilestones achieved:",
                      font=('TkDefaultFont', 10, 'bold')).pack()
            for m in milestones_earned:
                ttk.Label(frame, text=f"  • {m.name} (+{m.reward_ep} EP)").pack()

        ttk.Label(frame, text=f"\nTotal EP: {self.game_state.evolution_points}",
                  font=('TkDefaultFont', 11, 'bold')).pack()

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)

        ttk.Button(btn_frame, text="View Log",
                   command=self._show_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Return to Builder",
                   command=lambda: [dialog.destroy(), self._end_round()]).pack(side=tk.LEFT, padx=5)

    def _end_round(self, early_exit: bool = False):
        """End the current round and return to builder."""
        if self.sim_timer:
            self.after_cancel(self.sim_timer)

        self.sim_state.is_ended = True
        self.sim_state.is_running = False

        if early_exit:
            self.sim_state.log.append("\n=== Round ended early ===")

        self._return_to_builder()

    def _return_to_builder(self):
        """Return to the builder module."""
        # Call callback first (while this window still exists)
        if self.on_return_callback:
            self.on_return_callback(victory=self.sim_state.is_victory)

        # Then destroy this window
        self.destroy()
