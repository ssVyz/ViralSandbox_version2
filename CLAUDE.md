# CLAUDE.md

Viral Sandbox: educational virus-evolution game. Python 3.13 + Tkinter, stdlib only, managed with uv. Flat layout (modules at repo root). Architecture details: README.md.

## Commands
- Run: `uv run main.py`
- Test: `uv run pytest`
- Balance sim: `uv run simulate.py --runs 20`

## Architecture constraint
Logic modules (`models`, `database`, `settings`, `game_state`, `simulation`, `session`, `simulate`) must never import tkinter. UI lives only in `main`, `builder`, `play_module`, `database_editor`.

## Repo rules
- Every code change: bump the patch version and add a CHANGELOG.md entry for it.
  - Version lives in `pyproject.toml`; run `uv lock` afterwards so `uv.lock` matches.
  - Changelog: newest first, `## [x.y.z] - YYYY-MM-DD`, grouped under Added/Changed/Fixed/Removed.
- Minor/major versions change only when the user asks.
- Never run `git commit` or `git push`; humans handle commits. Leave changes in the working tree.
- Never edit CLAUDE.md.
