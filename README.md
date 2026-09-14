# Viral Sandbox

**Status: Work in Progress**

A virus simulation game where players configure and evolve a virus to infect cells. Built with Python and Tkinter.

## Project Structure

```
├── main.py              # Application entry point and main menu
├── models.py            # Data models (Gene, Effect, Milestone, VirusConfig, etc.)
├── database.py          # Database operations, JSON persistence
├── database_editor.py   # Content editor for entities, effects, genes, milestones
├── game_state.py        # Game session state and logic
├── builder.py           # Builder module - virus configuration and gene management
├── play_module.py       # Play module - simulation execution
└── default_database.json # Default game content
```

## Architecture

### Data Layer
- **models.py**: Defines dataclasses for game entities (ViralEntity, Effect, Gene, Milestone) and virus configuration
- **database.py**: Handles loading/saving game content from JSON files
- **game_state.py**: Manages session state including installed genes, evolution points, and virus configuration

### UI Layer
- **main.py**: Main menu with options to start new game, continue, or edit database
- **database_editor.py**: Tabbed editor for creating and modifying game content (entities, effects, genes, milestones, global settings)
- **builder.py**: Module where players configure their virus genome type, install genes, and manage ORFs
- **play_module.py**: Simulation module that runs the virus infection, tracks entity populations, and checks milestone completion

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
