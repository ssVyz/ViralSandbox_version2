"""
Database handler for Viral Sandbox.
Manages loading, saving, and manipulating game databases.
"""
import json
from pathlib import Path
from typing import Optional
from models import ViralEntity, Effect, Gene, Milestone, EntityCategory, CellLocation


# Default degradation chances per category per location (percentage per turn)
DEFAULT_DEGRADATION_CHANCES = {
    EntityCategory.VIRION.value: {
        CellLocation.EXTRACELLULAR.value: 2.0,
        CellLocation.MEMBRANE.value: 3.0,
        CellLocation.ENDOSOME.value: 5.0,
        CellLocation.ER.value: 4.0,
        CellLocation.CYTOSOL.value: 3.0,
        CellLocation.NUCLEUS.value: 2.0,
    },
    EntityCategory.VIRAL_COMPLEX.value: {
        CellLocation.EXTRACELLULAR.value: 5.0,
        CellLocation.MEMBRANE.value: 4.0,
        CellLocation.ENDOSOME.value: 6.0,
        CellLocation.ER.value: 5.0,
        CellLocation.CYTOSOL.value: 4.0,
        CellLocation.NUCLEUS.value: 3.0,
    },
    EntityCategory.DNA.value: {
        CellLocation.EXTRACELLULAR.value: 10.0,
        CellLocation.MEMBRANE.value: 8.0,
        CellLocation.ENDOSOME.value: 7.0,
        CellLocation.ER.value: 6.0,
        CellLocation.CYTOSOL.value: 5.0,
        CellLocation.NUCLEUS.value: 2.0,
    },
    EntityCategory.RNA.value: {
        CellLocation.EXTRACELLULAR.value: 15.0,
        CellLocation.MEMBRANE.value: 12.0,
        CellLocation.ENDOSOME.value: 10.0,
        CellLocation.ER.value: 8.0,
        CellLocation.CYTOSOL.value: 6.0,
        CellLocation.NUCLEUS.value: 4.0,
    },
    EntityCategory.PROTEIN.value: {
        CellLocation.EXTRACELLULAR.value: 8.0,
        CellLocation.MEMBRANE.value: 6.0,
        CellLocation.ENDOSOME.value: 7.0,
        CellLocation.ER.value: 5.0,
        CellLocation.CYTOSOL.value: 4.0,
        CellLocation.NUCLEUS.value: 3.0,
    },
}

# Default interferon modifiers per category (percentage at max interferon level)
# 100% means degradation chance doubles at max interferon (100)
DEFAULT_INTERFERON_MODIFIERS = {
    EntityCategory.VIRION.value: 50.0,
    EntityCategory.VIRAL_COMPLEX.value: 75.0,
    EntityCategory.DNA.value: 25.0,
    EntityCategory.RNA.value: 100.0,
    EntityCategory.PROTEIN.value: 50.0,
}

# Default interferon decay per turn (absolute value)
DEFAULT_INTERFERON_DECAY = 0.5


