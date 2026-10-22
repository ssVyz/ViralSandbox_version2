"""
Viral Sandbox - launcher.
An educational game/simulator for building virtual viruses.

Picks a user interface and starts it::

    uv run main.py               # the default UI (tkinter)
    uv run main.py --ui tkinter

Every UI is a module with a ``run(api: GameAPI)`` function, registered in
``UIS`` below. A UI module is imported only when it is chosen, so one UI's
toolkit is never loaded for another. This launcher must never import tkinter.
"""
import argparse
import importlib

from game_api import GameAPI

# UI name -> module providing run(api). Only the tkinter UI includes the
# database editor; every other UI is gameplay only (see ui_interface.md).
UIS = {
    "tkinter": "main_menu",
    "dearpygui": "dpg_ui",
}
DEFAULT_UI = "tkinter"


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Viral Sandbox")
    parser.add_argument("--ui", choices=sorted(UIS), default=DEFAULT_UI,
                        help=f"user interface to start (default: {DEFAULT_UI})")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    ui = importlib.import_module(UIS[args.ui])
    ui.run(GameAPI())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
