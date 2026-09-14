"""
Play Module for Viral Sandbox.
Where the virus simulation runs and players observe their virus infecting a cell.

This module is the *view*. All simulation rules live in simulation.py; this
window drives the engine from a Tk timer and redraws in response to the
engine's on_* callbacks.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from collections import defaultdict

from game_state import GameState
from models import CellLocation, EntityCategory
from simulation import SimulationEngine, SimulationState
from builder import BlueprintDialog


class PlayModule(tk.Toplevel):
    """Play module window where simulation runs."""

    WIN_THRESHOLD = SimulationEngine.WIN_THRESHOLD

    def __init__(self, parent, game_state: GameState,
                 on_return: Optional[Callable] = None,
                 window_mode: str = "maximized"):
        super().__init__(parent)

        self.game_state = game_state
        self.on_return_callback = on_return

        self.title("Viral Sandbox - Play Module")
        self.geometry("1400x900")
        self.minsize(1200, 700)
        if window_mode == "maximized":
            self.state('zoomed')

        # The engine owns all simulation rules and state; this window observes
        # it and redraws when it reports progress.
        self.engine = SimulationEngine(game_state)
        self.engine.on_turn_complete = self._update_display
        self.engine.on_game_end = self._on_game_end
        self.engine.on_milestone_achieved = self._update_milestone_display
        self.engine.on_active_milestones_changed = self._populate_milestones

        # Simulation timer
        self.sim_timer = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._create_ui()
        self._update_display()

    @property
    def sim_state(self) -> SimulationState:
        """Live simulation state, owned by the engine."""
        return self.engine.sim_state

    def _run_turn(self):
        """Advance the simulation by one turn, then schedule the next."""
        if not self.sim_state.is_running or self.sim_state.is_ended:
            return

        self.engine.run_turn()

        if not self.sim_state.is_ended:
            self._schedule_next_turn()

    def _on_game_end(self):
        """Engine reported that the run has ended."""
        if self.sim_state.extinction:
            self.status_var.set("Virus Extinct!")
        elif self.sim_state.is_victory:
            self.status_var.set("VICTORY!")
        self._show_end_dialog()

    def _on_close(self):
        """Handle window close."""
        if self.sim_timer:
            self.after_cancel(self.sim_timer)

        if not self.sim_state.is_ended:
            if messagebox.askyesno("End Round",
                                   "End this play round and return to Builder?"):
                self._end_round(early_exit=True)
        else:
            self._return_to_builder()

    def _create_ui(self):
        """Create the main UI layout."""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Top section - Turn info and status bars
        self._create_top_section(main_frame)

        # Main content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Left side - Entity display and graph
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._create_entity_display(left_frame)
        self._create_graph_display(left_frame)

        # Right side - Controls and milestones
        right_frame = ttk.Frame(content_frame, width=350)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_frame.pack_propagate(False)

        self._create_controls(right_frame)
        self._create_milestone_tracker(right_frame)

    def _create_top_section(self, parent):
        """Create the top section with turn info and status bars."""
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=tk.X, pady=(0, 5))

        # Turn counter
        turn_frame = ttk.Frame(top_frame)
        turn_frame.pack(side=tk.LEFT, padx=10)

        ttk.Label(turn_frame, text="Turn:", font=('TkDefaultFont', 12)).pack(side=tk.LEFT)
        self.turn_var = tk.StringVar(value="0")
        ttk.Label(turn_frame, textvariable=self.turn_var,
                  font=('TkDefaultFont', 14, 'bold')).pack(side=tk.LEFT, padx=5)

        # Entity count
        count_frame = ttk.Frame(top_frame)
        count_frame.pack(side=tk.LEFT, padx=20)

        ttk.Label(count_frame, text="Total Entities:").pack(side=tk.LEFT)
        self.entity_count_var = tk.StringVar(value="10")
        ttk.Label(count_frame, textvariable=self.entity_count_var,
                  font=('TkDefaultFont', 11, 'bold')).pack(side=tk.LEFT, padx=5)

        # Virion count (for win condition)
        virion_frame = ttk.Frame(top_frame)
        virion_frame.pack(side=tk.LEFT, padx=20)

        ttk.Label(virion_frame, text="Virions:").pack(side=tk.LEFT)
        self.virion_count_var = tk.StringVar(value="10")
        ttk.Label(virion_frame, textvariable=self.virion_count_var,
                  font=('TkDefaultFont', 11, 'bold'), foreground='purple').pack(side=tk.LEFT, padx=5)
        ttk.Label(virion_frame, text=f"/ {self.WIN_THRESHOLD}").pack(side=tk.LEFT)

        # Status bars frame
        bars_frame = ttk.Frame(top_frame)
        bars_frame.pack(side=tk.RIGHT, padx=10)

        # Interferon bar (using Canvas for dynamic color)
        ifn_frame = ttk.Frame(bars_frame)
        ifn_frame.pack(fill=tk.X, pady=2)

        ttk.Label(ifn_frame, text="Interferon:", width=12).pack(side=tk.LEFT)
        self.ifn_var = tk.StringVar(value="0")
        self.ifn_canvas = tk.Canvas(ifn_frame, width=200, height=20, bg='#e0e0e0',
                                    highlightthickness=1, highlightbackground='#999999')
        self.ifn_canvas.pack(side=tk.LEFT, padx=5)
        self.ifn_bar_rect = self.ifn_canvas.create_rectangle(0, 0, 0, 20, fill='#4caf50', outline='')
        ttk.Label(ifn_frame, textvariable=self.ifn_var, width=12).pack(side=tk.LEFT)

        # Antibody bar
        ab_frame = ttk.Frame(bars_frame)
        ab_frame.pack(fill=tk.X, pady=2)

        ttk.Label(ab_frame, text="Antibodies:", width=12).pack(side=tk.LEFT)
        self.ab_var = tk.StringVar(value="0 (0 stored)")
        self.ab_bar = ttk.Progressbar(ab_frame, length=200, maximum=100)
        self.ab_bar.pack(side=tk.LEFT, padx=5)
        ttk.Label(ab_frame, textvariable=self.ab_var, width=15).pack(side=tk.LEFT)

    def _create_entity_display(self, parent):
        """Create the entity display section."""
        frame = ttk.LabelFrame(parent, text="Entities by Location")
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # Canvas with scrollbar for entity bars
        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.entity_canvas = tk.Canvas(canvas_frame, bg='white')
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                                   command=self.entity_canvas.yview)

        self.entity_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.entity_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bind resize
        self.entity_canvas.bind('<Configure>', lambda e: self._draw_entity_bars())

    def _create_graph_display(self, parent):
        """Create the graph display section."""
        frame = ttk.LabelFrame(parent, text="Population Over Time")
        frame.pack(fill=tk.X, pady=(0, 5))

        # Main container with graph on left and controls on right
        main_frame = ttk.Frame(frame)
        main_frame.pack(fill=tk.X, padx=5, pady=5)

        # Graph canvas (left side)
        self.graph_canvas = tk.Canvas(main_frame, height=200, bg='white')
        self.graph_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Controls frame (right side)
        controls_frame = ttk.Frame(main_frame, width=120)
        controls_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        controls_frame.pack_propagate(False)

        # Display window dropdown
        ttk.Label(controls_frame, text="Display:", font=('TkDefaultFont', 9)).pack(anchor='w')
        self.graph_window_var = tk.StringVar(value="50")
        window_combo = ttk.Combobox(controls_frame, textvariable=self.graph_window_var,
                                     values=["10", "50", "100", "200", "All"],
                                     state='readonly', width=8)
        window_combo.pack(anchor='w', pady=(0, 10))
        window_combo.bind('<<ComboboxSelected>>', lambda e: self._draw_graph())

        # Filter section
        ttk.Label(controls_frame, text="Show:", font=('TkDefaultFont', 9)).pack(anchor='w')

        # Category filter checkboxes
        self.graph_filters = {}
        colors = [('Virion', 'purple'), ('RNA', 'green'),
                  ('DNA', 'blue'), ('Protein', 'orange'),
                  ('Antibodies', 'red')]
        for name, color in colors:
            var = tk.BooleanVar(value=True)
            self.graph_filters[name] = var
            cb_frame = ttk.Frame(controls_frame)
            cb_frame.pack(anchor='w')
            cb = ttk.Checkbutton(cb_frame, variable=var, command=self._draw_graph)
            cb.pack(side=tk.LEFT)
            ttk.Label(cb_frame, text="■", foreground=color).pack(side=tk.LEFT)
            ttk.Label(cb_frame, text=name, font=('TkDefaultFont', 8)).pack(side=tk.LEFT)

    def _create_controls(self, parent):
        """Create the simulation control section."""
        frame = ttk.LabelFrame(parent, text="Simulation Controls")
        frame.pack(fill=tk.X, pady=(0, 5))

        # Run/Stop button and speed controls on same row
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        # Run/Stop button (using tk.Button for color support)
        self.run_stop_btn = tk.Button(control_frame, text="Run", width=8,
                                       bg='#4caf50', fg='white', font=('TkDefaultFont', 10, 'bold'),
                                       activebackground='#45a049', activeforeground='white',
                                       command=self._toggle_simulation)
        self.run_stop_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Speed selection
        ttk.Label(control_frame, text="Speed:").pack(side=tk.LEFT, padx=(0, 5))
        self.speed_var = tk.StringVar(value="normal")

        speeds = [("Normal", "normal"), ("Fast", "fast"), ("Max", "max")]
        for text, value in speeds:
            ttk.Radiobutton(control_frame, text=text, variable=self.speed_var,
                           value=value, command=self._on_speed_change).pack(side=tk.LEFT, padx=2)

        # Action buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="View Log",
                   command=self._show_log).pack(side=tk.LEFT, padx=2)
        self.end_round_btn = tk.Button(btn_frame, text="End Round",
                                        command=self._request_end_round)
        self.end_round_btn.pack(side=tk.LEFT, padx=2)

        # Status
        self.status_var = tk.StringVar(value="Paused - Click Run to start")
        ttk.Label(frame, textvariable=self.status_var,
                  font=('TkDefaultFont', 10, 'italic')).pack(padx=5, pady=5)

    def _create_milestone_tracker(self, parent):
        """Create the milestone tracking section."""
        frame = ttk.LabelFrame(parent, text="Milestones")
        frame.pack(fill=tk.BOTH, expand=True)

        # Scrollable list of milestones
        canvas = tk.Canvas(frame, bg='white')
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        self.milestone_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas.create_window((0, 0), window=self.milestone_frame, anchor='nw')
        self.milestone_frame.bind('<Configure>',
                                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        self.milestone_canvas = canvas
        self._populate_milestones()

    def _populate_milestones(self):
        """Populate the milestone list with active and achieved milestones only.

        Only shows milestones that are:
        - Already achieved (shown with checkmark)
        - Currently active (prerequisites met, shown with circle)

        Milestones with unmet prerequisites are not shown.
        """
        for widget in self.milestone_frame.winfo_children():
            widget.destroy()

        self.milestone_labels = {}

        # Get milestones to display: achieved OR active
        milestones_to_show = []
        for milestone in self.game_state.database.milestones.values():
            is_achieved = milestone.id in self.game_state.achieved_milestones
            is_active = milestone.id in self.sim_state.active_milestone_ids
            if is_achieved or is_active:
                milestones_to_show.append(milestone)

        # Sort by ID for consistent ordering
        milestones_to_show.sort(key=lambda m: m.id)

        for milestone in milestones_to_show:
            frame = ttk.Frame(self.milestone_frame)
            frame.pack(fill=tk.X, padx=5, pady=2)

            # Check if already achieved
            achieved = milestone.id in self.game_state.achieved_milestones

            # Checkbox-style indicator
            indicator = "✓" if achieved else "○"
            color = "green" if achieved else "gray"

            lbl = ttk.Label(frame, text=indicator, foreground=color, width=2)
            lbl.pack(side=tk.LEFT)

            name_lbl = ttk.Label(frame, text=f"{milestone.name} (+{milestone.reward_ep} EP)")
            name_lbl.pack(side=tk.LEFT)

            self.milestone_labels[milestone.id] = (lbl, name_lbl)

    def _toggle_simulation(self):
        """Toggle simulation between running and paused."""
        if self.sim_state.is_running:
            # Stop the simulation
            self._stop_simulation()
        else:
            # Start the simulation
            self._start_simulation()

    def _start_simulation(self):
        """Start the simulation."""
        if self.sim_state.is_ended:
            return

        self.sim_state.is_running = True
        self.sim_state.speed = self.speed_var.get()

        # Update button to red "Stop"
        self.run_stop_btn.config(text="Stop", bg='#f44336',
                                  activebackground='#d32f2f')

        speed_text = self.speed_var.get().capitalize()
        self.status_var.set(f"Running ({speed_text})")
        self._schedule_next_turn()

    def _stop_simulation(self):
        """Stop/pause the simulation."""
        self.sim_state.is_running = False

        if self.sim_timer:
            self.after_cancel(self.sim_timer)
            self.sim_timer = None

        # Update button to green "Run"
        self.run_stop_btn.config(text="Run", bg='#4caf50',
                                  activebackground='#45a049')

        self.status_var.set("Paused")

    def _on_speed_change(self):
        """Handle speed control change."""
        speed = self.speed_var.get()
        self.sim_state.speed = speed

        # If running, update the status and reschedule with new speed
        if self.sim_state.is_running:
            if self.sim_timer:
                self.after_cancel(self.sim_timer)
                self.sim_timer = None

            speed_text = speed.capitalize()
            self.status_var.set(f"Running ({speed_text})")
            self._schedule_next_turn()

    def _schedule_next_turn(self):
        """Schedule the next simulation turn."""
        if not self.sim_state.is_running or self.sim_state.is_ended:
            return

        speed = self.sim_state.speed
        if speed == "normal":
            delay = 500  # ms
        elif speed == "fast":
            delay = 100
        elif speed == "max":
            delay = 1
        else:
            return

        self.sim_timer = self.after(delay, self._run_turn)


    def _update_milestone_display(self, milestone_id: int):
        """Update milestone display when achieved."""
        if milestone_id in self.milestone_labels:
            lbl, name_lbl = self.milestone_labels[milestone_id]
            lbl.configure(text="✓", foreground="green")

    def _update_display(self):
        """Update all display elements."""
        self.turn_var.set(str(self.sim_state.turn))

        # Count entities (including polyproteins)
        total = (sum(self.sim_state.entities.values()) +
                 sum(self.sim_state.new_entities.values()) +
                 sum(self.sim_state.polyproteins.values()) +
                 sum(self.sim_state.new_polyproteins.values()))
        self.entity_count_var.set(str(total))

        # Count virions
        virions = 0
        for (entity_id, location), count in self.sim_state.entities.items():
            entity = self.game_state.database.get_entity(entity_id)
            if entity and entity.category in [EntityCategory.VIRION.value,
                                               EntityCategory.VIRAL_COMPLEX.value]:
                virions += count
        for (entity_id, location), count in self.sim_state.new_entities.items():
            entity = self.game_state.database.get_entity(entity_id)
            if entity and entity.category in [EntityCategory.VIRION.value,
                                               EntityCategory.VIRAL_COMPLEX.value]:
                virions += count
        self.virion_count_var.set(str(virions))

        # Update status bars
        self._update_interferon_bar()

        stored = self.sim_state.antibody_stored
        active = self.sim_state.antibody_active
        self.ab_bar['value'] = min(100, active)
        self.ab_var.set(f"{active} ({stored:.0f} stored)")

        # Draw entity bars
        self._draw_entity_bars()

        # Draw graph
        self._draw_graph()

    def _update_interferon_bar(self):
        """Update the interferon bar with dynamic color based on level."""
        level = self.sim_state.interferon_level
        max_level = 100000

        # Calculate bar width (0 to 200 pixels)
        bar_width = int((level / max_level) * 200)
        bar_width = max(0, min(200, bar_width))

        # Calculate color: green (low) -> orange (mid) -> red (high)
        # Normalize level to 0-1 range
        ratio = level / max_level

        if ratio <= 0.5:
            # Green to orange (0% to 50%)
            # Green: #4caf50 (76, 175, 80) -> Orange: #ff9800 (255, 152, 0)
            t = ratio * 2  # 0 to 1 over first half
            r = int(76 + (255 - 76) * t)
            g = int(175 + (152 - 175) * t)
            b = int(80 + (0 - 80) * t)
        else:
            # Orange to red (50% to 100%)
            # Orange: #ff9800 (255, 152, 0) -> Red: #f44336 (244, 67, 54)
            t = (ratio - 0.5) * 2  # 0 to 1 over second half
            r = int(255 + (244 - 255) * t)
            g = int(152 + (67 - 152) * t)
            b = int(0 + (54 - 0) * t)

        color = f'#{r:02x}{g:02x}{b:02x}'

        # Update the canvas
        self.ifn_canvas.coords(self.ifn_bar_rect, 0, 0, bar_width, 20)
        self.ifn_canvas.itemconfig(self.ifn_bar_rect, fill=color)

        # Update the label
        self.ifn_var.set(f"{level:,.0f}")

    def _draw_entity_bars(self):
        """Draw entity bars on the canvas."""
        self.entity_canvas.delete("all")

        width = self.entity_canvas.winfo_width()
        if width < 10:
            width = 400

        # Group entities by location
        location_order = [
            CellLocation.EXTRACELLULAR.value,
            CellLocation.MEMBRANE.value,
            CellLocation.ENDOSOME.value,
            CellLocation.ER.value,
            CellLocation.CYTOSOL.value,
            CellLocation.NUCLEUS.value
        ]

        entities_by_location = defaultdict(list)
        all_entities = dict(self.sim_state.entities)
        for key, count in self.sim_state.new_entities.items():
            if key in all_entities:
                all_entities[key] += count
            else:
                all_entities[key] = count

        for (entity_id, location), count in all_entities.items():
            entities_by_location[location].append((entity_id, count, False))  # False = not polyprotein

        # Add polyproteins to cytosol
        all_polyproteins = dict(self.sim_state.polyproteins)
        for poly, count in self.sim_state.new_polyproteins.items():
            if poly in all_polyproteins:
                all_polyproteins[poly] += count
            else:
                all_polyproteins[poly] = count

        for poly, count in all_polyproteins.items():
            if count > 0:
                entities_by_location[CellLocation.CYTOSOL.value].append((poly, count, True))  # True = polyprotein

        # Find max count for scaling
        all_counts = [c for c in all_entities.values()] + [c for c in all_polyproteins.values()] + [50]
        max_count = max(all_counts)

        y = 10
        bar_height = 18
        text_area_width = 155  # Space reserved for entity names
        bar_start_x = 160  # Where bars begin

        for location in location_order:
            # Always show location header (even if empty)
            self.entity_canvas.create_text(10, y, text=location, anchor='w',
                                           font=('TkDefaultFont', 10, 'bold'))
            y += 20

            # Entity bars (if any entities in this location)
            if location in entities_by_location:
                for item, count, is_poly in sorted(entities_by_location[location],
                                                   key=lambda x: -x[1]):
                    if is_poly:
                        # Polyprotein - build display name using abbreviations if available
                        poly = item
                        protein_names = []
                        for eid in poly.protein_entity_ids:
                            entity = self.game_state.database.get_entity(eid)
                            if entity:
                                protein_names.append(entity.get_display_name(use_abbreviation=True))
                            else:
                                protein_names.append(f"ID:{eid}")
                        name = f"Poly ({', '.join(protein_names)})"
                        color = '#FF8C00'  # Dark orange for polyproteins
                    else:
                        entity_id = item
                        entity = self.game_state.database.get_entity(entity_id)
                        name = entity.name if entity else f"Entity {entity_id}"

                        # Category color
                        color = '#888888'
                        if entity:
                            cat = entity.category
                            if cat == EntityCategory.VIRION.value or cat == EntityCategory.VIRAL_COMPLEX.value:
                                color = 'purple'
                            elif cat == EntityCategory.RNA.value:
                                color = 'green'
                            elif cat == EntityCategory.DNA.value:
                                color = 'blue'
                            elif cat == EntityCategory.PROTEIN.value:
                                color = 'orange'

                    # Draw bar (compressed to leave more space for text)
                    max_bar_width = width - bar_start_x - 50  # Leave space for count text
                    bar_width = int((count / max_count) * max_bar_width)
                    bar_width = max(5, bar_width)

                    self.entity_canvas.create_rectangle(
                        bar_start_x, y, bar_start_x + bar_width, y + bar_height,
                        fill=color, outline=color)

                    # Entity name (truncate if needed)
                    display_name = name[:22] if len(name) > 22 else name
                    self.entity_canvas.create_text(
                        15, y + bar_height // 2, text=display_name, anchor='w',
                        font=('TkDefaultFont', 9))

                    # Count
                    self.entity_canvas.create_text(
                        bar_start_x + bar_width + 5, y + bar_height // 2, text=str(count),
                        anchor='w', font=('TkDefaultFont', 9))

                    y += bar_height + 2
            else:
                # Show "(empty)" for locations with no entities
                self.entity_canvas.create_text(15, y, text="(empty)", anchor='w',
                                               font=('TkDefaultFont', 9, 'italic'),
                                               fill='#888888')
                y += 18

            y += 8  # Space between locations

        # Update scroll region
        self.entity_canvas.configure(scrollregion=(0, 0, width, y + 20))

    def _draw_graph(self):
        """Draw the population graph."""
        self.graph_canvas.delete("all")

        width = self.graph_canvas.winfo_width()
        height = self.graph_canvas.winfo_height()

        if width < 10 or height < 10:
            width = 400
            height = 200

        margin_left = 45
        margin_right = 10
        margin_top = 15
        margin_bottom = 35  # More space for x-axis labels
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom

        if len(self.sim_state.history) < 2:
            return

        # Get display window from dropdown
        window_setting = self.graph_window_var.get()
        if window_setting == "All":
            history = self.sim_state.history[:]
        else:
            window_size = int(window_setting)
            history = self.sim_state.history[-window_size:]

        # Get enabled categories from filter
        enabled_categories = [cat for cat, var in self.graph_filters.items() if var.get()]

        # Find max value only for enabled categories, add 5% padding
        max_val = 10
        for turn, counts in history:
            for cat, count in counts.items():
                if cat in enabled_categories:
                    max_val = max(max_val, count)
        max_val = int(max_val * 1.05) + 1  # Add 5% padding

        # Get turn range for x-axis labels
        first_turn = history[0][0]
        last_turn = history[-1][0]

        # Draw axes
        self.graph_canvas.create_line(margin_left, height - margin_bottom,
                                       width - margin_right, height - margin_bottom, fill='gray')
        self.graph_canvas.create_line(margin_left, height - margin_bottom,
                                       margin_left, margin_top, fill='gray')

        # Draw Y-axis scale labels
        self.graph_canvas.create_text(margin_left - 5, height - margin_bottom,
                                       text="0", anchor='e', font=('TkDefaultFont', 8))
        self.graph_canvas.create_text(margin_left - 5, margin_top,
                                       text=str(max_val), anchor='e', font=('TkDefaultFont', 8))
        # Middle Y label
        self.graph_canvas.create_text(margin_left - 5, margin_top + graph_height // 2,
                                       text=str(max_val // 2), anchor='e', font=('TkDefaultFont', 8))

        # Draw X-axis labels (always 10 labels, dynamically spaced)
        if last_turn > first_turn:
            turn_range = last_turn - first_turn
            num_labels = 10
            for i in range(num_labels + 1):
                turn_label = first_turn + int(i * turn_range / num_labels)
                x = margin_left + (i / num_labels) * graph_width
                self.graph_canvas.create_text(x, height - margin_bottom + 12,
                                               text=str(turn_label), anchor='n',
                                               font=('TkDefaultFont', 8))
                # Small tick mark
                self.graph_canvas.create_line(x, height - margin_bottom,
                                               x, height - margin_bottom + 3, fill='gray')

        # X-axis label
        self.graph_canvas.create_text(margin_left + graph_width // 2, height - 5,
                                       text="Turn", anchor='n', font=('TkDefaultFont', 8))

        # Draw lines for each enabled category
        colors = {'Virion': 'purple', 'RNA': 'green', 'DNA': 'blue', 'Protein': 'orange', 'Antibodies': 'red'}

        for category, color in colors.items():
            if category not in enabled_categories:
                continue

            points = []
            for i, (turn, counts) in enumerate(history):
                x = margin_left + (i / max(1, len(history) - 1)) * graph_width
                y = height - margin_bottom - (counts.get(category, 0) / max_val) * graph_height
                points.append((x, y))

            if len(points) >= 2:
                for i in range(len(points) - 1):
                    self.graph_canvas.create_line(
                        points[i][0], points[i][1],
                        points[i+1][0], points[i+1][1],
                        fill=color, width=2)

    def _show_log(self):
        """Show the simulation log in a new window."""
        log_window = tk.Toplevel(self)
        log_window.title("Simulation Log")
        log_window.geometry("600x500")

        text = tk.Text(log_window, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_window, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        text.insert('1.0', '\n'.join(self.sim_state.log))
        text.configure(state='disabled')

    def _enter_review_mode(self):
        """Enter review mode after extinction - let the player inspect the round."""
        self.sim_state.is_running = False

        # Hide the Run/Stop button
        self.run_stop_btn.pack_forget()

        # Update status
        self.status_var.set("Round over - Review your results, then return to Builder")

        # Highlight the End Round button
        self.end_round_btn.configure(
            text="Return to Builder",
            bg='#2196f3', fg='white',
            font=('TkDefaultFont', 10, 'bold'),
            activebackground='#1976d2', activeforeground='white'
        )

    def _request_end_round(self):
        """Request to end the current round early."""
        if self.sim_state.is_ended:
            # Round already ended (extinction/review mode) - no confirmation needed
            self._end_round()
            return

        if messagebox.askyesno("End Round",
                               "End this play round and return to Builder?"):
            self._end_round(early_exit=True)

    def _show_end_dialog(self):
        """Show the end-of-round dialog."""
        if self.sim_timer:
            self.after_cancel(self.sim_timer)

        dialog = tk.Toplevel(self)
        dialog.title("Round Complete")
        dialog.geometry("400x350")
        dialog.transient(self)
        dialog.grab_set()

        # Handle window close button
        def on_dialog_close():
            dialog.destroy()
            if self.sim_state.extinction:
                self._enter_review_mode()
            else:
                self._end_round()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Result
        if self.sim_state.is_victory:
            result_text = "VICTORY!"
            result_color = "green"
        elif self.sim_state.extinction:
            result_text = "Virus Extinct"
            result_color = "red"
        else:
            result_text = "Round Ended"
            result_color = "black"

        ttk.Label(frame, text=result_text,
                  font=('TkDefaultFont', 16, 'bold'),
                  foreground=result_color).pack(pady=10)

        # Stats
        ttk.Label(frame, text=f"Turns survived: {self.sim_state.turn}").pack()

        # Milestones earned this round
        milestones_earned = [m for m in self.game_state.database.milestones.values()
                           if m.id in self.game_state.achieved_milestones]
        if milestones_earned:
            ttk.Label(frame, text="\nMilestones achieved:",
                      font=('TkDefaultFont', 10, 'bold')).pack()
            for m in milestones_earned:
                ttk.Label(frame, text=f"  • {m.name} (+{m.reward_ep} EP)").pack()

        ttk.Label(frame, text=f"\nTotal EP: {self.game_state.evolution_points}",
                  font=('TkDefaultFont', 11, 'bold')).pack()

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)

        if self.sim_state.is_victory:
            tk.Button(btn_frame, text="View Virus Blueprint",
                      command=lambda: BlueprintDialog(dialog, self.game_state),
                      bg='#9c27b0', fg='white',
                      font=('TkDefaultFont', 10, 'bold'),
                      activebackground='#7b1fa2', activeforeground='white'
                      ).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="View Log",
                   command=self._show_log).pack(side=tk.LEFT, padx=5)

        if self.sim_state.extinction:
            ttk.Button(btn_frame, text="Review Round",
                       command=lambda: [dialog.destroy(), self._enter_review_mode()]
                       ).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Return to Builder",
                   command=lambda: [dialog.destroy(), self._end_round()]).pack(side=tk.LEFT, padx=5)

    def _end_round(self, early_exit: bool = False):
        """End the current round and return to builder."""
        if self.sim_timer:
            self.after_cancel(self.sim_timer)

        self.sim_state.is_ended = True
        self.sim_state.is_running = False

        if early_exit:
            self.sim_state.log.append("\n=== Round ended early ===")

        self._return_to_builder()

    def _return_to_builder(self):
        """Return to the builder module."""
        # Call callback first (while this window still exists)
        if self.on_return_callback:
            self.on_return_callback(victory=self.sim_state.is_victory)

        # Then destroy this window
        self.destroy()
