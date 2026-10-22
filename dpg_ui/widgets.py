"""Shared widgets: modal choice dialogs and toast notifications.

DearPyGui has no blocking message boxes: a dialog is a modal window whose
buttons call back with the player's choice.
"""
import time
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from . import theme


def viewport_size() -> tuple:
    return dpg.get_viewport_client_width(), dpg.get_viewport_client_height()


class Dialogs:
    """Modal dialogs, centered while their auto-size settles."""

    WIDTH = 520
    CENTER_FRAMES = 8  # an autosized window takes a few frames to reach its final size

    def __init__(self, fonts: theme.Fonts):
        self.fonts = fonts
        self._to_center: dict = {}  # window -> frames left

    def choose(self, title: str, message: str, buttons: list, width: int = WIDTH):
        """Ask the player to pick one of ``buttons``: ``(label, callback or None, color or None)``.

        Every button closes the dialog; then its callback runs.
        """
        vw, vh = viewport_size()
        with dpg.window(label=title, modal=True, no_collapse=True, no_resize=True,
                        autosize=True, no_saved_settings=True, no_open_over_existing_popup=False,
                        pos=(max(0, (vw - width) // 2), max(0, vh // 2 - 140)),
                        on_close=self._on_close) as window:
            dpg.add_text(message, wrap=width - 30)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                for label, callback, color in buttons:
                    button = dpg.add_button(label=label, callback=self._on_button,
                                            user_data=(window, callback), height=32)
                    if color is not None:
                        dpg.bind_item_theme(button, theme.button_theme(color))
        self.center_later(window)
        return window

    def message(self, title: str, message: str, ok: Optional[Callable] = None):
        return self.choose(title, message, [("OK", ok, theme.ACCENT)])

    def center_later(self, window):
        self._to_center[window] = self.CENTER_FRAMES

    def _on_button(self, sender, app_data, user_data):
        window, callback = user_data
        dpg.delete_item(window)
        if callback is not None:
            callback()

    def _on_close(self, sender, app_data, user_data):
        dpg.delete_item(sender)

    def on_frame(self):
        """Keep new dialogs centered until their size has settled."""
        vw, vh = viewport_size()
        for window, frames in list(self._to_center.items()):
            if not dpg.does_item_exist(window) or frames <= 0:
                del self._to_center[window]
                continue
            w, h = dpg.get_item_rect_size(window)
            if w > 0 and h > 0:
                dpg.set_item_pos(window, (max(0, (vw - w) // 2), max(0, (vh - h) // 2)))
                self._to_center[window] = frames - 1


class Toasts:
    """Short notifications stacked in the top-right corner."""

    LIMIT = 4

    def __init__(self):
        self._items: list = []  # [window, expires_at]

    def show(self, text: str, color=theme.INFO, seconds: float = 3.5):
        while len(self._items) >= self.LIMIT:
            window, _ = self._items.pop(0)
            if dpg.does_item_exist(window):
                dpg.delete_item(window)
        with dpg.window(no_title_bar=True, no_resize=True, no_move=True, autosize=True,
                        no_collapse=True, no_focus_on_appearing=True, no_saved_settings=True,
                        no_scrollbar=True, min_size=(60, 20), pos=(-1000, -1000)) as window:
            with dpg.group(horizontal=True):
                dpg.add_text("●", color=color)
                dpg.add_text(text)
        self._items.append([window, time.perf_counter() + seconds])

    def on_frame(self):
        now = time.perf_counter()
        keep = []
        for window, expires in self._items:
            if now >= expires:
                if dpg.does_item_exist(window):
                    dpg.delete_item(window)
            else:
                keep.append([window, expires])
        self._items = keep

        vw, _ = viewport_size()
        y = 70
        for window, _ in self._items:
            w, h = dpg.get_item_rect_size(window)
            dpg.set_item_pos(window, (vw - max(w, 200) - 18, y))
            y += max(h, 30) + 6
