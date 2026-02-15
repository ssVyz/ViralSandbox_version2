"""
Game state manager for Viral Sandbox.
Tracks the current game session state.
"""
import random
from dataclasses import dataclass, field
from typing import Optional
from database import GameDatabase
from models import Gene, Effect, EffectType


@dataclass
class VirusConfig:
    """Configuration for the player's virus."""
    # Genome configuration
    nucleic_acid: str = "RNA"  # "RNA" or "DNA"
    strandedness: str = "single"  # "single" or "double"
    polarity: str = "positive"  # "positive" or "negative" (for single-stranded)

    # Virion type
    virion_type: str = "Enveloped"  # "Enveloped" or "Unenveloped"

    # Whether config has been locked in
    is_locked: bool = False

    # Genome entity IDs (from database.py constants)
    POSITIVE_SENSE_RNA_ID = 3
    NEGATIVE_SENSE_RNA_ID = 4
    SSDNA_ID = 5
    DSDNA_ID = 6

    def get_genome_string(self) -> str:
        """Get a human-readable genome description."""
        if self.strandedness == "double":
            return f"ds{self.nucleic_acid}"
        else:
            polarity_symbol = "+" if self.polarity == "positive" else "-"
            return f"({polarity_symbol})ss{self.nucleic_acid}"

    def get_genome_entity_ids(self) -> list[int]:
        """Get the entity ID(s) for the genome based on current configuration.

        Returns a list of entity IDs:
        - For dsRNA: returns both positive and negative sense RNA IDs
        - For all other genome types: returns a single ID in a list
        """
        if self.nucleic_acid == "RNA":
            if self.strandedness == "double":
                # dsRNA = both positive and negative sense strands
                return [self.POSITIVE_SENSE_RNA_ID, self.NEGATIVE_SENSE_RNA_ID]
            else:
                # ssRNA - depends on polarity
                if self.polarity == "positive":
                    return [self.POSITIVE_SENSE_RNA_ID]
                else:
                    return [self.NEGATIVE_SENSE_RNA_ID]
        else:  # DNA
            if self.strandedness == "double":
                return [self.DSDNA_ID]
            else:
                return [self.SSDNA_ID]

    def copy(self) -> "VirusConfig":
        """Create a copy of this config."""
        return VirusConfig(
            nucleic_acid=self.nucleic_acid,
            strandedness=self.strandedness,
            polarity=self.polarity,
            virion_type=self.virion_type,
            is_locked=self.is_locked
        )


