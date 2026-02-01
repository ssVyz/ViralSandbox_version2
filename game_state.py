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
    polarity: str = "positive"  # "positive", "negative", or "ambisense" (for single-stranded)

    # Virion type
    virion_type: str = "Enveloped"  # "Enveloped" or "Unenveloped"

    # Translation mode
    translation_mode: str = "Standard"  # Can be customized

    # Whether config has been locked in
    is_locked: bool = False

    def get_genome_string(self) -> str:
        """Get a human-readable genome description."""
        if self.strandedness == "double":
            return f"ds{self.nucleic_acid}"
        else:
            polarity_symbol = "+" if self.polarity == "positive" else "-" if self.polarity == "negative" else "+/-"
            return f"({polarity_symbol})ss{self.nucleic_acid}"

    def copy(self) -> "VirusConfig":
        """Create a copy of this config."""
        return VirusConfig(
            nucleic_acid=self.nucleic_acid,
            strandedness=self.strandedness,
            polarity=self.polarity,
            virion_type=self.virion_type,
            translation_mode=self.translation_mode,
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
    installed_genes: list = field(default_factory=list)  # Gene IDs installed

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
                self.pending_config.virion_type != self.virus_config.virion_type or
                self.pending_config.translation_mode != self.virus_config.translation_mode)

    def get_total_genome_length(self) -> int:
        """Calculate total genome length from installed genes."""
        total = 0
        for gene_id in self.installed_genes:
            gene = self.get_gene(gene_id)
            if gene:
                total += gene.length
        return total

    def get_enabled_types(self) -> set:
        """Get all entity types enabled by installed genes."""
        types = set()
        for gene_id in self.installed_genes:
            gene = self.get_gene(gene_id)
            if gene and gene.gene_type != "None":
                types.add(gene.gene_type)
        return types

    def get_all_effects(self) -> list[Effect]:
        """Get all effects from installed genes (no duplicates)."""
        effect_ids = set()
        for gene_id in self.installed_genes:
            gene = self.get_gene(gene_id)
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
