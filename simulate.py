"""Headless simulation runner for Viral Sandbox.

Runs the game's simulation without opening a window, for balance testing:

    uv run simulate.py --runs 20
    uv run simulate.py --seed 7 --verbose

This exists because the rules live in simulation.py rather than inside the
play window, so they can be driven from a script.
"""
import argparse
import os
import random
import statistics
import sys

from database import GameDatabase
from game_state import GameState
from simulation import SimulationEngine

ROOT = os.path.dirname(os.path.abspath(__file__))


def build_virus(database, seed, ep, hand):
    """Configure a virus by installing every gene it can afford."""
    random.seed(seed)
    gs = GameState.new_game(database=database, starting_ep=ep, starting_hand_size=hand)
    gs.install_orf()
    for gid in sorted(gs.available_genes):
        can, _ = gs.can_install_gene(gid)
        if can:
            gs.install_gene(gid)
    gs.install_orf()
    if gs.needs_config_lock():
        gs.lock_config()
    return gs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database", default=os.path.join(ROOT, "default_database.json"))
    ap.add_argument("--runs", type=int, default=5, help="number of simulations")
    ap.add_argument("--seed", type=int, default=0, help="base random seed")
    ap.add_argument("--max-turns", type=int, default=500)
    ap.add_argument("--ep", type=int, default=100000, help="evolution points to spend")
    ap.add_argument("--hand", type=int, default=40, help="starting hand size")
    ap.add_argument("--verbose", action="store_true", help="print the full turn log")
    args = ap.parse_args(argv)

    database = GameDatabase()
    if not database.load(args.database):
        print(f"error: could not load {args.database}", file=sys.stderr)
        return 1

    wins = 0
    extinctions = 0
    turns = []

    for i in range(args.runs):
        seed = args.seed + i
        game = build_virus(database, seed, args.ep, args.hand)
        engine = SimulationEngine(game, rng=random.Random(seed))
        state = engine.run_until_end(max_turns=args.max_turns)

        if state.is_victory:
            outcome, wins = "VICTORY", wins + 1
        elif state.extinction:
            outcome, extinctions = "EXTINCT", extinctions + 1
        else:
            outcome = f"no result in {args.max_turns} turns"
        turns.append(state.turn)

        print(f"run {i + 1:>3} (seed {seed}): {outcome} after {state.turn} turns, "
              f"{len(game.achieved_milestones)} milestones, {game.evolution_points} EP")

        if args.verbose:
            for line in state.log:
                print("   ", line)

    print(f"\n{args.runs} runs: {wins} victories, {extinctions} extinctions")
    if turns:
        print(f"turns: min {min(turns)}, median {statistics.median(turns):.0f}, max {max(turns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