@dataclass
class GameState:
    """Manages the state of a game session."""
    database: GameDatabase

    # Player resources
    evolution_points: int = 100

    # Gene management
    available_genes: list = field(default_factory=list)  # Gene IDs in hand
    installed_genes: list = field(default_factory=list)  # Gene IDs (int) or ORF markers (str like "ORF-1")

    # ORF tracking
    _orf_counter: int = 0  # Counter for generating ORF names
    _total_orfs_installed: int = 0  # Total ORFs ever installed (for cost calculation)

    # Terminator tracking
    _terminator_counter: int = 0  # Counter for generating Terminator names

    # Virus configuration
    virus_config: VirusConfig = field(default_factory=VirusConfig)
    pending_config: Optional[VirusConfig] = None  # Config changes not yet locked in

    # Game progress
    current_round: int = 1
    max_rounds: int = 10

    # Milestones achieved (milestone IDs)
    achieved_milestones: set = field(default_factory=set)

    # Game settings
    starting_ep: int = 100
    starting_hand_size: int = 7
    genes_offered_per_round: int = 5
    config_lock_cost: int = 10
    orf_cost: int = 20  # Cost for ORFs after the first one
    terminator_cost: int = 10  # Cost to install a terminator
    terminator_chance: int = 100  # Percentage chance terminators apply (1-100)
    win_threshold: int = 10000

    # Game status
    game_over: bool = False
    game_won: bool = False

    def __post_init__(self):
        """Initialize pending config as a copy of virus config."""
        if self.pending_config is None:
            self.pending_config = self.virus_config.copy()

    @classmethod
    def new_game(cls, database: GameDatabase,
                 starting_ep: int = 100,
                 starting_hand_size: int = 7) -> "GameState":
        """Create a new game state with a random starting hand."""
        state = cls(
            database=database,
            evolution_points=starting_ep,
            starting_ep=starting_ep,
            starting_hand_size=starting_hand_size
        )

        # Draw random starting hand
        state._draw_genes(starting_hand_size)

        return state

    def _draw_genes(self, count: int) -> list:
        """Draw random genes from the database and add to available genes."""
        all_gene_ids = list(self.database.genes.keys())

        # Filter out genes already in hand or installed
        available_ids = [gid for gid in all_gene_ids
                        if gid not in self.available_genes
                        and gid not in self.installed_genes]

        # Draw up to count genes
        draw_count = min(count, len(available_ids))
        if draw_count > 0:
            drawn = random.sample(available_ids, draw_count)
            self.available_genes.extend(drawn)
            return drawn
        return []

    def get_gene(self, gene_id: int) -> Optional[Gene]:
        """Get a gene from the database."""
        return self.database.get_gene(gene_id)

    def get_effect(self, effect_id: int) -> Optional[Effect]:
        """Get an effect from the database."""
        return self.database.get_effect(effect_id)

    def has_utr_installed(self) -> bool:
        """Check if a UTR gene is already installed."""
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and gene.is_utr:
                    return True
        return False

    def get_installed_utr_gene_id(self) -> int | None:
        """Get the ID of the installed UTR gene, or None if none installed."""
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and gene.is_utr:
                    return item
        return None

    def has_polymerase_installed(self) -> bool:
        """Check if a polymerase gene is already installed."""
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and gene.is_polymerase:
                    return True
        return False

    def can_install_gene(self, gene_id: int) -> tuple[bool, str]:
        """Check if a gene can be installed. Returns (can_install, reason)."""
        gene = self.get_gene(gene_id)
        if not gene:
            return False, "Gene not found"

        if gene_id not in self.available_genes:
            return False, "Gene not in available genes"

        if gene_id in self.installed_genes:
            return False, "Gene already installed"

        if gene.install_cost > self.evolution_points:
            return False, f"Not enough EP (need {gene.install_cost}, have {self.evolution_points})"

        # Check UTR constraint: only one UTR gene allowed
        if gene.is_utr and self.has_utr_installed():
            return False, "Only one UTR gene can be installed at a time"

        # Check polymerase constraint: only one polymerase gene allowed
        if gene.is_polymerase and self.has_polymerase_installed():
            return False, "Only one polymerase gene can be installed at a time"

        return True, "OK"

    def install_gene(self, gene_id: int) -> tuple[bool, str]:
        """Install a gene from available genes. Returns (success, message)."""
        can_install, reason = self.can_install_gene(gene_id)
        if not can_install:
            return False, reason

        gene = self.get_gene(gene_id)

        # Pay the cost
        self.evolution_points -= gene.install_cost

        # Move gene from available to installed
        self.available_genes.remove(gene_id)

        # UTR genes always go at the beginning (5' end)
        if gene.is_utr:
            self.installed_genes.insert(0, gene_id)
        else:
            self.installed_genes.append(gene_id)

        return True, f"Installed {gene.name} for {gene.install_cost} EP"

    def remove_gene(self, gene_id: int) -> tuple[bool, str]:
        """Remove an installed gene. It goes back to available genes."""
        if gene_id not in self.installed_genes:
            return False, "Gene not installed"

        gene = self.get_gene(gene_id)

        # Move gene from installed to available
        self.installed_genes.remove(gene_id)
        self.available_genes.append(gene_id)

        return True, f"Removed {gene.name}"

    def move_gene_up(self, gene_id: int) -> bool:
        """Move an installed gene up in the order. Returns True if moved."""
        if gene_id not in self.installed_genes:
            return False

        gene = self.get_gene(gene_id)
        if gene and gene.is_utr:
            return False  # UTR genes cannot be moved

        idx = self.installed_genes.index(gene_id)
        if idx == 0:
            return False  # Already at top

        # Don't allow moving past UTR gene at position 0
        prev_item = self.installed_genes[idx - 1]
        if not self.is_orf(prev_item):
            prev_gene = self.get_gene(prev_item)
            if prev_gene and prev_gene.is_utr:
                return False  # Cannot move past UTR

        # Swap with previous gene
        self.installed_genes[idx], self.installed_genes[idx - 1] = \
            self.installed_genes[idx - 1], self.installed_genes[idx]
        return True

    def move_gene_down(self, gene_id: int) -> bool:
        """Move an installed gene down in the order. Returns True if moved."""
        if gene_id not in self.installed_genes:
            return False

        gene = self.get_gene(gene_id)
        if gene and gene.is_utr:
            return False  # UTR genes cannot be moved

        idx = self.installed_genes.index(gene_id)
        if idx >= len(self.installed_genes) - 1:
            return False  # Already at bottom

        # Swap with next gene
        self.installed_genes[idx], self.installed_genes[idx + 1] = \
            self.installed_genes[idx + 1], self.installed_genes[idx]
        return True

    # ORF Management Methods

    @staticmethod
    def is_orf(item) -> bool:
        """Check if an item in installed_genes is an ORF."""
        return isinstance(item, str) and item.startswith("ORF-")

    @staticmethod
    def is_terminator(item) -> bool:
        """Check if an item in installed_genes is a Terminator."""
        return isinstance(item, str) and item.startswith("Term-")

    @staticmethod
    def is_marker(item) -> bool:
        """Check if an item is an ORF or Terminator marker (not a gene)."""
        return GameState.is_orf(item) or GameState.is_terminator(item)

    def get_orf_cost(self) -> int:
        """Get the cost to install the next ORF."""
        # First ORF is free, subsequent ones cost orf_cost EP
        if self._total_orfs_installed == 0:
            return 0
        return self.orf_cost

    def can_install_orf(self) -> tuple[bool, str]:
        """Check if an ORF can be installed."""
        cost = self.get_orf_cost()
        if cost > self.evolution_points:
            return False, f"Not enough EP (need {cost}, have {self.evolution_points})"
        return True, "OK"

    def install_orf(self) -> tuple[bool, str]:
        """Install a new ORF. Returns (success, message)."""
        can_install, reason = self.can_install_orf()
        if not can_install:
            return False, reason

        cost = self.get_orf_cost()

        # Pay the cost
        self.evolution_points -= cost

        # Generate temporary ORF name (will be renumbered)
        self._orf_counter += 1
        self._total_orfs_installed += 1
        orf_name = f"ORF-{self._orf_counter}"

        # Add to installed list
        self.installed_genes.append(orf_name)

        # Renumber to ensure correct sequential naming
        self.renumber_markers()

        # Get the actual name after renumbering (it's the last ORF)
        orf_count = self.get_installed_orf_count()
        actual_name = f"ORF-{orf_count}"

        if cost == 0:
            return True, f"Added {actual_name} (free)"
        return True, f"Added {actual_name} for {cost} EP"

    def remove_orf(self, orf_name: str) -> tuple[bool, str, dict]:
        """Remove an ORF from installed genes. No cost refund.

        Returns (success, message, rename_map) where rename_map contains
        any markers that were renamed due to renumbering.
        """
        if not self.is_orf(orf_name):
            return False, "Not a valid ORF", {}

        if orf_name not in self.installed_genes:
            return False, "ORF not installed", {}

        self.installed_genes.remove(orf_name)
        rename_map = self.renumber_markers()
        return True, f"Removed {orf_name}", rename_map

    # Terminator Management Methods

    def can_install_terminator(self) -> tuple[bool, str]:
        """Check if a Terminator can be installed."""
        if self.terminator_cost > self.evolution_points:
            return False, f"Not enough EP (need {self.terminator_cost}, have {self.evolution_points})"
        return True, "OK"

    def install_terminator(self) -> tuple[bool, str]:
        """Install a new Terminator. Returns (success, message)."""
        can_install, reason = self.can_install_terminator()
        if not can_install:
            return False, reason

        # Pay the cost
        self.evolution_points -= self.terminator_cost

        # Generate temporary Terminator name (will be renumbered)
        self._terminator_counter += 1
        term_name = f"Term-{self._terminator_counter}"

        # Add to installed list
        self.installed_genes.append(term_name)

        # Renumber to ensure correct sequential naming
        self.renumber_markers()

        # Get the actual name after renumbering (it's the last Terminator)
        term_count = self.get_installed_terminator_count()
        actual_name = f"Term-{term_count}"

        return True, f"Added {actual_name} for {self.terminator_cost} EP"

    def remove_terminator(self, term_name: str) -> tuple[bool, str, dict]:
        """Remove a Terminator from installed genes. Free removal.

        Returns (success, message, rename_map) where rename_map contains
        any markers that were renamed due to renumbering.
        """
        if not self.is_terminator(term_name):
            return False, "Not a valid Terminator", {}

        if term_name not in self.installed_genes:
            return False, "Terminator not installed", {}

        self.installed_genes.remove(term_name)
        rename_map = self.renumber_markers()
        return True, f"Removed {term_name} (free)", rename_map

    def renumber_markers(self) -> dict:
        """Renumber all ORFs and Terminators based on their position in the list.

        This ensures ORF-1 is always the first ORF, ORF-2 is the second, etc.
        Same for Terminators.

        Returns a mapping of old names to new names for updating references.
        """
        rename_map = {}
        orf_count = 0
        term_count = 0

        for idx, item in enumerate(self.installed_genes):
            if self.is_orf(item):
                orf_count += 1
                new_name = f"ORF-{orf_count}"
                if item != new_name:
                    rename_map[item] = new_name
                    self.installed_genes[idx] = new_name
            elif self.is_terminator(item):
                term_count += 1
                new_name = f"Term-{term_count}"
                if item != new_name:
                    rename_map[item] = new_name
                    self.installed_genes[idx] = new_name

        return rename_map

    def move_item_up(self, item) -> tuple[bool, dict]:
        """Move an installed item (gene, ORF, or Terminator) up in the order.

        Returns (moved, rename_map) where rename_map contains any markers
        that were renamed due to renumbering after the move.
        """
        if item not in self.installed_genes:
            return False, {}

        # UTR genes cannot be moved - they must stay at position 0
        if not self.is_marker(item):
            gene = self.get_gene(item)
            if gene and gene.is_utr:
                return False, {}

        idx = self.installed_genes.index(item)
        if idx == 0:
            return False, {}  # Already at top

        # Don't allow moving past UTR gene at position 0
        prev_item = self.installed_genes[idx - 1]
        if not self.is_marker(prev_item):
            prev_gene = self.get_gene(prev_item)
            if prev_gene and prev_gene.is_utr:
                return False, {}  # Cannot move past UTR

        # Swap with previous item
        self.installed_genes[idx], self.installed_genes[idx - 1] = \
            self.installed_genes[idx - 1], self.installed_genes[idx]

        # Renumber markers after move
        rename_map = self.renumber_markers()
        return True, rename_map

    def move_item_down(self, item) -> tuple[bool, dict]:
        """Move an installed item (gene, ORF, or Terminator) down in the order.

        Returns (moved, rename_map) where rename_map contains any markers
        that were renamed due to renumbering after the move.
        """
        if item not in self.installed_genes:
            return False, {}

        # UTR genes cannot be moved - they must stay at position 0 (5' end)
        if not self.is_marker(item):
            gene = self.get_gene(item)
            if gene and gene.is_utr:
                return False, {}

        idx = self.installed_genes.index(item)
        if idx >= len(self.installed_genes) - 1:
            return False, {}  # Already at bottom

        # Swap with next item
        self.installed_genes[idx], self.installed_genes[idx + 1] = \
            self.installed_genes[idx + 1], self.installed_genes[idx]

        # Renumber markers after move
        rename_map = self.renumber_markers()
        return True, rename_map

    def get_orf_structure(self) -> list[dict]:
        """Get the ORF structure showing which genes belong to which ORF.

        ORFs now extend from their position to either:
        - The next Terminator in the list, OR
        - The end of the list if no Terminator follows

        This means ORFs can now overlap if there's no Terminator between them.

        Returns a list of dicts, each containing:
        - 'orf': The ORF name (e.g., "ORF-1")
        - 'genes': List of gene IDs under this ORF
        - 'start_idx': Index in installed_genes where this ORF starts
        - 'end_idx': Index where this ORF ends (at Terminator or end of list)

        Only includes ORFs that have at least one gene.
        """
        structure = []

        # Find all ORF positions
        orf_positions = []
        for idx, item in enumerate(self.installed_genes):
            if self.is_orf(item):
                orf_positions.append((idx, item))

        # For each ORF, find genes until next Terminator or end of list
        for orf_idx, orf_name in orf_positions:
            genes = []
            end_idx = len(self.installed_genes)

            # Collect genes from after this ORF until we hit a Terminator or end
            for idx in range(orf_idx + 1, len(self.installed_genes)):
                item = self.installed_genes[idx]
                if self.is_terminator(item):
                    end_idx = idx
                    break
                elif not self.is_orf(item):
                    # It's a gene - add it
                    genes.append(item)
                # If it's another ORF, we continue (ORFs can overlap)

            # Only include ORFs that have at least one gene
            if genes:
                structure.append({
                    'orf': orf_name,
                    'genes': genes,
                    'start_idx': orf_idx,
                    'end_idx': end_idx
                })

        return structure

    def get_orf_ghost_structure(self) -> list[dict]:
        """Get ORF structure ignoring all terminators (maximum possible extent).

        Used by the builder visualization to show ghost extensions when
        terminator_chance < 100. Returns the same format as get_orf_structure()
        but ORFs extend to the end of the installed_genes list.
        """
        structure = []

        orf_positions = []
        for idx, item in enumerate(self.installed_genes):
            if self.is_orf(item):
                orf_positions.append((idx, item))

        for orf_idx, orf_name in orf_positions:
            genes = []
            for idx in range(orf_idx + 1, len(self.installed_genes)):
                item = self.installed_genes[idx]
                if not self.is_orf(item) and not self.is_terminator(item):
                    genes.append(item)

            if genes:
                structure.append({
                    'orf': orf_name,
                    'genes': genes,
                    'start_idx': orf_idx,
                    'end_idx': len(self.installed_genes)
                })

        return structure

    def resolve_orf_translation(self, orf_start_idx: int) -> list[int]:
        """Resolve which genes an ORF translates, rolling for each terminator.

        Walks forward from the ORF position, collecting genes. When a terminator
        is encountered, rolls against terminator_chance to decide if it stops.
        Returns the list of gene IDs that are translated.
        """
        genes = []
        for idx in range(orf_start_idx + 1, len(self.installed_genes)):
            item = self.installed_genes[idx]
            if self.is_terminator(item):
                if random.randint(1, 100) <= self.terminator_chance:
                    break  # Terminator applies
                # else: readthrough - continue past it
            elif not self.is_orf(item):
                genes.append(item)
        return genes

    def get_installed_orf_count(self) -> int:
        """Get the number of ORFs currently installed."""
        return sum(1 for item in self.installed_genes if self.is_orf(item))

    def get_installed_terminator_count(self) -> int:
        """Get the number of Terminators currently installed."""
        return sum(1 for item in self.installed_genes if self.is_terminator(item))

    def get_lock_cost(self) -> int:
        """Get the cost to lock config. First lock is free, subsequent locks cost config_lock_cost."""
        if not self.virus_config.is_locked:
            return 0
        return self.config_lock_cost

    def can_lock_config(self) -> tuple[bool, str]:
        """Check if config can be locked in."""
        cost = self.get_lock_cost()
        if self.evolution_points < cost:
            return False, f"Not enough EP (need {cost}, have {self.evolution_points})"
        return True, "OK"

    def needs_config_lock(self) -> bool:
        """Check if config needs to be locked (first time or has pending changes)."""
        return not self.virus_config.is_locked or self.has_pending_changes()

    def lock_config(self) -> tuple[bool, str]:
        """Lock in the pending virus configuration."""
        can_lock, reason = self.can_lock_config()
        if not can_lock:
            return False, reason

        cost = self.get_lock_cost()

        # Pay the cost
        self.evolution_points -= cost

        # Apply pending config
        self.virus_config = self.pending_config.copy()
        self.virus_config.is_locked = True
        self.pending_config = self.virus_config.copy()

        if cost == 0:
            return True, "Configuration locked (free)"
        return True, f"Configuration locked for {cost} EP"

    def reset_pending_config(self):
        """Reset pending config to current locked config."""
        self.pending_config = self.virus_config.copy()

    def has_pending_changes(self) -> bool:
        """Check if there are unsaved config changes."""
        if self.pending_config is None:
            return False
        return (self.pending_config.nucleic_acid != self.virus_config.nucleic_acid or
                self.pending_config.strandedness != self.virus_config.strandedness or
                self.pending_config.polarity != self.virus_config.polarity or
                self.pending_config.virion_type != self.virus_config.virion_type)

    def get_total_genome_length(self) -> int:
        """Calculate total genome length from installed genes."""
        total = 0
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene:
                    total += gene.length
        return total

    def get_enabled_types(self) -> set:
        """Get all entity types enabled by installed genes.

        Returns a set of protein entity names that are enabled.
        """
        types = set()
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and gene.gene_type_entity_id is not None:
                    type_name = self.database.get_gene_type_name(gene)
                    if type_name != "None":
                        types.add(type_name)
        return types

    def get_enabled_protein_entity_ids(self) -> set:
        """Get all protein entity IDs enabled by installed genes."""
        ids = set()
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and gene.gene_type_entity_id is not None:
                    ids.add(gene.gene_type_entity_id)
        return ids

    def is_gene_genome_compatible(self, gene) -> bool:
        """Check if a gene's required genome type matches the locked genome type.

        Returns True if:
        - Gene has no required_genome_type (empty string)
        - Genome is locked and matches the gene's required type
        Returns False if:
        - Genome is not locked but gene requires a specific type
        - Genome is locked to a different type than the gene requires
        """
        if not gene.required_genome_type:
            return True  # No requirement, always compatible

        if not self.virus_config.is_locked:
            return False  # Gene requires specific type but genome not locked

        current_genome = self.virus_config.get_genome_string()
        return current_genome == gene.required_genome_type

    def get_genome_incompatible_genes(self) -> set:
        """Get set of installed gene IDs that are incompatible with current genome type."""
        incompatible = set()
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and not self.is_gene_genome_compatible(gene):
                    incompatible.add(gene.id)
        return incompatible

    def is_domain_gene_active_at(self, idx: int) -> bool:
        """Check if a domain gene at the given index in installed_genes is active.

        A domain gene is active if it is directly adjacent (index ± 1) to a gene
        whose gene_type_entity_id matches the domain gene's domain_entity_id.
        ORF/Terminator markers break adjacency.

        Non-domain genes (domain_entity_id is None) are always active.
        """
        item = self.installed_genes[idx]
        if self.is_marker(item):
            return True  # Markers are not genes

        gene = self.get_gene(item)
        if not gene or gene.domain_entity_id is None:
            return True  # Not a domain gene, always active

        # Check neighbor above (idx - 1)
        if idx > 0:
            neighbor = self.installed_genes[idx - 1]
            if not self.is_marker(neighbor):
                neighbor_gene = self.get_gene(neighbor)
                if neighbor_gene and neighbor_gene.gene_type_entity_id == gene.domain_entity_id:
                    return True

        # Check neighbor below (idx + 1)
        if idx < len(self.installed_genes) - 1:
            neighbor = self.installed_genes[idx + 1]
            if not self.is_marker(neighbor):
                neighbor_gene = self.get_gene(neighbor)
                if neighbor_gene and neighbor_gene.gene_type_entity_id == gene.domain_entity_id:
                    return True

        return False

    def get_inactive_domain_gene_positions(self) -> set:
        """Get set of indices in installed_genes where domain genes are inactive.

        Returns indices (not gene IDs) since the same gene ID could appear
        at multiple positions with different adjacency results.
        """
        inactive = set()
        for idx, item in enumerate(self.installed_genes):
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene and gene.domain_entity_id is not None:
                    if not self.is_domain_gene_active_at(idx):
                        inactive.add(idx)
        return inactive

    def can_entity_exist(self, entity_id: int) -> bool:
        """Check if an entity can exist based on enabled types.

        Non-protein entities can always exist.
        Protein entities can only exist if their type is enabled by genes.
        """
        entity = self.database.get_entity(entity_id)
        if entity is None:
            return False

        # Non-proteins can always exist
        if entity.category != "Protein":
            return True

        # Proteins can only exist if their type is enabled
        enabled_ids = self.get_enabled_protein_entity_ids()
        return entity_id in enabled_ids

    def _can_transition_happen(self, effect: Effect) -> bool:
        """Check if a Transition effect can happen based on enabled types."""
        # Check all inputs can exist
        for inp in effect.inputs:
            entity_id = inp.get('entity_id', 0)
            if not self.can_entity_exist(entity_id):
                return False

        # Check at least one output can exist
        has_valid_output = False
        for out in effect.outputs:
            # Unpack genome outputs are always valid
            if out.get('is_unpack_genome', False):
                has_valid_output = True
                break
            entity_id = out.get('entity_id', 0)
            if self.can_entity_exist(entity_id):
                has_valid_output = True
                break

        return has_valid_output

    def _can_modify_happen(self, effect: Effect, valid_effect_ids: set) -> bool:
        """Check if a Modify effect can happen."""
        # If targeting a specific effect ID, check if it's in valid effects
        if effect.target_effect_id is not None:
            return effect.target_effect_id in valid_effect_ids

        # If targeting by category, check if any valid effect has that category
        if effect.target_category:
            for eid in valid_effect_ids:
                target_effect = self.get_effect(eid)
                if target_effect and target_effect.category == effect.target_category:
                    return True
            return False

        # No target specified - effect can apply to anything
        return True

    def _can_change_location_happen(self, effect: Effect) -> bool:
        """Check if a Change location effect can happen."""
        if effect.affected_entity_id is None:
            return True  # Affects all entities
        return self.can_entity_exist(effect.affected_entity_id)

    def _can_translation_happen(self, effect: Effect) -> bool:
        """Check if a Translation effect can happen based on ORFs."""
        orf_structure = self.get_orf_structure()

        if not orf_structure:
            return False  # No ORFs with genes

        orf_targeting = effect.orf_targeting

        if orf_targeting == "Random ORF":
            # Need at least one ORF
            return len(orf_structure) > 0

        elif orf_targeting == "ORF-1 only":
            # Need ORF-1 specifically
            for orf_info in orf_structure:
                if orf_info['orf'] == "ORF-1":
                    return True
            return False

        elif orf_targeting == "Not ORF-1":
            # Need at least one ORF that is not ORF-1
            for orf_info in orf_structure:
                if orf_info['orf'] != "ORF-1":
                    return True
            return False

        return True  # Unknown targeting, allow by default

    def get_all_effects(self, filter_invalid: bool = True) -> list[Effect]:
        """Get all effects from installed genes (no duplicates).

        Args:
            filter_invalid: If True, only include effects that can actually happen
                           based on enabled types, ORFs, genome compatibility, etc.
        """
        effect_ids = set()
        for idx, item in enumerate(self.installed_genes):
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene:
                    # Skip effects from genes with incompatible genome type
                    if not self.is_gene_genome_compatible(gene):
                        continue
                    # Skip effects from inactive domain genes
                    if not self.is_domain_gene_active_at(idx):
                        continue
                    effect_ids.update(gene.effect_ids)

        if not filter_invalid:
            effects = []
            for eid in sorted(effect_ids):
                effect = self.get_effect(eid)
                if effect:
                    effects.append(effect)
            return effects

        # First pass: filter Transition, Change location, and Translation effects
        valid_effect_ids = set()
        pending_modify_effects = []

        for eid in effect_ids:
            effect = self.get_effect(eid)
            if not effect:
                continue

            if effect.effect_type == EffectType.TRANSITION.value:
                if self._can_transition_happen(effect):
                    valid_effect_ids.add(eid)

            elif effect.effect_type == EffectType.CHANGE_LOCATION.value:
                if self._can_change_location_happen(effect):
                    valid_effect_ids.add(eid)

            elif effect.effect_type == EffectType.TRANSLATION.value:
                if self._can_translation_happen(effect):
                    valid_effect_ids.add(eid)

            elif effect.effect_type == EffectType.MODIFY_EFFECT.value:
                # Defer modify effects to second pass
                pending_modify_effects.append(effect)

            else:
                # Unknown effect types are included by default
                valid_effect_ids.add(eid)

        # Second pass: filter Modify effects based on valid effects
        # Include global effect IDs so gene-based Modify effects can target global effects
        global_effect_ids = {e.id for e in self.database.get_global_effects()}
        all_targetable_ids = valid_effect_ids | global_effect_ids
        for effect in pending_modify_effects:
            if self._can_modify_happen(effect, all_targetable_ids):
                valid_effect_ids.add(effect.id)

        # Build final list
        effects = []
        for eid in sorted(valid_effect_ids):
            effect = self.get_effect(eid)
            if effect:
                effects.append(effect)
        return effects

    def get_global_effects(self, filter_invalid: bool = True) -> list[Effect]:
        """Get all global effects from database.

        Args:
            filter_invalid: If True, only include effects that can actually happen.
        """
        global_effects = self.database.get_global_effects()

        if not filter_invalid:
            return global_effects

        # Get the valid gene effects first (needed for modify effect filtering)
        gene_effect_ids = set()
        for item in self.installed_genes:
            if not self.is_marker(item):
                gene = self.get_gene(item)
                if gene:
                    gene_effect_ids.update(gene.effect_ids)

        # Build set of valid effect IDs from gene effects
        valid_gene_effect_ids = set()
        for eid in gene_effect_ids:
            effect = self.get_effect(eid)
            if not effect:
                continue
            if effect.effect_type == EffectType.TRANSITION.value:
                if self._can_transition_happen(effect):
                    valid_gene_effect_ids.add(eid)
            elif effect.effect_type == EffectType.CHANGE_LOCATION.value:
                if self._can_change_location_happen(effect):
                    valid_gene_effect_ids.add(eid)
            elif effect.effect_type == EffectType.TRANSLATION.value:
                if self._can_translation_happen(effect):
                    valid_gene_effect_ids.add(eid)

        # Filter global effects: two passes to handle Modify effects that may
        # target other global effects regardless of iteration order
        filtered = []
        pending_modify = []
        for effect in global_effects:
            if effect.effect_type == EffectType.TRANSITION.value:
                if self._can_transition_happen(effect):
                    filtered.append(effect)

            elif effect.effect_type == EffectType.CHANGE_LOCATION.value:
                if self._can_change_location_happen(effect):
                    filtered.append(effect)

            elif effect.effect_type == EffectType.TRANSLATION.value:
                if self._can_translation_happen(effect):
                    filtered.append(effect)

            elif effect.effect_type == EffectType.MODIFY_EFFECT.value:
                # Defer to second pass so all global targets are known
                pending_modify.append(effect)

            else:
                filtered.append(effect)

        # Second pass: check Modify effects against all valid targets
        all_valid_ids = valid_gene_effect_ids | {e.id for e in filtered}
        for effect in pending_modify:
            if self._can_modify_happen(effect, all_valid_ids):
                filtered.append(effect)

        return filtered

    def complete_play_round(self):
        """Called when a play round is completed. Advances to next round."""
        self.current_round += 1

        if self.current_round > self.max_rounds:
            self.game_over = True
            return

        # Offer new genes to choose from
        # This will be handled by the UI - just prepare the offering

    def add_ep(self, amount: int, reason: str = ""):
        """Add evolution points (from milestones, etc)."""
        self.evolution_points += amount

    def achieve_milestone(self, milestone_id: int) -> bool:
        """Mark a milestone as achieved and grant reward. Returns True if newly achieved."""
        if milestone_id in self.achieved_milestones:
            return False

        milestone = self.database.get_milestone(milestone_id)
        if not milestone:
            return False

        self.achieved_milestones.add(milestone_id)
        self.add_ep(milestone.reward_ep, f"Milestone: {milestone.name}")
        return True

    def check_win_condition(self, virion_count: int) -> bool:
        """Check if the player has won."""
        if virion_count >= self.win_threshold:
            self.game_won = True
            self.game_over = True
            return True
        return False
