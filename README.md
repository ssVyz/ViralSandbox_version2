# Viral Sandbox

**Status: Work in Progress**

A virus simulation game where players configure and evolve a virus to infect cells. Built with Python and Tkinter.

## Project Structure

```
├── main.py              # Application entry point and main menu
├── models.py            # Data models (Gene, Effect, Milestone, VirusConfig, etc.)
├── database.py          # Database operations, JSON persistence
├── database_editor.py   # Content editor for entities, effects, genes, milestones
├── game_state.py        # Genome/builder rules - no UI
├── simulation.py        # Simulation engine - no UI, runs headless
├── session.py           # Playthrough flow: rounds, gene offers - no UI
├── builder.py           # Builder UI - virus configuration and gene management
├── play_module.py       # Play UI - observes and draws the simulation
├── simulate.py          # Headless CLI runner for balance testing
├── tests/               # Headless tests for the logic layer
└── default_database.json # Default game content
```

## Architecture

The codebase is split into a logic layer and a UI layer. **No module in the
logic layer imports tkinter**, so the game's rules can be run and tested
without a display.

### Data Layer
- **models.py**: Defines dataclasses for game entities (ViralEntity, Effect, Gene, Milestone) and virus configuration
- **database.py**: Handles loading/saving game content from JSON files

### Logic Layer (no UI)
- **game_state.py**: Session state and the genome/builder rules - installing genes, ORFs, terminators, and resolving which effects are active
- **simulation.py**: `SimulationEngine`, the turn-by-turn rules of the infection. Owns `SimulationState`. Reports progress through optional `on_*` callbacks so the UI can observe a run without the engine knowing anything about widgets
- **session.py**: `GameSession`, the lifecycle of one playthrough - starting a game, advancing rounds, and choosing which genes to offer between them. Returns `StartResult` / `RoundOutcome` values for the caller to present, so it holds no dialog text

### UI Layer
- **main.py**: Main menu and window management. Owns a `GameSession` and presents whatever it reports; contains no round logic of its own
- **database_editor.py**: Tabbed editor for creating and modifying game content (entities, effects, genes, milestones, global settings)
- **builder.py**: Module where players configure their virus genome type, install genes, and manage ORFs
- **play_module.py**: Play window. Drives `SimulationEngine` from a Tk timer and redraws in response to its callbacks; contains no simulation rules of its own

### Game Flow
1. Main menu launches the application
2. Builder module allows virus configuration and gene installation
3. Play module runs turn-based simulation
4. After each round, players return to builder with earned evolution points
5. Milestones track progress and unlock sequentially based on prerequisites

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages the Python version and the virtual environment
- Tkinter (bundled with the Python interpreter uv installs; no separate install needed)

There are no third-party dependencies — the game runs entirely on the standard library.

## Running

```bash
uv run main.py
```

That is the whole setup. On first run uv downloads the pinned Python
(`.python-version`), creates `.venv/`, and launches the game. No manual
`venv` activation and no `pip install` step.

To create the environment without launching the game:

```bash
uv sync
```

### Notes

- The game reads and writes `settings.json` and `default_database.json` next to
  the source files, so it is configured as a run-in-place application
  (`package = false` in `pyproject.toml`) rather than an installable library.
- `uv.lock` is committed so the environment is reproducible.

## Testing

The simulation engine runs headlessly, so the game's rules are testable without
opening a window:

```bash
uv run pytest
```

To run simulations for balance testing:

```bash
uv run simulate.py --runs 20
uv run simulate.py --seed 7 --verbose      # print the full turn log
```

`SimulationEngine` takes an optional `rng`, so a run can be made reproducible:

```python
from simulation import SimulationEngine
import random

engine = SimulationEngine(game_state, rng=random.Random(42))
state = engine.run_until_end()
print(state.turn, state.is_victory)
```
