"""
Game state manager for Viral Sandbox.
Tracks the current game session state.
"""
import random
from dataclasses import dataclass, field
from typing import Optional
from database import GameDatabase
from models import Gene, Effect


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

        idx = self.installed_genes.index(gene_id)
        if idx == 0:
            return False  # Already at top

        # Swap with previous gene
        self.installed_genes[idx], self.installed_genes[idx - 1] = \
            self.installed_genes[idx - 1], self.installed_genes[idx]
        return True

    def move_gene_down(self, gene_id: int) -> bool:
        """Move an installed gene down in the order. Returns True if moved."""
        if gene_id not in self.installed_genes:
            return False

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

        # Generate ORF name
        self._orf_counter += 1
        self._total_orfs_installed += 1
        orf_name = f"ORF-{self._orf_counter}"

        # Add to installed list
        self.installed_genes.append(orf_name)

        if cost == 0:
            return True, f"Added {orf_name} (free)"
        return True, f"Added {orf_name} for {cost} EP"

    def remove_orf(self, orf_name: str) -> tuple[bool, str]:
        """Remove an ORF from installed genes. No cost refund."""
        if not self.is_orf(orf_name):
            return False, "Not a valid ORF"

        if orf_name not in self.installed_genes:
            return False, "ORF not installed"

        self.installed_genes.remove(orf_name)
        return True, f"Removed {orf_name}"

    def move_item_up(self, item) -> bool:
        """Move an installed item (gene or ORF) up in the order."""
        if item not in self.installed_genes:
            return False

        idx = self.installed_genes.index(item)
        if idx == 0:
            return False  # Already at top

        # Swap with previous item
        self.installed_genes[idx], self.installed_genes[idx - 1] = \
            self.installed_genes[idx - 1], self.installed_genes[idx]
        return True

    def move_item_down(self, item) -> bool:
        """Move an installed item (gene or ORF) down in the order."""
        if item not in self.installed_genes:
            return False

        idx = self.installed_genes.index(item)
        if idx >= len(self.installed_genes) - 1:
            return False  # Already at bottom

        # Swap with next item
        self.installed_genes[idx], self.installed_genes[idx + 1] = \
            self.installed_genes[idx + 1], self.installed_genes[idx]
        return True

    def get_orf_structure(self) -> list[dict]:
        """Get the ORF structure showing which genes belong to which ORF.

        Returns a list of dicts, each containing:
        - 'orf': The ORF name (e.g., "ORF-1")
        - 'genes': List of gene IDs under this ORF
        - 'start_idx': Index in installed_genes where this ORF starts
        - 'end_idx': Index where the next ORF starts (or end of list)

        Only includes ORFs that have at least one gene.
        """
        structure = []
        current_orf = None
        current_genes = []
        start_idx = 0

        for idx, item in enumerate(self.installed_genes):
            if self.is_orf(item):
                # Save previous ORF if it has genes
                if current_orf is not None and current_genes:
                    structure.append({
                        'orf': current_orf,
                        'genes': current_genes,
                        'start_idx': start_idx,
                        'end_idx': idx
                    })
                # Start new ORF
                current_orf = item
                current_genes = []
                start_idx = idx
            else:
                # It's a gene
                if current_orf is not None:
                    current_genes.append(item)

        # Don't forget the last ORF
        if current_orf is not None and current_genes:
            structure.append({
                'orf': current_orf,
                'genes': current_genes,
                'start_idx': start_idx,
                'end_idx': len(self.installed_genes)
            })

        return structure

    def get_installed_orf_count(self) -> int:
        """Get the number of ORFs currently installed."""
        return sum(1 for item in self.installed_genes if self.is_orf(item))

    def can_lock_config(self) -> tuple[bool, str]:
        """Check if config can be locked in."""
        if self.evolution_points < self.config_lock_cost:
            return False, f"Not enough EP (need {self.config_lock_cost}, have {self.evolution_points})"
        return True, "OK"

    def lock_config(self) -> tuple[bool, str]:
        """Lock in the pending virus configuration."""
        can_lock, reason = self.can_lock_config()
        if not can_lock:
            return False, reason

        # Pay the cost
        self.evolution_points -= self.config_lock_cost

        # Apply pending config
        self.virus_config = self.pending_config.copy()
        self.virus_config.is_locked = True
        self.pending_config = self.virus_config.copy()

        return True, f"Configuration locked for {self.config_lock_cost} EP"

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
            if not self.is_orf(item):
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
            if not self.is_orf(item):
                gene = self.get_gene(item)
                if gene and gene.gene_type_entity_id is not None:
                    type_name = self.database.get_gene_type_name(gene)
                    if type_name != "None":
                        types.add(type_name)
        return types

    def get_all_effects(self) -> list[Effect]:
        """Get all effects from installed genes (no duplicates)."""
        effect_ids = set()
        for item in self.installed_genes:
            if not self.is_orf(item):
                gene = self.get_gene(item)
                if gene:
                    effect_ids.update(gene.effect_ids)

        effects = []
        for eid in sorted(effect_ids):
            effect = self.get_effect(eid)
            if effect:
                effects.append(effect)
        return effects

    def get_global_effects(self) -> list[Effect]:
        """Get all global effects from database."""
        return self.database.get_global_effects()

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
