"""Title screen: an animated backdrop, new game, settings.

The backdrop is a viewport drawlist behind all windows: drifting virions
made of draw nodes, moved and spun each frame with transform matrices.
"""
import math
import random

import dearpygui.dearpygui as dpg

from game_api import HAND_SIZE_MAX, HAND_SIZE_MIN, StartResult, WINDOW_MODES
from . import theme
from .widgets import viewport_size

START_ERRORS = {
    StartResult.LOAD_FAILED: "The database file could not be loaded.",
    StartResult.NO_GENES: "The database has no genes. Genes are created in the database editor "
                          "(uv run main.py --ui tkinter).",
    StartResult.NOT_ENOUGH_GENES: "The database doesn't have enough genes to deal a starting hand.",
}
COLUMN_WIDTH = 520


class Backdrop:
    COUNT = 28

    def __init__(self):
        rng = random.Random(7)
        self.rng = rng
        palette = [theme.CATEGORY_COLORS[c] for c in ("Virion", "RNA", "DNA", "Protein", "Viral complex")]
        self.particles = []
        with dpg.viewport_drawlist(front=False) as self.drawlist:
            for _ in range(self.COUNT):
                size = rng.uniform(9, 30)
                color = theme.with_alpha(rng.choice(palette), rng.randint(60, 130))
                with dpg.draw_node() as node:
                    dpg.draw_circle((0, 0), size, color=color, fill=theme.with_alpha(color, 28), thickness=2)
                    spikes = rng.randint(7, 12)
                    for k in range(spikes):
                        a = 2 * math.pi * k / spikes
                        inner = (size * math.cos(a), size * math.sin(a))
                        outer = (size * 1.4 * math.cos(a), size * 1.4 * math.sin(a))
                        dpg.draw_line(inner, outer, color=color, thickness=2)
                        dpg.draw_circle(outer, max(2.0, size * 0.1), color=color, fill=color)
                self.particles.append({
                    "node": node, "x": rng.uniform(0, 1600), "y": rng.uniform(0, 1000),
                    "vx": rng.uniform(-18, 18), "vy": rng.uniform(-14, 14),
                    "angle": rng.uniform(0, 6.3), "spin": rng.uniform(-0.6, 0.6), "size": size,
                })

    def show(self, visible: bool):
        dpg.configure_item(self.drawlist, show=visible)

    def animate(self, dt: float):
        width, height = viewport_size()
        for p in self.particles:
            p["x"] = (p["x"] + p["vx"] * dt) % (width + 120)
            p["y"] = (p["y"] + p["vy"] * dt) % (height + 120)
            p["angle"] += p["spin"] * dt
            transform = (dpg.create_translation_matrix([p["x"] - 60, p["y"] - 60])
                         * dpg.create_rotation_matrix(p["angle"], [0, 0, -1]))
            dpg.apply_transform(p["node"], transform)


