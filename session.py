"""
Game session flow for Viral Sandbox.

Owns the lifecycle of a single playthrough: starting a game, advancing through
play rounds, offering new genes between rounds, and ending. This module has no
UI dependency and must never import tkinter - the caller decides how to present
each outcome.

Typical use::

    session = GameSession(starting_hand_size=7)
    if session.start("default_database.json") is StartResult.OK:
        ...
        outcome = session.finish_round(victory=False)
        if outcome is RoundOutcome.CONTINUE:
            offered = session.draw_gene_offer()
            session.accept_gene(offered[0])
"""
import random
from enum import Enum
from typing import Optional

from database import GameDatabase
from game_state import GameState


class StartResult(Enum):
    """Why a game could or could not be started."""
    OK = "ok"
    LOAD_FAILED = "load_failed"
    NO_GENES = "no_genes"
    NOT_ENOUGH_GENES = "not_enough_genes"


class RoundOutcome(Enum):
    """What happened when a play round finished."""
    CONTINUE = "continue"            # back to the builder for another round
    VICTORY = "victory"              # the virus achieved a runaway reaction
    OUT_OF_ROUNDS = "out_of_rounds"  # all play rounds used up


class GameSession:
    """A single playthrough: the database in use, the game state, and the
    round loop that moves between them.

    Holds no widgets and shows no dialogs; every method returns a result for
    the caller to present.
    """

    def __init__(self, starting_ep: int = 100, starting_hand_size: int = 7, rng=None):
        self.starting_ep = starting_ep
        self.starting_hand_size = starting_hand_size
        # Defaults to the ``random`` module so behaviour matches the original
        # in-menu flow exactly; pass a ``random.Random(seed)`` to make gene
        # offers reproducible in tests.
        self.rng = rng if rng is not None else random

        self.database: Optional[GameDatabase] = None
        self.game_state: Optional[GameState] = None

    @property
    def is_active(self) -> bool:
        """True while a game is in progress."""
        return self.game_state is not None

    def start(self, filepath: str) -> StartResult:
        """Load ``filepath`` and begin a new game.

        The session is only modified on success, so a failed start leaves any
        previous game untouched.
        """
        database = GameDatabase()
        if not database.load(filepath):
            return StartResult.LOAD_FAILED

        if not database.genes:
            return StartResult.NO_GENES

        game_state = GameState.new_game(
            database=database,
            starting_ep=self.starting_ep,
            starting_hand_size=self.starting_hand_size,
        )

        if not game_state.available_genes:
            return StartResult.NOT_ENOUGH_GENES

        self.database = database
        self.game_state = game_state
        return StartResult.OK

    def finish_round(self, victory: bool = False) -> RoundOutcome:
        """Record the end of a play round and report what happens next."""
        if victory:
            return RoundOutcome.VICTORY

        self.game_state.complete_play_round()

        if self.game_state.game_over:
            return RoundOutcome.OUT_OF_ROUNDS

        return RoundOutcome.CONTINUE

    def draw_gene_offer(self) -> list:
        """Pick the genes to offer the player after a round.

        Returns an empty list when every gene is already in hand or installed.
        """
        all_gene_ids = list(self.game_state.database.genes.keys())

        available_ids = [gid for gid in all_gene_ids
                         if gid not in self.game_state.available_genes
                         and gid not in self.game_state.installed_genes]

        if not available_ids:
            return []

        offer_count = min(self.game_state.genes_offered_per_round, len(available_ids))
        return self.rng.sample(available_ids, offer_count)

    def accept_gene(self, gene_id: int) -> None:
        """Add an offered gene to the player's hand."""
        self.game_state.available_genes.append(gene_id)

    def end(self) -> None:
        """Discard the current game."""
        self.game_state = None
        self.database = None
