"""
Database handler for Viral Sandbox.
Manages loading, saving, and manipulating game databases.
"""
import json
from pathlib import Path
from typing import Optional
from models import ViralEntity, Effect, Gene, Milestone


class GameDatabase:
    """Manages the game database containing entities, effects, genes, and milestones."""

    # Predefined entity IDs that cannot be deleted
    ENVELOPED_VIRION_ID = 1
    UNENVELOPED_VIRION_ID = 2
    PROTECTED_ENTITY_IDS = {ENVELOPED_VIRION_ID, UNENVELOPED_VIRION_ID}

    def __init__(self):
        self.entities: dict[int, ViralEntity] = {}
        self.effects: dict[int, Effect] = {}
        self.genes: dict[int, Gene] = {}
        self.milestones: dict[int, Milestone] = {}
        self.filepath: Optional[Path] = None
        self.modified: bool = False

        # ID counters for new objects
        self._next_entity_id = 3  # Start after predefined entities
        self._next_effect_id = 1
        self._next_gene_id = 1
        self._next_milestone_id = 1

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
        self.entities[self.ENVELOPED_VIRION_ID] = enveloped
        self.entities[self.UNENVELOPED_VIRION_ID] = unenveloped

    def new_database(self):
        """Create a new database with predefined entities."""
        self.entities.clear()
        self.effects.clear()
        self.genes.clear()
        self.milestones.clear()
        self.filepath = None
        self.modified = False
        self._next_entity_id = 3  # Start after predefined entities
        self._next_effect_id = 1
        self._next_gene_id = 1
        self._next_milestone_id = 1

        # Always create predefined entities
        self._create_predefined_entities()

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
                "milestones": [m.to_dict() for m in self.milestones.values()]
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
            self._next_entity_id += 1
        self.entities[entity.id] = entity
        self.modified = True
        return entity.id

    def update_entity(self, entity: ViralEntity):
        """Update an existing entity."""
        if entity.id in self.entities:
            self.entities[entity.id] = entity
            self.modified = True

    def delete_entity(self, entity_id: int) -> bool:
        """Delete an entity from the database. Returns False if entity is protected."""
        if entity_id in self.PROTECTED_ENTITY_IDS:
            return False
        if entity_id in self.entities:
            del self.entities[entity_id]
            self.modified = True
            return True
        return False

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
            self._next_effect_id += 1
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
            self._next_gene_id += 1
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
            self._next_milestone_id += 1
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
