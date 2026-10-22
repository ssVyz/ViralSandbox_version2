"""
Game session flow for Viral Sandbox.

Owns the lifecycle of a single playthrough as a small state machine
(:class:`GamePhase`): start a game, build, play a round, take a gene offer,
and repeat until victory or the last round. This module has no UI dependency
and must never import tkinter. UIs reach it through game_api.GameAPI.

Typical use::

    session = GameSession(starting_hand_size=7)
    if session.start("default_database.json") is StartResult.OK:
        ...                                   # BUILDING: edit the genome
        engine = session.start_round()        # PLAYING
        engine.run_until_end()
        outcome = session.finish_round()
        if session.phase is GamePhase.GENE_OFFER:
            session.accept_gene(session.offer[0])   # back to BUILDING
"""
import random
from enum import Enum
from typing import Optional

from database import GameDatabase
from game_state import GameState, RoundReadiness, DEFAULT_STARTING_EP
from simulation import SimulationEngine


class GamePhase(Enum):
    """Where a playthrough is. Each phase allows a fixed set of calls."""
    NO_GAME = "no_game"        # start()
    BUILDING = "building"      # edit the genome, start_round()
    PLAYING = "playing"        # a round is running, finish_round()
    GENE_OFFER = "gene_offer"  # accept_gene() or decline_offer()
    GAME_OVER = "game_over"    # victory or out of rounds, end()


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


class GameFlowError(RuntimeError):
    """A call was made in a phase that does not allow it.

    This signals a bug in the caller, not a player mistake: player-facing
    problems are reported through return values instead.
    """


class GameSession:
    """A single playthrough: the database in use, the game state, the round in
    progress and the gene offer between rounds.

    Holds no widgets and shows no dialogs; every method returns a result for
    the caller to present.
    """

    def __init__(self, starting_ep: int = DEFAULT_STARTING_EP,
                 starting_hand_size: int = 7, rng=None):
        self.starting_ep = starting_ep
        self.starting_hand_size = starting_hand_size
        # Defaults to the ``random`` module so behaviour matches the original
        # in-menu flow exactly; pass a ``random.Random(seed)`` to make gene
        # offers and simulations reproducible in tests.
        self.rng = rng if rng is not None else random

        self.phase = GamePhase.NO_GAME
        self.database: Optional[GameDatabase] = None
        self.game_state: Optional[GameState] = None
        self.engine: Optional[SimulationEngine] = None  # the round in progress
        self.offer: list = []                           # gene IDs offered after a round

    @property
    def is_active(self) -> bool:
        """True while a game is in progress (including GAME_OVER until end())."""
        return self.game_state is not None

    def _require(self, *phases: GamePhase):
        if self.phase not in phases:
            allowed = " or ".join(p.name for p in phases)
            raise GameFlowError(f"not allowed in phase {self.phase.name} (needs {allowed})")

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
        self.engine = None
        self.offer = []
        self.phase = GamePhase.BUILDING
        return StartResult.OK

    def start_round(self) -> SimulationEngine:
        """Begin a play round with the current virus.

        Raises GameFlowError unless the phase is BUILDING and
        ``game_state.round_readiness()`` is READY.
        """
        self._require(GamePhase.BUILDING)
        readiness = self.game_state.round_readiness()
        if readiness is not RoundReadiness.READY:
            raise GameFlowError(f"round cannot start: {readiness.value}")

        self.engine = SimulationEngine(self.game_state, rng=self.rng)
        self.phase = GamePhase.PLAYING
        return self.engine

    def finish_round(self) -> RoundOutcome:
        """End the round in progress and report what happens next.

        The outcome is read from the simulation itself; a round still running
        is ended early first. On CONTINUE the next gene offer is drawn: the
        phase becomes GENE_OFFER, or BUILDING if no genes are left to offer.
        """
        self._require(GamePhase.PLAYING)
        engine = self.engine
        engine.end_early()
        self.engine = None

        if engine.sim_state.is_victory:
            self.game_state.game_won = True
            self.game_state.game_over = True
            self.phase = GamePhase.GAME_OVER
            return RoundOutcome.VICTORY

        self.game_state.complete_play_round()

        if self.game_state.game_over:
            self.phase = GamePhase.GAME_OVER
            return RoundOutcome.OUT_OF_ROUNDS

        self.offer = self.draw_gene_offer()
        self.phase = GamePhase.GENE_OFFER if self.offer else GamePhase.BUILDING
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
        """Add an offered gene to the player's hand and return to building."""
        self._require(GamePhase.GENE_OFFER)
        if gene_id not in self.offer:
            raise ValueError(f"gene {gene_id} was not offered")
        self.game_state.available_genes.append(gene_id)
        self.offer = []
        self.phase = GamePhase.BUILDING

    def decline_offer(self) -> None:
        """Take none of the offered genes and return to building."""
        self._require(GamePhase.GENE_OFFER)
        self.offer = []
        self.phase = GamePhase.BUILDING

    def end(self) -> None:
        """Discard the current game."""
        self.game_state = None
        self.database = None
        self.engine = None
        self.offer = []
        self.phase = GamePhase.NO_GAME
