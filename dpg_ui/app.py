"""The DearPyGui application: viewport, render loop and screen flow.

The render loop is ours (``render_dearpygui_frame`` once per frame), with
callbacks run from the same loop (manual callback management), so the game
is only ever touched from one thread. Which screen and dialog is shown
follows ``api.phase``.
"""
import sys
import time

import dearpygui.dearpygui as dpg

from game_api import GameAPI, GamePhase, RoundOutcome
from . import theme
from .builder_view import BuilderView
from .menu_view import MenuView
from .play_view import PlayView
from .widgets import Dialogs, Toasts, viewport_size


class App:
    PRIMARY = "viral_sandbox_primary"

    def __init__(self, api: GameAPI):
        self.api = api
        self.screen = None
        self._resize_pending = True
        self._offer_window = None
        self._game_over_window = None
        self._summary_window = None
        self._last_outcome = None
        self.frame_hook = None  # callable(app, dt) run every frame (used by scripted checks)

    # ------------------------------------------------------------------ lifecycle

    def setup(self):
        dpg.create_context()
        dpg.configure_app(manual_callback_management=True)
        self.fonts = theme.load_fonts()
        theme.apply_global_theme()
        dpg.create_viewport(title=f"Viral Sandbox {self.api.version}  ·  DearPyGui", width=1440, height=920,
                            min_width=1180, min_height=760, clear_color=theme.BG)
        self.dialogs = Dialogs(self.fonts)
        self.toasts = Toasts()

        with dpg.window(tag=self.PRIMARY, no_scrollbar=True):
            pass
        self.menu = MenuView(self)
        self.builder = BuilderView(self, self.PRIMARY)
        self.play = PlayView(self, self.PRIMARY)

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_Spacebar, callback=self._on_space)
            dpg.add_key_press_handler(dpg.mvKey_Right, callback=self._on_right)
        dpg.set_viewport_resize_callback(self._on_viewport_resize)

        dpg.setup_dearpygui()
        dpg.show_viewport()
        if self.api.settings["display"]["window_mode"] == "maximized":
            dpg.maximize_viewport()
        self.sync()

    def run(self):
        self.setup()
        # Turns run on a worker thread; switching threads more often keeps frames
        # coming while a heavy turn holds the interpreter
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(0.001)
        try:
            last = time.perf_counter()
            while dpg.is_dearpygui_running():
                dpg.run_callbacks(dpg.get_callback_queue())
                now = time.perf_counter()
                self.on_frame(min(now - last, 0.25))
                last = now
                dpg.render_dearpygui_frame()
        finally:
            sys.setswitchinterval(switch_interval)
            self.play.shutdown()
            dpg.destroy_context()

    def on_frame(self, dt: float):
        if self._resize_pending:
            width, height = viewport_size()
            if width > 0 and height > 0:
                self._resize_pending = False
                for screen in (self.menu, self.builder, self.play):
                    screen.on_resize(width, height)
        if self.screen is not None:
            self.screen.on_frame(dt)
        self.dialogs.on_frame()
        self.toasts.on_frame()
        if self.frame_hook is not None:
            self.frame_hook(self, dt)

    def _on_viewport_resize(self, sender, app_data, user_data):
        self._resize_pending = True

    # ------------------------------------------------------------------ flow

    def show_screen(self, screen):
        if screen is self.screen:
            if screen is self.builder:
                self.builder.refresh()
            return
        if self.screen is not None:
            self.screen.hide()
        # The menu has its own see-through window; builder and play share the primary one
        in_primary = screen is not self.menu
        dpg.configure_item(self.PRIMARY, show=in_primary)
        dpg.set_primary_window(self.PRIMARY, in_primary)
        self.screen = screen
        screen.show()
        self._resize_pending = True

    def sync(self):
        """Show what the current phase calls for."""
        phase = self.api.phase
        if phase is GamePhase.NO_GAME:
            self.show_screen(self.menu)
        elif phase is GamePhase.BUILDING:
            self.show_screen(self.builder)
        elif phase is GamePhase.PLAYING:
            self.show_screen(self.play)
        elif phase is GamePhase.GENE_OFFER:
            self.show_screen(self.builder)
            self._show_gene_offer()
        elif phase is GamePhase.GAME_OVER:
            self._show_game_over()

    def start_round(self):
        self.api.start_round()
        self.sync()

    def finish_round(self):
        self._close(self._summary_window)
        self._summary_window = None
        outcome = self.api.finish_round()
        self._last_outcome = outcome
        if outcome is RoundOutcome.CONTINUE and self.api.phase is GamePhase.BUILDING:
            self.toasts.show("No genes left to offer.", theme.TEXT_DIM)
        self.sync()

    def quit_game(self):
        self.api.end_game()
        self.sync()

    # ------------------------------------------------------------------ keys

    def _typing(self) -> bool:
        return self.screen is not None and self.screen.typing()

    def _on_space(self, sender, app_data, user_data):
        if self.screen is self.play and not self._typing():
            self.play.toggle()

    def _on_right(self, sender, app_data, user_data):
        if self.screen is self.play and not self._typing():
            self.play.step_once()

    # ------------------------------------------------------------------ dialogs

    def _close(self, window):
        if window is not None and dpg.does_item_exist(window):
            dpg.delete_item(window)

    def show_round_summary(self, summary, review):
        self._close(self._summary_window)
        if summary.is_victory:
            title, color = "VICTORY!", theme.GOOD
        elif summary.is_extinct:
            title, color = "Virus extinct", theme.BAD
        else:
            title, color = "Round ended", theme.TEXT
        width = 460
        vw, vh = viewport_size()
        with dpg.window(label="Round complete", modal=True, no_collapse=True, no_resize=True, autosize=True,
                        no_close=True, no_saved_settings=True, no_open_over_existing_popup=False,
                        pos=((vw - width) // 2, vh // 2 - 180)) as window:
            self._summary_window = window
            heading = dpg.add_text(title, color=color)
            theme.use_font(heading, self.fonts.title if summary.is_victory else self.fonts.large)
            dpg.add_text(f"Turns survived: {summary.turns:,}")
            if summary.milestones_achieved:
                dpg.add_text("Milestones this round:", color=theme.TEXT_DIM)
                for milestone in summary.milestones_achieved:
                    dpg.add_text(f"  ● {milestone.name}   +{milestone.reward_ep} EP", color=theme.GOLD)
            else:
                dpg.add_text("No new milestones this round.", color=theme.TEXT_DIM)
            total = dpg.add_text(f"Total: {summary.evolution_points} EP", color=theme.GOLD)
            theme.use_font(total, self.fonts.large)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                def do_review():
                    dpg.delete_item(window)
                    review()

                def do_continue():
                    dpg.delete_item(window)
                    self.finish_round()

                look = dpg.add_button(label="Review round", width=150, height=32, callback=do_review)
                go = dpg.add_button(label="Continue  →", width=150, height=32, callback=do_continue)
                dpg.bind_item_theme(go, theme.button_theme(theme.darken(theme.ACCENT, 0.2)))
                if not (summary.is_victory or summary.is_extinct):
                    dpg.configure_item(look, show=False)
        self.dialogs.center_later(window)

    def _show_gene_offer(self):
        if self._offer_window is not None and dpg.does_item_exist(self._offer_window):
            return
        offer = self.api.gene_offer
        if offer is None:
            return
        width = 760
        vw, vh = viewport_size()
        with dpg.window(label="Choose a gene", modal=True, no_collapse=True, no_close=True, autosize=True,
                        no_resize=True, no_saved_settings=True, no_open_over_existing_popup=False,
                        pos=((vw - width) // 2, vh // 2 - 220)) as window:
            self._offer_window = window
            heading = dpg.add_text(f"Round {offer.completed_round} / {offer.max_rounds} complete: "
                                   "add one gene to your hand")
            theme.use_font(heading, self.fonts.large)
            with dpg.table(header_row=True, policy=dpg.mvTable_SizingStretchProp, row_background=True,
                           width=width):
                dpg.add_table_column(label="Gene", init_width_or_weight=0.36)
                dpg.add_table_column(label="Set", init_width_or_weight=0.10)
                dpg.add_table_column(label="EP", init_width_or_weight=0.08)
                dpg.add_table_column(label="bp", init_width_or_weight=0.10)
                dpg.add_table_column(label="Effects", init_width_or_weight=0.24)
                dpg.add_table_column(label="", init_width_or_weight=0.12)
                for gene in offer.genes:
                    with dpg.table_row():
                        name = dpg.add_text(gene.name, color=theme.gene_color(gene))
                        with dpg.tooltip(name):
                            dpg.add_text(gene.description or gene.name, wrap=380)
                        dpg.add_text(gene.set_name, color=theme.TEXT_DIM)
                        dpg.add_text(str(gene.install_cost))
                        dpg.add_text(f"{gene.length:,}", color=theme.TEXT_DIM)
                        names = [e.name for e in map(self.api.get_effect, gene.effect_ids) if e]
                        joined = ", ".join(names)
                        summary = (f"{len(names)}: {joined[:38]}" + ("…" if len(joined) > 38 else "")
                                   if names else "none")
                        effects = dpg.add_text(summary, color=theme.TEXT_DIM)
                        with dpg.tooltip(effects):
                            for effect_name in names:
                                dpg.add_text(f"• {effect_name}")
                        take = dpg.add_button(label="Take", width=-1, callback=self._on_take_gene,
                                              user_data=gene.id)
                        dpg.bind_item_theme(take, theme.button_theme(theme.darken(theme.ACCENT, 0.25)))
            dpg.add_spacer(height=4)
            dpg.add_button(label="Skip: take none", height=30, callback=self._on_skip_offer)
        self.dialogs.center_later(window)

    def _close_offer(self):
        if self._offer_window is not None and dpg.does_item_exist(self._offer_window):
            dpg.delete_item(self._offer_window)
        self._offer_window = None

    def _on_take_gene(self, sender, app_data, user_data):
        gene = self.api.get_gene(user_data)
        self.api.accept_offered_gene(user_data)
        self._close_offer()
        if gene:
            self.toasts.show(f"{gene.name} added to your hand", theme.GOOD, 2.5)
        self.sync()

    def _on_skip_offer(self, sender, app_data, user_data):
        self.api.decline_gene_offer()
        self._close_offer()
        self.sync()

    def _show_game_over(self):
        if self._game_over_window is not None and dpg.does_item_exist(self._game_over_window):
            return
        status = self.api.status()
        victory = self._last_outcome is RoundOutcome.VICTORY
        width = 520
        vw, vh = viewport_size()
        with dpg.window(label="Game over", modal=True, no_collapse=True, no_close=True, autosize=True,
                        no_resize=True, no_saved_settings=True, no_open_over_existing_popup=False,
                        pos=((vw - width) // 2, vh // 2 - 140)) as window:
            self._game_over_window = window
            heading = dpg.add_text("Runaway reaction!" if victory else "Out of rounds",
                                   color=theme.GOOD if victory else theme.WARN)
            theme.use_font(heading, self.fonts.title)
            dpg.add_text("Your virus reached the virion threshold and took over the cell." if victory else
                         f"All {status.max_rounds} rounds are played without a runaway reaction.",
                         wrap=width - 30)
            total = dpg.add_text(f"Final score: {status.evolution_points} EP", color=theme.GOLD)
            theme.use_font(total, self.fonts.large)
            dpg.add_spacer(height=6)
            done = dpg.add_button(label="Back to the main menu", height=34, callback=self._on_game_over_done)
            dpg.bind_item_theme(done, theme.button_theme(theme.darken(theme.ACCENT, 0.2)))
        self.dialogs.center_later(window)

    def _on_game_over_done(self, sender, app_data, user_data):
        if self._game_over_window is not None and dpg.does_item_exist(self._game_over_window):
            dpg.delete_item(self._game_over_window)
        self._game_over_window = None
        self.quit_game()
