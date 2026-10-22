# Viral Sandbox

**Status: Work in Progress**

An educational simulation game where players configure and evolve a virus to infect cells. Built with Python, with two interfaces: Tkinter and DearPyGui.

## Project Structure

```
├── main.py              # Launcher - picks a UI with --ui (default: tkinter)
├── main_menu.py         # Tk UI entry point - main menu, settings and gene offer dialogs
├── builder.py           # Builder UI - virus configuration and gene management
├── play_module.py       # Play UI - paces a round and draws its snapshots
├── database_editor.py   # Content editor UI for entities, effects, genes, milestones
├── dpg_ui/              # DearPyGui UI (--ui dearpygui) - gameplay only, no editor
├── game_api.py          # Application layer - the only module a UI talks to
├── session.py           # Playthrough flow: phases, rounds, gene offers - no UI
├── game_state.py        # Per-game state, VirusConfig, genome/builder rules - no UI
├── simulation.py        # Simulation engine - no UI, runs headless
├── models.py            # Content dataclasses (ViralEntity, Effect, Gene, Milestone) and enums
├── database.py          # Content database, JSON persistence
├── settings.py          # Loads, validates and saves settings.json
├── simulate.py          # Headless CLI runner for balance testing
├── tests/               # Headless tests for the logic and application layers
├── default_database.json # Default game content
├── ui_interface.md      # The UI <-> game contract: every touch point of game_api
└── CHANGELOG.md         # Version history
```

## Architecture

The codebase has three layers. **Only the UI layer imports a UI toolkit**
(tkinter, DearPyGui), so the game runs and is tested without a display. **The UI layer reaches the game only
through `game_api`** (plus `models` for the content dataclasses and enums), so
the UI can be replaced without touching game code. `ui_interface.md` documents
that interface; `tests/test_game_api.py` enforces the import boundary.

### UI Layer
- **main.py**: Launcher. Creates the `GameAPI` and starts the UI chosen with `--ui`; each UI is a module with `run(api)`, registered in `UIS`. Never imports tkinter
- **main_menu.py**: Entry point of the Tk UI: main menu, settings and gene offer dialogs, window management. Presents whatever the `GameAPI` reports
- **builder.py**: Module where players configure their virus genome type, install genes, and manage ORFs, all through `game_api.Builder`
- **play_module.py**: Play window. Calls `Round.step()` from a Tk timer and draws the snapshot it returns; pacing (speed, pause) is its only job besides drawing
- **database_editor.py**: Tabbed editor for creating and modifying game content (entities, effects, genes, milestones, global settings), on a content database handed in by the API. Part of the Tk UI only; other UIs are gameplay only
- **dpg_ui/**: The DearPyGui UI, gameplay only (see [DearPyGui UI](#dearpygui-ui))

### Application Layer
- **game_api.py**: `GameAPI`, the entry point for a UI: settings, version, the game phases, rounds and gene offers. Hands out `Builder` (genome editing) and `Round` (a play round) plus immutable snapshots of everything a UI draws. Wrong-phase calls raise `GameFlowError`; player-facing problems come back as `(ok, message)` or result enums

### Logic Layer (no UI)
- **session.py**: `GameSession`, the lifecycle of one playthrough as a state machine (`GamePhase`): starting a game, starting and finishing rounds (the outcome is read from the simulation), and the gene offers between them
- **game_state.py**: `GameState` and `VirusConfig`: EP, hand, genome, milestones, and the genome/builder rules - installing genes, ORFs, terminators, config locking, round readiness, and resolving which effects are active
- **simulation.py**: `SimulationEngine`, the turn-by-turn rules of the infection. Owns `SimulationState`; optional `on_*` callbacks report progress to headless callers

### Data Layer
- **models.py**: Dataclasses for game content (ViralEntity, Effect, Gene, Milestone) and their enums
- **database.py**: `GameDatabase`, loading/saving game content from JSON files
- **settings.py**: Loading, validating and saving `settings.json`

### Game Flow
1. Main menu launches the application
2. Builder module allows virus configuration and gene installation
3. Play module runs turn-based simulation
4. After each round, players return to builder with earned evolution points
5. Milestones track progress and unlock sequentially based on prerequisites

## Requirements

- [uv](https://docs.astral.sh/uv/) — manages the Python version and the virtual environment
- Tkinter (bundled with the Python interpreter uv installs; no separate install needed)
- [DearPyGui](https://github.com/hoffstadt/DearPyGui) — installed by uv; the one third-party
  package, used only by the DearPyGui UI

The game logic and the Tk UI run entirely on the standard library.

## Running

```bash
uv run main.py
```

That is the whole setup. On first run uv downloads the pinned Python
(`.python-version`), creates `.venv/`, and launches the game. No manual
`venv` activation and no `pip install` step.

The UI is chosen with `--ui`; without it the Tk UI starts:

```bash
uv run main.py --ui tkinter    # same as no argument
uv run main.py --ui dearpygui  # the DearPyGui UI
uv run main.py --help          # lists the available UIs
```

The database editor is only available in the Tk UI (main menu → Database Editor).

### DearPyGui UI

A GPU-rendered, single-window interface (`dpg_ui/`), gameplay only:

- **Title screen** with an animated backdrop (drifting virions drawn with draw nodes
  and transform matrices on the viewport drawlist).
- **Builder**: sortable, searchable hand; drag and drop between hand and genome
  (install at a position, reorder, drag back to remove); a clickable genome map
  with ORF brackets, terminators and dashed read-through; configuration, details
  and tooltips. Tabs for the **life cycle** (a node-editor graph of the virus's
  reaction network with per-turn chances and a minimap) and the **blueprint**.
- **Play**: the round runs inside the render loop at a chosen turns-per-second
  (or turbo), on a worker thread so heavy late-game turns don't freeze the
  window. An animated cell shows every entity as particles in its compartment
  (hover a compartment to inspect it); interactive plots (population on a log
  scale with the win threshold, interferon and antibodies on two axes); a
  shaded compartments table; a filterable log; milestone toasts.
  Keys: Space runs/pauses, → steps one turn.

To create the environment without launching the game:

```bash
uv sync
```

### Notes

- The game reads and writes `settings.json` and `default_database.json` next to
  the source files, so it is configured as a run-in-place application
  (`package = false` in `pyproject.toml`) rather than an installable library.
- The version is declared only in `pyproject.toml`; the game reads it from there
  at runtime (`game_api.get_version()`). Changes are listed in `CHANGELOG.md`.
- `uv.lock` is committed so the environment is reproducible.

## Testing

The game runs headlessly through `game_api`, so its rules and flow are testable
without opening a window (the UI tests only cover their pure-Python parts):

```bash
uv run pytest
```

To run simulations for balance testing:

```bash
uv run simulate.py --runs 20
uv run simulate.py --seed 7 --verbose      # print the full turn log
```

`GameAPI` and `SimulationEngine` take an optional `rng`, so a run can be made
reproducible:

```python
from simulation import SimulationEngine
import random

engine = SimulationEngine(game_state, rng=random.Random(42))
state = engine.run_until_end()
print(state.turn, state.is_victory)
```
