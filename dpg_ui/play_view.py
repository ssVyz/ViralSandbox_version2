"""Play screen: the round advances inside the render loop, drawn live.

The UI paces the round itself: each frame it asks for as many Round.step()
calls as the chosen turns per second need (or, in turbo, as many as fit in
the frame budget), then redraws the cell, the plots and the panels from the
snapshots. Turns run on one worker thread, so a heavy turn late in a round
(hundreds of milliseconds) never freezes the window; the round is only
touched by that thread while a batch is in flight.
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor

import dearpygui.dearpygui as dpg

from game_api import POPULATION_GROUPS
from models import CellLocation
from . import theme
from .cell_view import CellView

LOCATIONS = [loc.value for loc in CellLocation]
FRAME_BUDGET = 0.014     # seconds of simulation per frame at most
PLOT_INTERVAL = 1 / 30   # seconds between plot/cell redraws
PANEL_INTERVAL = 0.25    # seconds between table/log redraws
HEADER_HEIGHT = 118
# Speed slider steps (turns per second): fine at the slow end, condensed toward the fast end
SPEEDS = (1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 8, 10, 12, 15, 20, 30, 50, 80, 120, 240)
DEFAULT_SPEED = 3
MILESTONE_AREA = 210     # below the cell view
# The symlog axis draws no tick labels by itself
LOG_TICKS = (("0", 0), ("1", 1), ("10", 10), ("100", 100), ("1k", 1e3), ("10k", 1e4),
             ("100k", 1e5), ("1M", 1e6), ("10M", 1e7), ("100M", 1e8))


class PlayView:
    def __init__(self, app, parent):
        self.app = app
        self.api = app.api
        self.round = None
        self.running = False
        self.over = False
        self._accum = 0.0
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="round")
        self._batch = None      # future of the turns in flight
        self._last_plot = self._last_panel = 0.0
        self._rate_window = []  # (time, turn) for the measured speed

        with dpg.group(parent=parent, show=False) as self.root:
            self._build_header()
            with dpg.table(header_row=False, resizable=True, policy=dpg.mvTable_SizingStretchProp,
                           borders_innerV=False, pad_outerX=False):
                dpg.add_table_column(init_width_or_weight=0.44)
                dpg.add_table_column(init_width_or_weight=0.56)
                with dpg.table_row():
                    with dpg.child_window(border=True) as self.left:
                        self.cell = CellView(self.left, 560, 520)
                        dpg.add_spacer(height=4)
                        title = dpg.add_text("MILESTONES")
                        theme.use_font(title, self.app.fonts.bold)
                        self.milestones = dpg.add_child_window(border=False, height=-1)
                    with dpg.child_window(border=True) as self.right:
                        with dpg.tab_bar(callback=self._on_tab) as self.tabs:
                            with dpg.tab(label="  Population  ") as self.tab_population:
                                self._build_population_plot()
                            with dpg.tab(label="  Immune response  ") as self.tab_immune:
                                self._build_immune_plot()
                            with dpg.tab(label="  Compartments  ") as self.tab_table:
                                self.table_area = dpg.add_group()
                            with dpg.tab(label="  Log  ") as self.tab_log:
                                with dpg.group(horizontal=True):
                                    self.log_filter = dpg.add_input_text(hint="Filter the log, e.g. milestone",
                                                                         width=320, callback=self._on_log_filter)
                                    dpg.add_text("newest first", color=theme.TEXT_DIM)
                                self.log_text = dpg.add_input_text(multiline=True, readonly=True,
                                                                   width=-1, height=-1)
                                theme.use_font(self.log_text, self.app.fonts.mono)

    # ------------------------------------------------------------------ layout

    def _build_header(self):
        with dpg.child_window(height=HEADER_HEIGHT, border=True, no_scrollbar=True):
            with dpg.group(horizontal=True):
                self.round_text = dpg.add_text("")
                theme.use_font(self.round_text, self.app.fonts.large)
                dpg.add_spacer(width=16)
                dpg.add_text("Virions", color=theme.TEXT_DIM)
                self.virion_bar = dpg.add_progress_bar(width=250, height=24)
                dpg.bind_item_theme(self.virion_bar, _bar_theme(theme.CATEGORY_COLORS["Virion"]))
                dpg.add_spacer(width=10)
                dpg.add_text("Interferon", color=theme.TEXT_DIM)
                self.ifn_bar = dpg.add_progress_bar(width=170, height=24)
                dpg.add_spacer(width=10)
                self.entity_text = dpg.add_text("")
                dpg.add_spacer(width=10)
                self.antibody_text = dpg.add_text("")
            with dpg.group(horizontal=True):
                self.run_button = dpg.add_button(label="", width=130, height=34, callback=self._on_toggle)
                self.step_button = dpg.add_button(label="Step  →", width=90, height=34, callback=self._on_step)
                dpg.add_spacer(width=10)
                self.speed = dpg.add_slider_int(default_value=SPEEDS.index(DEFAULT_SPEED), min_value=0,
                                                max_value=len(SPEEDS) - 1, width=200, clamped=True,
                                                format="")
                with dpg.tooltip(self.speed):
                    dpg.add_text("Turns per second; drag it while the round runs. "
                                 "Fine steps from 1 to 5, coarser above.")
                self.speed_text = dpg.add_text(_speed_label(DEFAULT_SPEED))
                self.turbo = dpg.add_checkbox(label="Turbo")
                with dpg.tooltip(self.turbo):
                    dpg.add_text("Run as many turns as fit in each frame (about 14 ms per frame).")
                dpg.add_spacer(width=10)
                self.rate_text = dpg.add_text("", color=theme.TEXT_DIM)
                dpg.add_spacer(width=20)
                self.end_button = dpg.add_button(label="End round", width=150, height=34, callback=self._on_end)
                self.status_text = dpg.add_text("", color=theme.TEXT_DIM)
            dpg.add_text("Space: run / pause   ·   →: one turn   ·   plots: drag to pan, scroll to zoom, "
                         "double-click to fit, click legend entries to hide them", color=theme.TEXT_DIM)

    def _build_population_plot(self):
        with dpg.group(horizontal=True):
            self.log_scale = dpg.add_checkbox(label="Log scale", default_value=True, callback=self._on_scale)
            self.follow = dpg.add_checkbox(label="Follow", default_value=True)
        with dpg.plot(height=-1, width=-1) as self.pop_plot:
            dpg.add_plot_legend()
            self.pop_x = dpg.add_plot_axis(dpg.mvXAxis, label="Turn")
            self.pop_y = dpg.add_plot_axis(dpg.mvYAxis, label="Count", scale=dpg.mvPlotScale_SymLog)
            dpg.set_axis_ticks(self.pop_y, LOG_TICKS)
            self.pop_series = {}
            for group in POPULATION_GROUPS:
                series = dpg.add_line_series([], [], label=group, parent=self.pop_y)
                dpg.bind_item_theme(series, theme.series_theme(theme.GROUP_COLORS.get(group, theme.TEXT)))
                self.pop_series[group] = series
            self.threshold_line = None

    def _build_immune_plot(self):
        dpg.add_text("Interferon (left axis) raises intracellular degradation; antibodies (right axis) clear "
                     "extracellular entities after a delay.", color=theme.TEXT_DIM, wrap=0)
        with dpg.plot(height=-1, width=-1) as self.immune_plot:
            dpg.add_plot_legend()
            self.imm_x = dpg.add_plot_axis(dpg.mvXAxis, label="Turn")
            self.imm_y = dpg.add_plot_axis(dpg.mvYAxis, label="Interferon")
            self.imm_y2 = dpg.add_plot_axis(dpg.mvYAxis2, label="Antibodies", opposite=True)
            self.ifn_shade = dpg.add_shade_series([], [], label="##interferon area", parent=self.imm_y)
            dpg.bind_item_theme(self.ifn_shade, theme.series_theme(theme.WARN, dpg.mvShadeSeries,
                                                                   fill_alpha=70))
            self.ifn_line = dpg.add_line_series([], [], label="Interferon", parent=self.imm_y)
            dpg.bind_item_theme(self.ifn_line, theme.series_theme(theme.WARN))
            self.ab_line = dpg.add_line_series([], [], label="Antibodies (active)", parent=self.imm_y2)
            dpg.bind_item_theme(self.ab_line, theme.series_theme(theme.BAD))
            self.ab_stored_line = dpg.add_line_series([], [], label="Antibodies (stored)", parent=self.imm_y2)
            dpg.bind_item_theme(self.ab_stored_line, theme.series_theme(theme.with_alpha(theme.BAD, 120),
                                                                        weight=1.0))

    # ------------------------------------------------------------------ screen

    def show(self):
        self.round = self.api.current_round
        # Constants of the round, read once: nothing calls into the round while turns run
        self.win_threshold = self.round.win_threshold
        self.interferon_max = self.round.interferon_max
        self.running = False
        self.over = False
        self._batch = None
        self._accum = 0.0
        self._rate_window = []
        self.xs, self.groups = [], {g: [] for g in POPULATION_GROUPS}
        self.imm_turns, self.ifn, self.antibodies, self.antibodies_stored = [], [], [], []
        if self.threshold_line is not None:
            dpg.delete_item(self.threshold_line)
        self.threshold_line = dpg.add_inf_line_series([float(self.win_threshold)], horizontal=True,
                                                      label="Win threshold", parent=self.pop_y)
        dpg.bind_item_theme(self.threshold_line, theme.series_theme(theme.GOLD, dpg.mvInfLineSeries, 1.5))
        dpg.set_value(self.log_filter, "")
        self.snapshot = self.round.snapshot()
        self._record_immune(self.snapshot)
        dpg.configure_item(self.root, show=True)
        self._set_running(False)
        self._refresh_milestones()
        self._redraw(force=True)

    def hide(self):
        self.running = False
        self._drain()
        dpg.configure_item(self.root, show=False)

    def shutdown(self):
        self._worker.shutdown(wait=True, cancel_futures=True)

    def on_resize(self, width: int, height: int):
        panel_height = max(400, height - HEADER_HEIGHT - 36)
        dpg.configure_item(self.left, height=panel_height)
        dpg.configure_item(self.right, height=panel_height)
        cell_width = max(360, int(width * 0.44) - 40)
        cell_height = max(320, panel_height - MILESTONE_AREA)
        self.cell.resize(cell_width, cell_height)

    def typing(self) -> bool:
        return bool(dpg.is_item_active(self.log_filter))

    def on_frame(self, dt: float):
        if self.round is None:
            return
        if self.running and not self.over:
            self._advance(dt)
        self.cell.animate()
        self._redraw()

    # ------------------------------------------------------------------ running

    def _set_running(self, running: bool):
        self.running = running and not self.over
        if self.over:
            dpg.configure_item(self.run_button, label="Round over", enabled=False)
            dpg.bind_item_theme(self.run_button, theme.button_theme((44, 56, 76, 255)))
        elif self.running:
            dpg.configure_item(self.run_button, label="Pause  ||", enabled=True)
            dpg.bind_item_theme(self.run_button, theme.button_theme(theme.darken(theme.WARN, 0.3)))
        else:
            dpg.configure_item(self.run_button, label="Run  ►", enabled=True)
            dpg.bind_item_theme(self.run_button, theme.button_theme(theme.darken(theme.GOOD, 0.25)))
        dpg.configure_item(self.step_button, enabled=not self.over and not self.running)
        dpg.configure_item(self.end_button, label="Continue  →" if self.over else "End round")
        dpg.bind_item_theme(self.end_button, theme.button_theme(
            theme.darken(theme.ACCENT, 0.2) if self.over else theme.darken(theme.BAD, 0.4)))

    def toggle(self):
        if not self.over:
            self._set_running(not self.running)

    def step_once(self):
        if not self.over and not self.running:
            self._drain()
            if not self.over:
                self._process(self.round.step())
            self._redraw(force=True)

    def _on_toggle(self, sender, app_data, user_data):
        self.toggle()

    def _on_step(self, sender, app_data, user_data):
        self.step_once()

    def _advance(self, dt: float):
        """Hand the next batch of turns to the worker; pick up finished ones."""
        if self._batch is not None:
            if not self._batch.done():
                return  # a heavy turn is still running: keep drawing the last snapshot
            self._take_batch()
            if self.over or not self.running:
                return
        if dpg.get_value(self.turbo):
            wanted = 1_000_000
        else:
            speed = self._turn_speed()
            self._accum = min(self._accum + dt * speed, speed)
            wanted = int(self._accum)
            self._accum -= wanted
        if wanted:
            self._batch = self._worker.submit(_run_turns, self.round, wanted, FRAME_BUDGET)

    def _turn_speed(self) -> float:
        return SPEEDS[dpg.get_value(self.speed)]

    def _take_batch(self):
        results, self._batch = self._batch.result(), None
        for result in results:
            self._process(result)

    def _drain(self):
        """Wait for the turns in flight (before anything else touches the round)."""
        if self._batch is not None:
            self._take_batch()

    def _process(self, result) -> bool:
        """Show one finished turn; returns True if it ended the round."""
        self.snapshot = result.snapshot
        self._record_immune(result.snapshot)
        for milestone_id in result.milestones_achieved:
            milestone = self.api.get_milestone(milestone_id)
            if milestone:
                self.app.toasts.show(f"Milestone: {milestone.name}  (+{milestone.reward_ep} EP)",
                                     theme.GOLD, 4.5)
        if result.milestones_changed:
            self._refresh_milestones()
        if result.ended:
            self._round_over()
            return True
        return False

    def _record_immune(self, snapshot):
        self.imm_turns.append(float(snapshot.turn))
        self.ifn.append(float(snapshot.interferon_level))
        self.antibodies.append(float(snapshot.antibodies_active))
        self.antibodies_stored.append(float(snapshot.antibodies_stored))

    def _round_over(self):
        if self.over:
            return
        self.over = True
        self._set_running(False)
        self._redraw(force=True)
        self.app.show_round_summary(self.round.summary(), review=self._review)

    def _review(self):
        dpg.set_value(self.status_text, "Round over. Look around, then continue.")

    def _on_end(self, sender, app_data, user_data):
        if self.over:
            self.app.finish_round()
            return
        was_running = self.running
        self._set_running(False)

        def resume():
            self._set_running(was_running)

        self.app.dialogs.choose("End round", "End this round now and return to the builder?",
                                [("End round", self._end_early, theme.darken(theme.BAD, 0.3)),
                                 ("Keep playing", resume, None)])

    def _end_early(self):
        self._drain()
        if self.over:
            return
        self.round.end_early()
        self.over = True
        self.snapshot = self.round.snapshot()
        self._set_running(False)
        self.app.show_round_summary(self.round.summary(), review=self._review)

    # ------------------------------------------------------------------ drawing

    def _redraw(self, force: bool = False):
        now = time.perf_counter()
        s = self.snapshot
        threshold = self.win_threshold
        dpg.set_value(self.round_text, f"Round {self.round.number}  ·  Turn {s.turn:,}")
        dpg.set_value(self.virion_bar, min(1.0, s.virion_count / threshold))
        dpg.configure_item(self.virion_bar, overlay=f"{s.virion_count:,} / {threshold:,}")
        ifn = s.interferon_level / self.interferon_max
        dpg.set_value(self.ifn_bar, ifn)
        dpg.configure_item(self.ifn_bar, overlay=f"{s.interferon_level:,.0f}")
        dpg.bind_item_theme(self.ifn_bar, _bar_theme(_interferon_color(round(ifn * 20) / 20)))
        dpg.set_value(self.entity_text, f"Entities {s.total_entities:,}")
        dpg.set_value(self.speed_text, _speed_label(self._turn_speed()))
        dpg.set_value(self.antibody_text, f"Antibodies {s.antibodies_active:,} ({s.antibodies_stored:,.0f} stored)")
        self._update_rate(now, s.turn)

        busy = self._batch is not None  # turns in flight: only snapshots may be read
        if force or now - self._last_plot >= PLOT_INTERVAL:
            self._last_plot = now
            self.cell.update(s.population)
            if not busy:
                self._update_plots()
        if not busy and (force or now - self._last_panel >= PANEL_INTERVAL):
            self._last_panel = now
            active = dpg.get_value(self.tabs)
            if active == self.tab_table:
                self._refresh_table()
            elif active == self.tab_log:
                self._refresh_log()

    def _update_rate(self, now: float, turn: int):
        self._rate_window = [(t, n) for t, n in self._rate_window if now - t < 1.0] + [(now, turn)]
        (t0, n0), (t1, n1) = self._rate_window[0], self._rate_window[-1]
        rate = (n1 - n0) / (t1 - t0) if t1 > t0 else 0
        dpg.set_value(self.rate_text, f"actual {rate:,.1f}/s" if self.running else "")
        dpg.set_value(self.status_text, "" if not self.over else dpg.get_value(self.status_text))

    def _update_plots(self):
        history = self.round.history()
        for turn, counts in history[len(self.xs):]:
            self.xs.append(float(turn))
            for group in POPULATION_GROUPS:
                self.groups[group].append(float(counts.get(group, 0)))
        for group, series in self.pop_series.items():
            dpg.set_value(series, [self.xs, self.groups[group]])
        dpg.set_value(self.ifn_shade, [self.imm_turns, self.ifn, [0.0] * len(self.ifn)])
        dpg.set_value(self.ifn_line, [self.imm_turns, self.ifn])
        dpg.set_value(self.ab_line, [self.imm_turns, self.antibodies])
        dpg.set_value(self.ab_stored_line, [self.imm_turns, self.antibodies_stored])
        if dpg.get_value(self.follow):
            for axis in (self.pop_x, self.pop_y, self.imm_x):
                dpg.fit_axis_data(axis)
            # Immune levels start at zero: keep the baseline at 0 instead of centering on it
            dpg.set_axis_limits(self.imm_y, 0, max(self.ifn + [1.0]) * 1.08)
            dpg.set_axis_limits(self.imm_y2, 0, max(self.antibodies + self.antibodies_stored + [1.0]) * 1.08)
        else:
            dpg.set_axis_limits_auto(self.imm_y)
            dpg.set_axis_limits_auto(self.imm_y2)

    def _on_scale(self, sender, app_data, user_data):
        dpg.configure_item(self.pop_y, scale=dpg.mvPlotScale_SymLog if app_data else dpg.mvPlotScale_Linear)
        if app_data:
            dpg.set_axis_ticks(self.pop_y, LOG_TICKS)
        else:
            dpg.reset_axis_ticks(self.pop_y)
        dpg.fit_axis_data(self.pop_y)

    def _on_tab(self, sender, app_data, user_data):
        self._redraw(force=True)

    def _refresh_milestones(self):
        dpg.delete_item(self.milestones, children_only=True)
        tracked = self.round.tracked_milestones()
        if not tracked:
            dpg.add_text("No milestones in this database.", parent=self.milestones, color=theme.TEXT_DIM)
        for status in tracked:
            m = status.milestone
            with dpg.group(horizontal=True, parent=self.milestones):
                dpg.add_text("●" if status.achieved else "○", color=theme.GOOD if status.achieved else theme.TEXT_DIM)
                dpg.add_text(m.name, color=theme.TEXT if status.achieved else theme.TEXT_DIM)
                dpg.add_text(f"+{m.reward_ep} EP", color=theme.GOLD if status.achieved else theme.TEXT_DIM)
            if m.description:
                with dpg.tooltip(dpg.last_container()):
                    dpg.add_text(m.description, wrap=320)

    def _refresh_table(self):
        dpg.delete_item(self.table_area, children_only=True)
        rows = {}
        for entry in self.snapshot.population:
            row = rows.setdefault((entry.name, entry.category, entry.is_polyprotein), [0] * len(LOCATIONS))
            if entry.location in LOCATIONS:
                row[LOCATIONS.index(entry.location)] += entry.count
        ordered = sorted(rows.items(), key=lambda item: -sum(item[1]))
        peak = max([c for _, counts in ordered for c in counts] + [1])
        dpg.add_text("Every entity by compartment. Cell shading grows with the count (log scale).",
                     parent=self.table_area, color=theme.TEXT_DIM)
        with dpg.table(parent=self.table_area, header_row=True, policy=dpg.mvTable_SizingStretchProp,
                       borders_innerV=True, borders_outerH=True, row_background=False,
                       scrollY=True, height=-1, freeze_rows=1) as table:
            dpg.add_table_column(label="Entity", init_width_or_weight=0.30)
            for location in LOCATIONS:
                dpg.add_table_column(label=location, init_width_or_weight=0.10)
            dpg.add_table_column(label="Total", init_width_or_weight=0.10)
            for row_index, ((name, category, is_poly), counts) in enumerate(ordered):
                color = theme.POLYPROTEIN_COLOR if is_poly else theme.category_color(category)
                with dpg.table_row():
                    dpg.add_text(name, color=color)
                    for column, count in enumerate(counts, start=1):
                        dpg.add_text(f"{count:,}" if count else "·",
                                     color=theme.TEXT if count else theme.TEXT_DIM)
                        if count:
                            strength = math.log10(count + 1) / math.log10(peak + 1)
                            dpg.highlight_table_cell(table, row_index, column,
                                                     theme.with_alpha(color, int(25 + 120 * strength)))
                    dpg.add_text(f"{sum(counts):,}")

    def _on_log_filter(self, sender, app_data, user_data):
        if self._batch is None:
            self._refresh_log()

    def _refresh_log(self):
        lines = self.round.log()
        needle = dpg.get_value(self.log_filter).strip().lower()
        if needle:
            lines = [line for line in lines if needle in line.lower()]
        dpg.set_value(self.log_text, "\n".join(reversed(lines[-800:])))


def _speed_label(speed: float) -> str:
    return f"{speed:g} turns/s"


def _run_turns(round_, wanted: int, budget: float) -> list:
    """Worker thread: run up to ``wanted`` turns, stopping after ``budget``
    seconds or when the round ends. Only this thread touches the round meanwhile."""
    results = []
    start = time.perf_counter()
    while len(results) < wanted:
        result = round_.step()
        results.append(result)
        if result.ended or time.perf_counter() - start >= budget:
            break
    return results


def _interferon_color(level: float):
    """Green when low, through orange, to red at the maximum."""
    stops = [(0.0, theme.GOOD), (0.5, theme.WARN), (1.0, theme.BAD)]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if level <= b:
            t = (level - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3)) + (255,)
    return theme.BAD


_bar_themes: dict = {}


def _bar_theme(color):
    key = tuple(color)
    if key not in _bar_themes:
        with dpg.theme() as bar:
            with dpg.theme_component(dpg.mvProgressBar):
                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, theme.darken(color, 0.15),
                                    category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (30, 36, 50, 255), category=dpg.mvThemeCat_Core)
        _bar_themes[key] = bar
    return _bar_themes[key]