class GameDatabase:
    """Manages the game database containing entities, effects, genes, and milestones."""

    # Predefined entity IDs that cannot be deleted
    ENVELOPED_VIRION_ID = 1
    UNENVELOPED_VIRION_ID = 2
    POSITIVE_SENSE_RNA_ID = 3
    NEGATIVE_SENSE_RNA_ID = 4
    SSDNA_ID = 5
    DSDNA_ID = 6
    PROTECTED_ENTITY_IDS = {
        ENVELOPED_VIRION_ID, UNENVELOPED_VIRION_ID,
        POSITIVE_SENSE_RNA_ID, NEGATIVE_SENSE_RNA_ID,
        SSDNA_ID, DSDNA_ID
    }

    def __init__(self):
        self.entities: dict[int, ViralEntity] = {}
        self.effects: dict[int, Effect] = {}
        self.genes: dict[int, Gene] = {}
        self.milestones: dict[int, Milestone] = {}
        self.degradation_chances: dict[str, dict[str, float]] = {}
        self.interferon_modifiers: dict[str, float] = {}
        self.interferon_decay: float = DEFAULT_INTERFERON_DECAY
        self.filepath: Optional[Path] = None
        self.modified: bool = False

        # ID counters for new objects
        self._next_entity_id = 7  # Start after predefined entities (IDs 1-6)
        self._next_effect_id = 1
        self._next_gene_id = 1
        self._next_milestone_id = 1

    def _init_default_degradation(self):
        """Initialize degradation chances with default values."""
        import copy
        self.degradation_chances = copy.deepcopy(DEFAULT_DEGRADATION_CHANCES)

    def _init_default_interferon_modifiers(self):
        """Initialize interferon modifiers with default values."""
        import copy
        self.interferon_modifiers = copy.deepcopy(DEFAULT_INTERFERON_MODIFIERS)

    def _create_predefined_entities(self):
        """Create the predefined starter entities."""
        enveloped = ViralEntity(
            id=self.ENVELOPED_VIRION_ID,
            name="Enveloped virion",
            category="Virion",
            entity_type="None",
            description="A complete virus particle with a lipid envelope. This is a starter entity."
        )
        unenveloped = ViralEntity(
            id=self.UNENVELOPED_VIRION_ID,
            name="Unenveloped virion",
            category="Virion",
            entity_type="None",
            description="A naked virus particle without an envelope. This is a starter entity."
        )
        positive_rna = ViralEntity(
            id=self.POSITIVE_SENSE_RNA_ID,
            name="Positive-sense RNA",
            category="RNA",
            entity_type="None",
            description="Positive-sense single-stranded RNA genome. Can be directly translated into proteins."
        )
        negative_rna = ViralEntity(
            id=self.NEGATIVE_SENSE_RNA_ID,
            name="Negative-sense RNA",
            category="RNA",
            entity_type="None",
            description="Negative-sense single-stranded RNA genome. Must be transcribed before translation."
        )
        ssdna = ViralEntity(
            id=self.SSDNA_ID,
            name="ssDNA",
            category="DNA",
            entity_type="None",
            description="Single-stranded DNA genome."
        )
        dsdna = ViralEntity(
            id=self.DSDNA_ID,
            name="dsDNA",
            category="DNA",
            entity_type="None",
            description="Double-stranded DNA genome."
        )
        self.entities[self.ENVELOPED_VIRION_ID] = enveloped
        self.entities[self.UNENVELOPED_VIRION_ID] = unenveloped
        self.entities[self.POSITIVE_SENSE_RNA_ID] = positive_rna
        self.entities[self.NEGATIVE_SENSE_RNA_ID] = negative_rna
        self.entities[self.SSDNA_ID] = ssdna
        self.entities[self.DSDNA_ID] = dsdna

    def new_database(self):
        """Create a new database with predefined entities."""
        self.entities.clear()
        self.effects.clear()
        self.genes.clear()
        self.milestones.clear()
        self.filepath = None
        self.modified = False
        self._next_entity_id = 7  # Start after predefined entities (IDs 1-6)
        self._next_effect_id = 1
        self._next_gene_id = 1
        self._next_milestone_id = 1

        # Always create predefined entities
        self._create_predefined_entities()

        # Initialize default degradation chances, interferon modifiers, and decay
        self._init_default_degradation()
        self._init_default_interferon_modifiers()
        self.interferon_decay = DEFAULT_INTERFERON_DECAY

    def load(self, filepath: str) -> bool:
        """Load a database from a JSON file."""
        try:
            path = Path(filepath)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.new_database()
            self.filepath = path

            # Load entities
            for entity_data in data.get("entities", []):
                entity = ViralEntity.from_dict(entity_data)
                self.entities[entity.id] = entity
                self._next_entity_id = max(self._next_entity_id, entity.id + 1)

            # Load effects
            for effect_data in data.get("effects", []):
                effect = Effect.from_dict(effect_data)
                self.effects[effect.id] = effect
                self._next_effect_id = max(self._next_effect_id, effect.id + 1)

            # Load genes
            for gene_data in data.get("genes", []):
                gene = Gene.from_dict(gene_data)
                self.genes[gene.id] = gene
                self._next_gene_id = max(self._next_gene_id, gene.id + 1)

            # Load milestones
            for milestone_data in data.get("milestones", []):
                milestone = Milestone.from_dict(milestone_data)
                self.milestones[milestone.id] = milestone
                self._next_milestone_id = max(self._next_milestone_id, milestone.id + 1)

            # Ensure protein entities have correct entity_type (their own name)
            for entity in self.entities.values():
                if entity.category == "Protein":
                    entity.entity_type = entity.name

            # Validate gene types - clear any that reference invalid entities
            self.validate_gene_types()

            # Load degradation chances (or use defaults if not present)
            if "degradation_chances" in data:
                self.degradation_chances = data["degradation_chances"]
            # else: defaults were already set by new_database()

            # Load interferon modifiers (or use defaults if not present)
            if "interferon_modifiers" in data:
                self.interferon_modifiers = data["interferon_modifiers"]
            # else: defaults were already set by new_database()

            # Load interferon decay (or use default if not present)
            if "interferon_decay" in data:
                self.interferon_decay = data["interferon_decay"]
            # else: default was already set by new_database()

            self.modified = False
            return True

        except Exception as e:
            print(f"Error loading database: {e}")
            return False

    def save(self, filepath: Optional[str] = None) -> bool:
        """Save the database to a JSON file."""
        try:
            if filepath:
                path = Path(filepath)
            elif self.filepath:
                path = self.filepath
            else:
                return False

            data = {
                "entities": [e.to_dict() for e in self.entities.values()],
                "effects": [e.to_dict() for e in self.effects.values()],
                "genes": [g.to_dict() for g in self.genes.values()],
                "milestones": [m.to_dict() for m in self.milestones.values()],
                "degradation_chances": self.degradation_chances,
                "interferon_modifiers": self.interferon_modifiers,
                "interferon_decay": self.interferon_decay
            }

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            self.filepath = path
            self.modified = False
            return True

        except Exception as e:
            print(f"Error saving database: {e}")
            return False

    # Entity methods
    def add_entity(self, entity: ViralEntity) -> int:
        """Add an entity to the database. Returns the assigned ID."""
        if entity.id == 0:
            entity.id = self._next_entity_id
        # Always ensure next ID is greater than any added entity's ID
        if entity.id >= self._next_entity_id:
            self._next_entity_id = entity.id + 1

        # Auto-set entity_type for proteins to their own name
        if entity.category == "Protein":
            entity.entity_type = entity.name

        self.entities[entity.id] = entity
        self.modified = True
        return entity.id

    def update_entity(self, entity: ViralEntity):
        """Update an existing entity."""
        if entity.id in self.entities:
            old_entity = self.entities[entity.id]

            # Auto-set entity_type for proteins to their own name
            if entity.category == "Protein":
                entity.entity_type = entity.name
            else:
                entity.entity_type = "None"

            # If category changed FROM Protein to something else, clear gene types
            if old_entity.category == "Protein" and entity.category != "Protein":
                self._clear_gene_types_for_entity(entity.id)

            self.entities[entity.id] = entity
            self.modified = True

    def delete_entity(self, entity_id: int) -> bool:
        """Delete an entity from the database. Returns False if entity is protected."""
        if entity_id in self.PROTECTED_ENTITY_IDS:
            return False
        if entity_id in self.entities:
            entity = self.entities[entity_id]

            # If deleting a protein, clear any gene types referencing it
            if entity.category == "Protein":
                self._clear_gene_types_for_entity(entity_id)

            del self.entities[entity_id]
            self.modified = True
            return True
        return False

    def _clear_gene_types_for_entity(self, entity_id: int):
        """Clear gene_type_entity_id for all genes referencing the given entity."""
        for gene in self.genes.values():
            if gene.gene_type_entity_id == entity_id:
                gene.gene_type_entity_id = None

    def is_protected_entity(self, entity_id: int) -> bool:
        """Check if an entity is protected (cannot be deleted)."""
        return entity_id in self.PROTECTED_ENTITY_IDS

    def get_entity(self, entity_id: int) -> Optional[ViralEntity]:
        """Get an entity by ID."""
        return self.entities.get(entity_id)

    def get_next_entity_id(self) -> int:
        """Get the next available entity ID."""
        return self._next_entity_id

    # Effect methods
    def add_effect(self, effect: Effect) -> int:
        """Add an effect to the database. Returns the assigned ID."""
        if effect.id == 0:
            effect.id = self._next_effect_id
        # Always ensure next ID is greater than any added effect's ID
        if effect.id >= self._next_effect_id:
            self._next_effect_id = effect.id + 1
        self.effects[effect.id] = effect
        self.modified = True
        return effect.id

    def update_effect(self, effect: Effect):
        """Update an existing effect."""
        if effect.id in self.effects:
            self.effects[effect.id] = effect
            self.modified = True

    def delete_effect(self, effect_id: int):
        """Delete an effect from the database."""
        if effect_id in self.effects:
            del self.effects[effect_id]
            # Remove this effect from all genes
            for gene in self.genes.values():
                if effect_id in gene.effect_ids:
                    gene.effect_ids.remove(effect_id)
            self.modified = True

    def get_effect(self, effect_id: int) -> Optional[Effect]:
        """Get an effect by ID."""
        return self.effects.get(effect_id)

    def get_next_effect_id(self) -> int:
        """Get the next available effect ID."""
        return self._next_effect_id

    # Gene methods
    def add_gene(self, gene: Gene) -> int:
        """Add a gene to the database. Returns the assigned ID."""
        if gene.id == 0:
            gene.id = self._next_gene_id
        # Always ensure next ID is greater than any added gene's ID
        if gene.id >= self._next_gene_id:
            self._next_gene_id = gene.id + 1
        self.genes[gene.id] = gene
        self.modified = True
        return gene.id

    def update_gene(self, gene: Gene):
        """Update an existing gene."""
        if gene.id in self.genes:
            self.genes[gene.id] = gene
            self.modified = True

    def delete_gene(self, gene_id: int):
        """Delete a gene from the database."""
        if gene_id in self.genes:
            del self.genes[gene_id]
            self.modified = True

    def get_gene(self, gene_id: int) -> Optional[Gene]:
        """Get a gene by ID."""
        return self.genes.get(gene_id)

    def get_next_gene_id(self) -> int:
        """Get the next available gene ID."""
        return self._next_gene_id

    # Milestone methods
    def add_milestone(self, milestone: Milestone) -> int:
        """Add a milestone to the database. Returns the assigned ID."""
        if milestone.id == 0:
            milestone.id = self._next_milestone_id
        # Always ensure next ID is greater than any added milestone's ID
        if milestone.id >= self._next_milestone_id:
            self._next_milestone_id = milestone.id + 1
        self.milestones[milestone.id] = milestone
        self.modified = True
        return milestone.id

    def update_milestone(self, milestone: Milestone):
        """Update an existing milestone."""
        if milestone.id in self.milestones:
            self.milestones[milestone.id] = milestone
            self.modified = True

    def delete_milestone(self, milestone_id: int):
        """Delete a milestone from the database."""
        if milestone_id in self.milestones:
            del self.milestones[milestone_id]
            self.modified = True

    def get_milestone(self, milestone_id: int) -> Optional[Milestone]:
        """Get a milestone by ID."""
        return self.milestones.get(milestone_id)

    def get_next_milestone_id(self) -> int:
        """Get the next available milestone ID."""
        return self._next_milestone_id

    # Utility methods
    def get_effects_for_gene(self, gene_id: int) -> list[Effect]:
        """Get all effects attached to a gene."""
        gene = self.get_gene(gene_id)
        if not gene:
            return []
        return [self.effects[eid] for eid in gene.effect_ids if eid in self.effects]

    def get_genes_with_effect(self, effect_id: int) -> list[Gene]:
        """Get all genes that have a specific effect."""
        return [g for g in self.genes.values() if effect_id in g.effect_ids]

    def get_global_effects(self) -> list[Effect]:
        """Get all global effects."""
        return [e for e in self.effects.values() if e.is_global]

    def get_protein_entities(self) -> list[ViralEntity]:
        """Get all entities with category 'Protein'. These serve as available types for genes."""
        return [e for e in self.entities.values() if e.category == "Protein"]

    def get_gene_type_name(self, gene: Gene) -> str:
        """Get the display name for a gene's type."""
        if gene.gene_type_entity_id is None:
            return "None"
        entity = self.get_entity(gene.gene_type_entity_id)
        if entity and entity.category == "Protein":
            return entity.name
        return "None"

    def validate_gene_types(self):
        """Validate all gene types and clear any that reference non-existent or non-protein entities."""
        for gene in self.genes.values():
            if gene.gene_type_entity_id is not None:
                entity = self.get_entity(gene.gene_type_entity_id)
                if entity is None or entity.category != "Protein":
                    gene.gene_type_entity_id = None
                    self.modified = True

    # Degradation chance methods
    def get_degradation_chance(self, category: str, location: str) -> float:
        """Get the degradation chance for a category at a location."""
        if category in self.degradation_chances:
            return self.degradation_chances[category].get(location, 5.0)
        return 5.0  # Default fallback

    def set_degradation_chance(self, category: str, location: str, chance: float):
        """Set the degradation chance for a category at a location."""
        if category not in self.degradation_chances:
            self.degradation_chances[category] = {}
        self.degradation_chances[category][location] = chance
        self.modified = True

    def reset_degradation_to_defaults(self):
        """Reset all degradation chances to default values."""
        self._init_default_degradation()
        self.modified = True

    # Interferon modifier methods
    def get_interferon_modifier(self, category: str) -> float:
        """Get the interferon modifier for a category (% increase at max interferon)."""
        return self.interferon_modifiers.get(category, 50.0)

    def set_interferon_modifier(self, category: str, modifier: float):
        """Set the interferon modifier for a category."""
        self.interferon_modifiers[category] = modifier
        self.modified = True

    def reset_interferon_modifiers_to_defaults(self):
        """Reset all interferon modifiers to default values."""
        self._init_default_interferon_modifiers()
        self.modified = True

    # Interferon decay methods
    def get_interferon_decay(self) -> float:
        """Get the interferon decay rate per turn."""
        return self.interferon_decay

    def set_interferon_decay(self, decay: float):
        """Set the interferon decay rate per turn."""
        self.interferon_decay = decay
        self.modified = True

    def reset_interferon_decay_to_default(self):
        """Reset interferon decay to default value."""
        self.interferon_decay = DEFAULT_INTERFERON_DECAY
        self.modified = True
