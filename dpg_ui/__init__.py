"""DearPyGui user interface (``uv run main.py --ui dearpygui``).

Gameplay only: content editing stays in the Tk UI. It talks to the game only
through game_api.GameAPI.
"""


def run(api) -> None:
    """Start the DearPyGui UI and block until its window closes."""
    from .app import App
    App(api).run()
