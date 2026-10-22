# Changelog

All notable changes to this project are documented here.
Every code change bumps the patch version; minor and major bumps happen only on request.

## [0.2.3] - 2026-10-22

### Added
- `--ui` command-line option to choose the user interface: `uv run main.py --ui tkinter`. Without it the Tk UI starts. UIs are registered in `UIS` in `main.py`; each is a module with `run(api)`.
- `tests/test_launcher.py`: `--ui` parsing, every registered UI has `run(api)`, the launcher never loads tkinter, and no UI except tkinter loads the database editor.

### Changed
- `main.py` is now only the launcher (no tkinter import); the Tk main menu, settings and gene offer dialogs moved to `main_menu.py`.
- `MainMenu` receives its `GameAPI` from the launcher instead of creating one.
- `ui_interface.md`: how to add a UI; the database editor is Tk-only. `README.md` updated.

## [0.2.2] - 2026-10-22

### Added
- `game_api.py`: application layer between UI and game. `GameAPI` (settings, version, game phases, rounds, gene offers), `Builder` (genome editing) and `Round` (paced play round), returning immutable snapshots.
- `ui_interface.md`: documents every UI touch point of `game_api`.
- Game phase state machine in `session.py` (`GamePhase`, `GameFlowError`); the session now owns the round in progress and the pending gene offer.
- Rules moved out of the UI into the logic layer: round readiness (`RoundReadiness`), genome fit of a gene (`GenomeFit`), validated config and terminator-chance setters, settings validation, movability of installed items.
- `SimulationEngine.end_early()` and `count_population()`; shared `INTERFERON_MAX` and `POPULATION_GROUPS` constants.
- Tests: `tests/test_game_api.py` (API flow, and a check that UI modules import only `game_api` and `models`), plus new session and engine tests.

### Changed
- All four UI modules (`main.py`, `builder.py`, `play_module.py`, `database_editor.py`) talk to the game only through `game_api`.
- The round outcome is read from the simulation instead of being passed back by the play window.
- Win threshold comes from `GameState.win_threshold` (the engine's duplicate `WIN_THRESHOLD` and the unused `GameState.check_win_condition` are gone).
- `SimulationState` no longer holds UI pacing (`is_running`, `speed`); the play window owns them.
- Version is read at runtime from `pyproject.toml`, its single declaration (main menu showed a hard-coded 0.1.0).
- `requires-python` raised to 3.11 (for `tomllib`); `uv.lock` updated.
- `README.md` structure and architecture updated; `.gitignore` tracks `ui_interface.md`.

### Fixed
- The gene offer dialog showed the next round as completed ("Round 2/10 complete!" after round 1).
- The end-of-round dialog listed all milestones ever achieved instead of this round's.
- Milestones achieved on a round's final turn were missing from the end-of-round dialog.
- An ORF or terminator alone counted as "a gene installed" for starting a round.
- The "Genome Type Required" prompt showed the locked/default genome and a 10 EP cost instead of the configuration about to be locked and its actual (free) cost.
- The builder window is closed when a game ends by victory or by running out of rounds (it stayed hidden in the background).

## [0.2.1] - 2026-10-22

### Added
- `CHANGELOG.md` and `CLAUDE.md` for repo housekeeping and agent rules.

### Changed
- Version set to 0.2.1 (was 0.1.0) in `pyproject.toml` and `uv.lock`.
- Project description now reads "educational simulation game" (`README.md`, `pyproject.toml`).
- `.gitignore`: `CHANGELOG.md` and `CLAUDE.md` are tracked (previously excluded by `*.md`).

## [0.1.0] and earlier

Not recorded; see git history.