class MenuView:
    """The title screen lives in its own window without a background (the
    primary window is hidden meanwhile), so the backdrop shows through."""

    def __init__(self, app):
        self.app = app
        self.api = app.api
        self.backdrop = Backdrop()
        with dpg.window(show=False, no_title_bar=True, no_resize=True, no_move=True, no_background=True,
                        no_scrollbar=True, no_collapse=True, no_saved_settings=True,
                        no_bring_to_front_on_focus=True, pos=(0, 0)) as self.root:
            self.top_spacer = dpg.add_spacer(height=160)
            with dpg.group(indent=400) as self.column:
                self.title = dpg.add_text("VIRAL SANDBOX", color=theme.ACCENT)
                theme.use_font(self.title, app.fonts.title)
                self.subtitle = dpg.add_text("Build.  Infect.  Evolve.", color=theme.TEXT)
                theme.use_font(self.subtitle, app.fonts.large)
                dpg.add_spacer(height=28)
                new_game = dpg.add_button(label="New game", width=COLUMN_WIDTH, height=52, callback=self._on_new_game)
                dpg.bind_item_theme(new_game, theme.button_theme(theme.darken(theme.ACCENT, 0.25)))
                theme.use_font(new_game, app.fonts.large)
                settings = dpg.add_button(label="Settings", width=COLUMN_WIDTH, height=44, callback=self._on_settings)
                theme.use_font(settings, app.fonts.large)
                quit_button = dpg.add_button(label="Quit", width=COLUMN_WIDTH, height=44,
                                             callback=lambda: dpg.stop_dearpygui())
                theme.use_font(quit_button, app.fonts.large)
                dpg.add_spacer(height=24)
                dpg.add_text("An educational simulator: configure a virus genome, then watch it infect a cell.",
                             color=theme.TEXT_DIM, wrap=COLUMN_WIDTH)
                dpg.add_text("The database editor is part of the Tk interface:  uv run main.py --ui tkinter",
                             color=theme.TEXT_DIM, wrap=COLUMN_WIDTH)
                dpg.add_text(f"Version {self.api.version}  ·  DearPyGui interface", color=theme.TEXT_DIM)

    def show(self):
        dpg.configure_item(self.root, show=True)
        self.backdrop.show(True)

    def hide(self):
        dpg.configure_item(self.root, show=False)
        self.backdrop.show(False)

    def typing(self) -> bool:
        return False

    def on_resize(self, width: int, height: int):
        dpg.configure_item(self.root, width=width, height=height)
        dpg.configure_item(self.top_spacer, height=max(40, int(height * 0.22)))
        dpg.configure_item(self.column, indent=max(20, (width - COLUMN_WIDTH) // 2))

    def on_frame(self, dt: float):
        self.backdrop.animate(dt)

    # ------------------------------------------------------------------ new game

    def _on_new_game(self, sender, app_data, user_data):
        path = self.api.default_database_path()
        if path is not None:
            self._start(path)
            return
        with dpg.file_dialog(label="Choose a game database", modal=True, width=760, height=460,
                             callback=self._on_file_chosen, cancel_callback=self._on_file_cancel):
            dpg.add_file_extension(".json", color=theme.ACCENT)
            dpg.add_file_extension(".*")

    def _on_file_chosen(self, sender, app_data, user_data):
        dpg.delete_item(sender)
        path = app_data.get("file_path_name") if isinstance(app_data, dict) else None
        if path:
            self._start(path)

    def _on_file_cancel(self, sender, app_data, user_data):
        dpg.delete_item(sender)

    def _start(self, path: str):
        result = self.api.new_game(path)
        if result is StartResult.OK:
            self.app.sync()
        else:
            self.app.dialogs.message("Could not start a game", START_ERRORS.get(result, str(result)))

    # ------------------------------------------------------------------ settings

    def _on_settings(self, sender, app_data, user_data):
        settings = self.api.settings
        width = 470
        vw, vh = viewport_size()
        with dpg.window(label="Settings", modal=True, no_collapse=True, no_resize=True, autosize=True,
                        no_saved_settings=True, no_open_over_existing_popup=False, pos=((vw - width) // 2, vh // 2 - 160),
                        on_close=lambda sender: dpg.delete_item(sender)) as window:
            with dpg.table(header_row=False, policy=dpg.mvTable_SizingFixedFit):
                dpg.add_table_column()
                dpg.add_table_column()
                with dpg.table_row():
                    dpg.add_text("Window mode")
                    mode = dpg.add_combo(list(WINDOW_MODES), default_value=settings["display"]["window_mode"],
                                         width=220)
                with dpg.table_row():
                    dpg.add_text("Starting hand")
                    hand = dpg.add_slider_int(default_value=settings["game"]["starting_hand_size"],
                                              min_value=HAND_SIZE_MIN, max_value=HAND_SIZE_MAX, width=220,
                                              format="%d genes")
                with dpg.table_row():
                    dpg.add_text("Database file")
                    database = dpg.add_input_text(default_value=settings["game"]["default_database"], width=220)
            dpg.add_text("Hand size and database apply to the next new game.", color=theme.TEXT_DIM,
                         wrap=width - 30)
            error = dpg.add_text("", color=theme.BAD, wrap=width - 30)
            with dpg.group(horizontal=True):
                save = dpg.add_button(label="Save", width=110, height=30, callback=self._on_settings_save,
                                      user_data=(window, mode, hand, database, error))
                dpg.bind_item_theme(save, theme.button_theme(theme.darken(theme.ACCENT, 0.25)))
                dpg.add_button(label="Cancel", width=110, height=30,
                               callback=lambda: dpg.delete_item(window))
        self.app.dialogs.center_later(window)

    def _on_settings_save(self, sender, app_data, user_data):
        window, mode, hand, database, error = user_data
        settings = self.api.settings
        settings["display"]["window_mode"] = dpg.get_value(mode)
        settings["game"]["starting_hand_size"] = dpg.get_value(hand)
        settings["game"]["default_database"] = dpg.get_value(database).strip()
        saved, message = self.api.save_settings(settings)
        if not saved:
            dpg.set_value(error, message)
            return
        dpg.delete_item(window)
        if settings["display"]["window_mode"] == "maximized":
            dpg.maximize_viewport()
        self.app.toasts.show("Settings saved", theme.GOOD, 2.0)
