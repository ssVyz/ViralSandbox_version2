# CLAUDE.md

Viral Sandbox: educational virus-evolution game. Python 3.13, managed with uv. Two UIs: Tkinter (default, stdlib only, includes the database editor) and DearPyGui (`dpg_ui/` package, `--ui dearpygui`, the only third-party dependency, gameplay only). Otherwise flat layout (modules at repo root). Architecture details: README.md.

## Commands
- Run: `uv run main.py`
- Test: `uv run pytest`
- Balance sim: `uv run simulate.py --runs 20`

## Architecture constraints
- Logic modules (`models`, `database`, `settings`, `game_state`, `simulation`, `session`, `simulate`) and the application layer `game_api` should never import ui packages. Special cases would require human consent.
- New UI touch points go into `game_api` and must be documented in `ui_interface.md`.
- UI ↔ game API (phases, `GameAPI`/`Builder`/`Round`, snapshots, conventions): see `ui_interface.md`.

## Repo rules
- Every code change: bump the patch version and add a CHANGELOG.md entry for it.
  - Version lives in `pyproject.toml`; run `uv lock` afterwards so `uv.lock` matches.
  - Changelog: newest first, `## [x.y.z] - YYYY-MM-DD`, grouped under Added/Changed/Fixed/Removed.
- Minor/major versions change only when the user asks.
- Never run `git commit` or `git push`; humans handle commits. Leave changes in the working tree.
- Never edit CLAUDE.md, unless specifically instructed to do so.
