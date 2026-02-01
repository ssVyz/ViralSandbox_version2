"""
Data models for Viral Sandbox game.
Contains dataclasses for all game entities.
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class EntityCategory(Enum):
    VIRION = "Virion"
    VIRAL_COMPLEX = "Viral complex"
    DNA = "DNA"
    RNA = "RNA"
    PROTEIN = "Protein"


class CellLocation(Enum):
    EXTRACELLULAR = "Extracellular"
    MEMBRANE = "Membrane"
    ENDOSOME = "Endosome"
    GOLGI = "Golgi"
    CYTOSOL = "Cytosol"
    NUCLEUS = "Nucleus"


class EffectType(Enum):
    TRANSITION = "Transition"
    MODIFY_TRANSITION = "Modify transition"
    CHANGE_LOCATION = "Change location"
    TRANSLATION = "Translation"


class OrfTargeting(Enum):
    """ORF targeting options for Translation effects."""
    RANDOM = "Random ORF"
    ORF1_ONLY = "ORF-1 only"
    NOT_ORF1 = "Not ORF-1"


class MilestoneType(Enum):
    ENTER_COMPARTMENT = "Enter compartment"
    PRODUCE_FIRST_ENTITY = "Produce first entity"
    PRODUCE_ENTITY_COUNT = "Produce entity count"
    SURVIVE_TURNS = "Survive turns"


@dataclass
class EntityInput:
    """Input entity for a transition effect."""
    entity_id: int
    amount: int
    location: str
    consumed: bool = True


@dataclass
class EntityOutput:
    """Output entity for a transition effect."""
    entity_id: int
    amount: int
    location: str
    is_unpack_genome: bool = False  # If True, spawns the genome entity instead of entity_id


@dataclass
class ViralEntity:
    """A viral entity in the database."""
    id: int
    name: str
    category: str  # EntityCategory value
    entity_type: str = "None"  # EntityType value
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "entity_type": self.entity_type,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ViralEntity":
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            entity_type=data.get("entity_type", "None"),
            description=data.get("description", "")
        )


@dataclass
class Effect:
    """An effect that can be attached to genes."""
    id: int
    name: str
    effect_type: str  # EffectType value
    category: str = ""  # Optional category for grouping
    description: str = ""
    is_global: bool = False  # Global effects always apply

    # For Transition effects
    inputs: list = field(default_factory=list)  # List of EntityInput dicts
    outputs: list = field(default_factory=list)  # List of EntityOutput dicts (can include unpack_genome outputs)
    chance: float = 100.0  # Percentage 0-100
    interferon_production: float = 0.0
    antibody_response: float = 0.0
    requires_genome_type: str = ""  # For polymerase activity

    # For Modify transition effects
    target_effect_id: Optional[int] = None
    target_category: str = ""  # Can target by category string
    chance_modifier: float = 0.0
    interferon_modifier: float = 0.0
    antibody_modifier: float = 0.0

    # For Change location effects
    source_location: str = ""
    target_location: str = ""
    affected_entity_id: Optional[int] = None
    location_change_chance: float = 100.0

    # For Translation effects
    templates: list = field(default_factory=list)  # List of template dicts (RNA entities, location)
    translation_chance: float = 100.0  # Percentage 0-100
    orf_targeting: str = "Random ORF"  # OrfTargeting value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "effect_type": self.effect_type,
            "category": self.category,
            "description": self.description,
            "is_global": self.is_global,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "chance": self.chance,
            "interferon_production": self.interferon_production,
            "antibody_response": self.antibody_response,
            "requires_genome_type": self.requires_genome_type,
            "target_effect_id": self.target_effect_id,
            "target_category": self.target_category,
            "chance_modifier": self.chance_modifier,
            "interferon_modifier": self.interferon_modifier,
            "antibody_modifier": self.antibody_modifier,
            "source_location": self.source_location,
            "target_location": self.target_location,
            "affected_entity_id": self.affected_entity_id,
            "location_change_chance": self.location_change_chance,
            "templates": self.templates,
            "translation_chance": self.translation_chance,
            "orf_targeting": self.orf_targeting
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Effect":
        return cls(
            id=data["id"],
            name=data["name"],
            effect_type=data["effect_type"],
            category=data.get("category", ""),
            description=data.get("description", ""),
            is_global=data.get("is_global", False),
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            chance=data.get("chance", 100.0),
            interferon_production=data.get("interferon_production", 0.0),
            antibody_response=data.get("antibody_response", 0.0),
            requires_genome_type=data.get("requires_genome_type", ""),
            target_effect_id=data.get("target_effect_id"),
            target_category=data.get("target_category", ""),
            chance_modifier=data.get("chance_modifier", 0.0),
            interferon_modifier=data.get("interferon_modifier", 0.0),
            antibody_modifier=data.get("antibody_modifier", 0.0),
            source_location=data.get("source_location", ""),
            target_location=data.get("target_location", ""),
            affected_entity_id=data.get("affected_entity_id"),
            location_change_chance=data.get("location_change_chance", 100.0),
            templates=data.get("templates", []),
            translation_chance=data.get("translation_chance", 100.0),
            orf_targeting=data.get("orf_targeting", "Random ORF")
        )


@dataclass
class Gene:
    """A gene that can be installed in a virus."""
    id: int
    name: str
    set_name: str  # e.g., "HIV", "RSV", "EV"
    install_cost: int  # EP cost
    length: int  # in bp, should be multiple of 3
    gene_type_entity_id: Optional[int] = None  # Entity ID of protein type this gene enables, None for "None"
    effect_ids: list = field(default_factory=list)  # List of effect IDs
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "set_name": self.set_name,
            "install_cost": self.install_cost,
            "length": self.length,
            "gene_type_entity_id": self.gene_type_entity_id,
            "effect_ids": self.effect_ids,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Gene":
        # Handle migration from old gene_type string to new gene_type_entity_id
        gene_type_entity_id = data.get("gene_type_entity_id")
        if gene_type_entity_id is None:
            # Check for old format - ignore old string types, they'll be None now
            old_gene_type = data.get("gene_type", "None")
            if old_gene_type != "None":
                # Old format had string types - these won't map to entities, so set to None
                gene_type_entity_id = None

        return cls(
            id=data["id"],
            name=data["name"],
            set_name=data["set_name"],
            install_cost=data["install_cost"],
            length=data["length"],
            gene_type_entity_id=gene_type_entity_id,
            effect_ids=data.get("effect_ids", []),
            description=data.get("description", "")
        )


@dataclass
class Milestone:
    """A milestone that can be achieved during play."""
    id: int
    name: str
    milestone_type: str  # MilestoneType value
    reward_ep: int  # Evolution points reward
    description: str = ""

    # Type-specific parameters
    target_compartment: str = ""  # For ENTER_COMPARTMENT
    target_entity_category: str = ""  # For PRODUCE_FIRST_ENTITY, PRODUCE_ENTITY_COUNT
    target_count: int = 0  # For PRODUCE_ENTITY_COUNT
    target_turns: int = 0  # For SURVIVE_TURNS

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "milestone_type": self.milestone_type,
            "reward_ep": self.reward_ep,
            "description": self.description,
            "target_compartment": self.target_compartment,
            "target_entity_category": self.target_entity_category,
            "target_count": self.target_count,
            "target_turns": self.target_turns
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Milestone":
        return cls(
            id=data["id"],
            name=data["name"],
            milestone_type=data["milestone_type"],
            reward_ep=data["reward_ep"],
            description=data.get("description", ""),
            target_compartment=data.get("target_compartment", ""),
            target_entity_category=data.get("target_entity_category", ""),
            target_count=data.get("target_count", 0),
            target_turns=data.get("target_turns", 0)
        )
