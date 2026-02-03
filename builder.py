"""
Builder Module for Viral Sandbox.
Where players manage genes and configure their virus.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from game_state import GameState, VirusConfig
from models import Gene, Effect


class BuilderModule(tk.Toplevel):
    """Builder module window."""

    def __init__(self, parent, game_state: GameState,
                 on_play: Optional[Callable] = None,
                 on_quit: Optional[Callable] = None):
        super().__init__(parent)

        self.game_state = game_state
        self.on_play_callback = on_play
        self.on_quit_callback = on_quit

        self.title("Viral Sandbox - Builder Module")
        self.geometry("1400x900")
        self.minsize(1200, 700)

        # Track expanded genes in tree views
        self.available_expanded = set()
        self.installed_expanded = set()

        # Currently selected item
        self.selected_item = None  # ('gene', id) or ('effect', id)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._create_ui()
        self._refresh_all()

    def _on_close(self):
        """Handle window close."""
        if messagebox.askyesno("Quit Game", "Are you sure you want to quit the current game?"):
            if self.on_quit_callback:
                self.on_quit_callback()
            self.destroy()

    def _create_ui(self):
        """Create the main UI layout."""
        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Status bar at top
        self._create_status_bar(main_frame)

        # Top section (1/3) - Virus configuration
        top_frame = ttk.LabelFrame(main_frame, text="Virus Configuration")
        top_frame.pack(fill=tk.X, pady=(0, 5))
        self._create_config_section(top_frame)

        # Bottom section (2/3) - Three panels
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid for three equal columns
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)
        bottom_frame.columnconfigure(2, weight=1)
        bottom_frame.rowconfigure(0, weight=1)

        # Left panel - Available genes
        left_frame = ttk.LabelFrame(bottom_frame, text="Available Genes (Hand)")
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 2))
        self._create_available_panel(left_frame)

        # Center panel - Installed genes
        center_frame = ttk.LabelFrame(bottom_frame, text="Installed Genes")
        center_frame.grid(row=0, column=1, sticky='nsew', padx=2)
        self._create_installed_panel(center_frame)

        # Right panel - Details
        right_frame = ttk.LabelFrame(bottom_frame, text="Details")
        right_frame.grid(row=0, column=2, sticky='nsew', padx=(2, 0))
        self._create_details_panel(right_frame)

    def _create_status_bar(self, parent):
        """Create the status bar showing EP and round info."""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=(0, 5))

        # EP display
        self.ep_var = tk.StringVar()
        ep_label = ttk.Label(status_frame, textvariable=self.ep_var,
                            font=('TkDefaultFont', 12, 'bold'))
        ep_label.pack(side=tk.LEFT, padx=10)

        # Round display
        self.round_var = tk.StringVar()
        round_label = ttk.Label(status_frame, textvariable=self.round_var,
                               font=('TkDefaultFont', 12))
        round_label.pack(side=tk.LEFT, padx=10)

        # Genome length display
        self.genome_var = tk.StringVar()
        genome_label = ttk.Label(status_frame, textvariable=self.genome_var,
                                font=('TkDefaultFont', 10))
        genome_label.pack(side=tk.LEFT, padx=10)

        # Play round button
        play_btn = ttk.Button(status_frame, text="Start Play Round",
                             command=self._on_play_round)
        play_btn.pack(side=tk.RIGHT, padx=10)

        # View blueprint button
        blueprint_btn = ttk.Button(status_frame, text="View Virus Blueprint",
                                  command=self._show_blueprint)
        blueprint_btn.pack(side=tk.RIGHT, padx=5)

    def _create_config_section(self, parent):
        """Create the virus configuration section."""
        config_frame = ttk.Frame(parent, padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True)

        # Left side - genome visual representation
        visual_frame = ttk.Frame(config_frame)
        visual_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.genome_display_var = tk.StringVar(value="No genome configured")
        genome_display = ttk.Label(visual_frame, textvariable=self.genome_display_var,
                                   font=('Courier', 16, 'bold'))
        genome_display.pack(pady=10)

        # Genome visualization canvas (taller to accommodate ORF indicators)
        self.genome_canvas = tk.Canvas(visual_frame, height=115, bg='white')
        self.genome_canvas.pack(fill=tk.X, padx=20, pady=5)

        # Right side - configuration options
        options_frame = ttk.Frame(config_frame)
        options_frame.pack(side=tk.RIGHT, padx=20)

        # Nucleic acid type
        row = 0
        ttk.Label(options_frame, text="Nucleic Acid:").grid(row=row, column=0, sticky='w', pady=2)
        self.nucleic_acid_var = tk.StringVar(value="RNA")
        na_frame = ttk.Frame(options_frame)
        na_frame.grid(row=row, column=1, sticky='w', pady=2)
        ttk.Radiobutton(na_frame, text="RNA", variable=self.nucleic_acid_var,
                       value="RNA", command=self._on_config_change).pack(side=tk.LEFT)
        ttk.Radiobutton(na_frame, text="DNA", variable=self.nucleic_acid_var,
                       value="DNA", command=self._on_config_change).pack(side=tk.LEFT)

        # Strandedness
        row += 1
        ttk.Label(options_frame, text="Strandedness:").grid(row=row, column=0, sticky='w', pady=2)
        self.strandedness_var = tk.StringVar(value="single")
        strand_frame = ttk.Frame(options_frame)
        strand_frame.grid(row=row, column=1, sticky='w', pady=2)
        ttk.Radiobutton(strand_frame, text="Single-stranded", variable=self.strandedness_var,
                       value="single", command=self._on_config_change).pack(side=tk.LEFT)
        ttk.Radiobutton(strand_frame, text="Double-stranded", variable=self.strandedness_var,
                       value="double", command=self._on_config_change).pack(side=tk.LEFT)

        # Polarity (only for single-stranded)
        row += 1
        ttk.Label(options_frame, text="Polarity:").grid(row=row, column=0, sticky='w', pady=2)
        self.polarity_var = tk.StringVar(value="positive")
        self.polarity_frame = ttk.Frame(options_frame)
        self.polarity_frame.grid(row=row, column=1, sticky='w', pady=2)
        ttk.Radiobutton(self.polarity_frame, text="Positive (+)", variable=self.polarity_var,
                       value="positive", command=self._on_config_change).pack(side=tk.LEFT)
        ttk.Radiobutton(self.polarity_frame, text="Negative (-)", variable=self.polarity_var,
                       value="negative", command=self._on_config_change).pack(side=tk.LEFT)

        # Virion type
        row += 1
        ttk.Label(options_frame, text="Virion Type:").grid(row=row, column=0, sticky='w', pady=2)
        self.virion_type_var = tk.StringVar(value="Enveloped")
        virion_frame = ttk.Frame(options_frame)
        virion_frame.grid(row=row, column=1, sticky='w', pady=2)
        ttk.Radiobutton(virion_frame, text="Enveloped", variable=self.virion_type_var,
                       value="Enveloped", command=self._on_config_change).pack(side=tk.LEFT)
        ttk.Radiobutton(virion_frame, text="Unenveloped", variable=self.virion_type_var,
                       value="Unenveloped", command=self._on_config_change).pack(side=tk.LEFT)

        # Lock config button
        row += 1
        self.lock_btn_frame = ttk.Frame(options_frame)
        self.lock_btn_frame.grid(row=row, column=0, columnspan=2, pady=10)

        self.config_status_var = tk.StringVar()
        ttk.Label(self.lock_btn_frame, textvariable=self.config_status_var).pack(side=tk.LEFT, padx=5)

        self.lock_btn = ttk.Button(self.lock_btn_frame, text=f"Lock Configuration ({self.game_state.config_lock_cost} EP)",
                                  command=self._lock_config)
        self.lock_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(self.lock_btn_frame, text="Reset Changes",
                  command=self._reset_config).pack(side=tk.LEFT, padx=5)

    def _create_available_panel(self, parent):
        """Create the available genes panel with tree view."""
        # Buttons at bottom - pack FIRST so they always show
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        self.install_btn = ttk.Button(btn_frame, text="Install Gene ->",
                                     command=self._install_gene)
        self.install_btn.pack(side=tk.LEFT, padx=5)

        # Scrollable frame - pack AFTER buttons so it fills remaining space
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.available_frame = ttk.Frame(canvas)

        self.available_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.available_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _create_installed_panel(self, parent):
        """Create the installed genes panel with tree view."""
        # Buttons at bottom - pack FIRST so they always show
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        self.remove_btn = ttk.Button(btn_frame, text="<- Remove",
                                    command=self._remove_item)
        self.remove_btn.pack(side=tk.LEFT, padx=5)

        # Add ORF button
        self.add_orf_btn = ttk.Button(btn_frame, text="+ Add ORF",
                                      command=self._add_orf)
        self.add_orf_btn.pack(side=tk.LEFT, padx=5)

        # Add Terminator button
        self.add_term_btn = ttk.Button(btn_frame, text="+ Add Terminator",
                                       command=self._add_terminator)
        self.add_term_btn.pack(side=tk.LEFT, padx=5)

        # Ordering buttons
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Label(btn_frame, text="Order:").pack(side=tk.LEFT, padx=2)
        self.move_up_btn = ttk.Button(btn_frame, text="Up", width=5,
                                      command=self._move_item_up)
        self.move_up_btn.pack(side=tk.LEFT, padx=2)
        self.move_down_btn = ttk.Button(btn_frame, text="Down", width=5,
                                        command=self._move_item_down)
        self.move_down_btn.pack(side=tk.LEFT, padx=2)

        # Scrollable frame - pack AFTER buttons so it fills remaining space
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.installed_frame = ttk.Frame(canvas)

        self.installed_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.installed_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _create_details_panel(self, parent):
        """Create the details panel."""
        self.details_text = tk.Text(parent, wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=scrollbar.set)

        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure text tags for formatting
        self.details_text.tag_configure("title", font=('TkDefaultFont', 12, 'bold'))
        self.details_text.tag_configure("header", font=('TkDefaultFont', 10, 'bold'))
        self.details_text.tag_configure("value", font=('TkDefaultFont', 10))

    def _refresh_all(self):
        """Refresh all UI elements."""
        self._update_status()
        self._update_config_ui()
        self._update_available_genes()
        self._update_installed_genes()
        self._update_genome_visual()
        self._update_move_buttons()

    def _update_status(self):
        """Update the status bar."""
        self.ep_var.set(f"Evolution Points: {self.game_state.evolution_points}")
        self.round_var.set(f"Round: {self.game_state.current_round}/{self.game_state.max_rounds}")
        total_length = self.game_state.get_total_genome_length()
        self.genome_var.set(f"Genome Length: {total_length:,} bp")

    def _update_config_ui(self):
        """Update the configuration UI to match game state."""
        config = self.game_state.pending_config

        self.nucleic_acid_var.set(config.nucleic_acid)
        self.strandedness_var.set(config.strandedness)
        self.polarity_var.set(config.polarity)
        self.virion_type_var.set(config.virion_type)

        # Update polarity visibility
        self._update_polarity_state()

        # Update config status
        if self.game_state.virus_config.is_locked:
            self.config_status_var.set(f"Locked: {self.game_state.virus_config.get_genome_string()}")
        else:
            self.config_status_var.set("Not locked (using defaults)")

        if self.game_state.has_pending_changes():
            self.config_status_var.set(self.config_status_var.get() + " - UNSAVED CHANGES")

    def _update_polarity_state(self):
        """Enable/disable polarity options based on strandedness."""
        state = 'normal' if self.strandedness_var.get() == 'single' else 'disabled'
        for child in self.polarity_frame.winfo_children():
            child.configure(state=state)

    def _on_config_change(self):
        """Handle configuration change."""
        self._update_polarity_state()

        # Update pending config
        self.game_state.pending_config.nucleic_acid = self.nucleic_acid_var.get()
        self.game_state.pending_config.strandedness = self.strandedness_var.get()
        self.game_state.pending_config.polarity = self.polarity_var.get()
        self.game_state.pending_config.virion_type = self.virion_type_var.get()

        self._update_config_ui()
        self._update_genome_visual()

    def _lock_config(self):
        """Lock in the current configuration."""
        can_lock, reason = self.game_state.can_lock_config()
        if not can_lock:
            messagebox.showerror("Cannot Lock", reason)
            return

        # Update pending config from UI
        self.game_state.pending_config.nucleic_acid = self.nucleic_acid_var.get()
        self.game_state.pending_config.strandedness = self.strandedness_var.get()
        self.game_state.pending_config.polarity = self.polarity_var.get()
        self.game_state.pending_config.virion_type = self.virion_type_var.get()

        success, message = self.game_state.lock_config()
        if success:
            self._refresh_all()
            messagebox.showinfo("Configuration Locked", message)
        else:
            messagebox.showerror("Error", message)

    def _reset_config(self):
        """Reset pending config to locked config."""
        self.game_state.reset_pending_config()
        self._update_config_ui()
        self._update_genome_visual()

    def _update_genome_visual(self):
        """Update the genome visualization."""
        config = self.game_state.pending_config
        genome_str = config.get_genome_string()
        total_length = self.game_state.get_total_genome_length()

        # Update the text display
        if total_length > 0:
            self.genome_display_var.set(f"Genome: {genome_str} | {config.virion_type} | {total_length:,} bp")
        else:
            self.genome_display_var.set(f"Genome: {genome_str} | {config.virion_type} | No genes installed")

        # Draw genome on canvas
        self.genome_canvas.delete("all")
        width = self.genome_canvas.winfo_width()
        if width < 10:
            width = 400

        height = 115
        orf_area_height = 30  # Space for ORF indicators at top
        genome_center_y = orf_area_height + 40  # Center of genome area

        # If no genes installed, show placeholder message
        if total_length == 0:
            self.genome_canvas.create_text(
                width // 2, height // 2,
                text="Install genes to see genome structure",
                font=('TkDefaultFont', 11, 'italic'),
                fill='#888888'
            )
            return

        # Calculate drawing area
        left_margin = 50
        right_margin = 50
        available_width = width - left_margin - right_margin

        # Determine if we need to flip 5'/3' labels
        # Flip for negative-strand RNA or any DNA genome (they represent the template/antisense strand)
        is_flipped = (config.nucleic_acid == "DNA" or
                      (config.nucleic_acid == "RNA" and
                       config.strandedness == "single" and
                       config.polarity == "negative"))

        # Draw 5' and 3' labels (flipped for negative-strand RNA or DNA)
        left_label = "3'" if is_flipped else "5'"
        right_label = "5'" if is_flipped else "3'"

        self.genome_canvas.create_text(
            left_margin - 5, genome_center_y,
            text=left_label, font=('TkDefaultFont', 12, 'bold'),
            fill='#333333', anchor='e'
        )
        self.genome_canvas.create_text(
            width - right_margin + 5, genome_center_y,
            text=right_label, font=('TkDefaultFont', 12, 'bold'),
            fill='#333333', anchor='w'
        )

        # Draw DNA/RNA backbone
        strand_color = "#2196F3" if config.nucleic_acid == "DNA" else "#4CAF50"

        if config.strandedness == "double":
            # Double strand backbone
            self.genome_canvas.create_line(
                left_margin, genome_center_y - 12,
                width - right_margin, genome_center_y - 12,
                fill=strand_color, width=3
            )
            self.genome_canvas.create_line(
                left_margin, genome_center_y + 12,
                width - right_margin, genome_center_y + 12,
                fill=strand_color, width=3
            )
        else:
            # Single strand backbone
            self.genome_canvas.create_line(
                left_margin, genome_center_y,
                width - right_margin, genome_center_y,
                fill=strand_color, width=3
            )

            # Polarity indicator at 3' end
            polarity_x = width - right_margin + 25
            if config.polarity == "positive":
                self.genome_canvas.create_text(
                    polarity_x, genome_center_y, text="(+)",
                    font=('TkDefaultFont', 10, 'bold'), fill='green'
                )
            else:  # negative
                self.genome_canvas.create_text(
                    polarity_x, genome_center_y, text="(-)",
                    font=('TkDefaultFont', 10, 'bold'), fill='red'
                )

        # Build gene position map (for ORF visualization)
        # Map gene_id to (x_start, x_end, color_index)
        # Also track terminator positions for visualization
        gene_positions = {}
        terminator_positions = {}  # Map terminator name to x position
        colors = ['#FF5722', '#9C27B0', '#00BCD4', '#FFEB3B', '#E91E63',
                  '#8BC34A', '#FF9800', '#3F51B5', '#009688', '#F44336']
        x_pos = left_margin
        color_idx = 0

        for item in self.game_state.installed_genes:
            if self.game_state.is_terminator(item):
                # Track terminator position (at current x position)
                terminator_positions[item] = x_pos
            elif not self.game_state.is_orf(item):
                gene = self.game_state.get_gene(item)
                if gene:
                    # Calculate proportional width
                    gene_width = int((gene.length / total_length) * available_width)
                    if gene_width < 10:
                        gene_width = 10

                    gene_positions[item] = (x_pos, x_pos + gene_width, color_idx)

                    color = colors[color_idx % len(colors)]

                    # Check if this gene is selected
                    is_selected = (self.selected_item and
                                  self.selected_item[0] == 'gene' and
                                  self.selected_item[1] == item)
                    outline_color = '#0066cc' if is_selected else 'black'
                    outline_width = 3 if is_selected else 1

                    if config.strandedness == "double":
                        self.genome_canvas.create_rectangle(
                            x_pos, genome_center_y - 10,
                            x_pos + gene_width, genome_center_y + 10,
                            fill=color, outline=outline_color, width=outline_width
                        )
                    else:
                        self.genome_canvas.create_rectangle(
                            x_pos, genome_center_y - 8,
                            x_pos + gene_width, genome_center_y + 8,
                            fill=color, outline=outline_color, width=outline_width
                        )

                    # Add gene name label if wide enough
                    if gene_width > 40:
                        # Use abbreviation if available, otherwise truncate name
                        display_name = gene.get_display_name(use_abbreviation=True)
                        if len(display_name) > 10:
                            display_name = display_name[:8] + "..."
                        self.genome_canvas.create_text(
                            x_pos + gene_width // 2, genome_center_y,
                            text=display_name,
                            font=('TkDefaultFont', 8),
                            fill='white' if self._is_dark_color(color) else 'black'
                        )

                    x_pos += gene_width
                    color_idx += 1

        # Draw ORF indicators above the genome
        orf_structure = self.game_state.get_orf_structure()
        orf_colors = ['#cc5500', '#0055cc', '#00cc55', '#cc0055', '#5500cc']

        for orf_idx, orf_info in enumerate(orf_structure):
            orf_name = orf_info['orf']
            orf_genes = orf_info['genes']

            if not orf_genes:
                continue  # Skip ORFs with no genes

            # Find the x positions for this ORF's genes
            orf_x_start = None
            orf_x_end = None
            for gene_id in orf_genes:
                if gene_id in gene_positions:
                    x_start, x_end, _ = gene_positions[gene_id]
                    if orf_x_start is None or x_start < orf_x_start:
                        orf_x_start = x_start
                    if orf_x_end is None or x_end > orf_x_end:
                        orf_x_end = x_end

            if orf_x_start is not None and orf_x_end is not None:
                orf_color = orf_colors[orf_idx % len(orf_colors)]

                # Check if this ORF is selected
                is_orf_selected = (self.selected_item and
                                   self.selected_item[0] == 'orf' and
                                   self.selected_item[1] == orf_name)
                line_width = 4 if is_orf_selected else 2

                # Draw ORF bracket/span
                orf_y = 12 + (orf_idx % 2) * 12  # Alternate y positions to avoid overlap
                self.genome_canvas.create_line(
                    orf_x_start, orf_y,
                    orf_x_end, orf_y,
                    fill=orf_color, width=line_width
                )
                # Draw end caps
                self.genome_canvas.create_line(
                    orf_x_start, orf_y - 4,
                    orf_x_start, orf_y + 4,
                    fill=orf_color, width=line_width
                )
                self.genome_canvas.create_line(
                    orf_x_end, orf_y - 4,
                    orf_x_end, orf_y + 4,
                    fill=orf_color, width=line_width
                )

                # Draw ORF label
                label_x = (orf_x_start + orf_x_end) // 2
                self.genome_canvas.create_text(
                    label_x, orf_y - 8,
                    text=orf_name,
                    font=('TkDefaultFont', 8, 'bold'),
                    fill=orf_color
                )

        # Draw Terminator indicators (vertical red lines)
        for term_name, term_x in terminator_positions.items():
            # Check if this terminator is selected
            is_term_selected = (self.selected_item and
                               self.selected_item[0] == 'terminator' and
                               self.selected_item[1] == term_name)
            line_width = 4 if is_term_selected else 2
            term_color = '#cc0000'

            # Draw vertical line through the genome
            if config.strandedness == "double":
                self.genome_canvas.create_line(
                    term_x, genome_center_y - 15,
                    term_x, genome_center_y + 15,
                    fill=term_color, width=line_width
                )
            else:
                self.genome_canvas.create_line(
                    term_x, genome_center_y - 12,
                    term_x, genome_center_y + 12,
                    fill=term_color, width=line_width
                )

            # Draw small "T" or stop indicator above
            self.genome_canvas.create_text(
                term_x, genome_center_y - 20,
                text="T",
                font=('TkDefaultFont', 8, 'bold'),
                fill=term_color
            )

        # Draw length indicator below
        self.genome_canvas.create_text(
            width // 2, height - 5,
            text=f"{total_length:,} bp",
            font=('TkDefaultFont', 9),
            fill='#666666'
        )

    def _is_dark_color(self, hex_color: str) -> bool:
        """Check if a hex color is dark (for text contrast)."""
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Calculate luminance
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.5

    def _update_available_genes(self):
        """Update the available genes tree view."""
        # Clear existing
        for widget in self.available_frame.winfo_children():
            widget.destroy()

        for gene_id in self.game_state.available_genes:
            gene = self.game_state.get_gene(gene_id)
            if gene:
                self._create_gene_entry(self.available_frame, gene, 'available')

    def _update_installed_genes(self):
        """Update the installed genes tree view."""
        # Clear existing
        for widget in self.installed_frame.winfo_children():
            widget.destroy()

        for item in self.game_state.installed_genes:
            if self.game_state.is_orf(item):
                self._create_orf_entry(self.installed_frame, item)
            elif self.game_state.is_terminator(item):
                self._create_terminator_entry(self.installed_frame, item)
            else:
                gene = self.game_state.get_gene(item)
                if gene:
                    self._create_gene_entry(self.installed_frame, gene, 'installed')

    def _create_gene_entry(self, parent, gene: Gene, panel: str):
        """Create a gene entry with expandable effects."""
        expanded_set = self.available_expanded if panel == 'available' else self.installed_expanded
        is_expanded = gene.id in expanded_set

        # Check if this gene is selected
        is_selected = (self.selected_item and
                       self.selected_item[0] == 'gene' and
                       self.selected_item[1] == gene.id)

        # Gene frame with selection highlighting
        gene_frame = tk.Frame(parent)
        if is_selected:
            gene_frame.configure(bg='#cce5ff', relief=tk.SOLID, borderwidth=1)
        gene_frame.pack(fill=tk.X, padx=2, pady=1)

        # Expand/collapse button
        expand_text = "[-]" if is_expanded else "[+]"
        expand_btn = ttk.Button(gene_frame, text=expand_text, width=3,
                               command=lambda: self._toggle_gene(gene.id, panel))
        expand_btn.pack(side=tk.LEFT)

        # Check if gene is genome-incompatible (only for installed panel)
        is_genome_incompatible = (panel == 'installed' and
                                   not self.game_state.is_gene_genome_compatible(gene))

        # Gene info with color based on affordability, selection, and genome compatibility
        font_style = ('TkDefaultFont', 10, 'italic') if is_genome_incompatible else None
        if is_selected:
            bg_color = '#cce5ff'
            fg_color = '#004085'
        elif panel == 'available':
            bg_color = gene_frame.cget('bg')
            fg_color = 'blue' if gene.install_cost <= self.game_state.evolution_points else 'red'
        else:
            bg_color = gene_frame.cget('bg')
            fg_color = 'red' if is_genome_incompatible else 'dark green'

        # Add UTR indicator if applicable
        utr_indicator = " [UTR]" if gene.is_utr else ""
        # Add genome incompatibility indicator
        genome_indicator = " - Wrong genome type" if is_genome_incompatible else ""
        gene_text = f"({gene.set_name}) {gene.name} [{gene.install_cost} EP]{utr_indicator}{genome_indicator}"

        gene_label = tk.Label(gene_frame, text=gene_text, cursor="hand2",
                             fg=fg_color, bg=bg_color if is_selected else gene_frame.cget('bg'))
        if font_style:
            gene_label.configure(font=font_style)
        gene_label.pack(side=tk.LEFT, padx=5)
        gene_label.bind("<Button-1>", lambda e, g=gene, p=panel: self._select_gene(g, p))

        # Show effects if expanded
        if is_expanded:
            effects_frame = tk.Frame(parent)
            if is_selected:
                effects_frame.configure(bg='#e6f2ff')
            effects_frame.pack(fill=tk.X, padx=20, pady=1)

            for effect_id in gene.effect_ids:
                effect = self.game_state.get_effect(effect_id)
                if effect:
                    effect_entry = tk.Frame(effects_frame)
                    if is_selected:
                        effect_entry.configure(bg='#e6f2ff')
                    effect_entry.pack(fill=tk.X, pady=1)

                    lbl = tk.Label(effect_entry, text="|-")
                    if is_selected:
                        lbl.configure(bg='#e6f2ff')
                    lbl.pack(side=tk.LEFT)

                    effect_label = tk.Label(effect_entry,
                                           text=f"{effect.name} ({effect.effect_type})",
                                           cursor="hand2", fg='#666666')
                    if is_selected:
                        effect_label.configure(bg='#e6f2ff')
                    effect_label.pack(side=tk.LEFT, padx=5)
                    effect_label.bind("<Button-1>", lambda e, ef=effect: self._select_effect(ef))

    def _create_orf_entry(self, parent, orf_name: str):
        """Create an ORF entry in the installed list."""
        # Check if this ORF is selected
        is_selected = (self.selected_item and
                       self.selected_item[0] == 'orf' and
                       self.selected_item[1] == orf_name)

        # ORF frame with selection highlighting
        orf_frame = tk.Frame(parent)
        if is_selected:
            orf_frame.configure(bg='#ffe6cc', relief=tk.SOLID, borderwidth=1)
        else:
            orf_frame.configure(bg='#fff3e6')
        orf_frame.pack(fill=tk.X, padx=2, pady=1)

        # ORF indicator
        orf_indicator = tk.Label(orf_frame, text="[ORF]", font=('TkDefaultFont', 9, 'bold'),
                                fg='#cc5500', bg=orf_frame.cget('bg'))
        orf_indicator.pack(side=tk.LEFT, padx=2)

        # ORF name
        orf_label = tk.Label(orf_frame, text=orf_name, cursor="hand2",
                            fg='#cc5500', bg=orf_frame.cget('bg'),
                            font=('TkDefaultFont', 10, 'bold'))
        orf_label.pack(side=tk.LEFT, padx=5)
        orf_label.bind("<Button-1>", lambda e, name=orf_name: self._select_orf(name))

        # Show genes covered by this ORF
        orf_structure = self.game_state.get_orf_structure()
        genes_under_orf = []
        for orf_info in orf_structure:
            if orf_info['orf'] == orf_name:
                genes_under_orf = orf_info['genes']
                break

        if genes_under_orf:
            count_label = tk.Label(orf_frame, text=f"({len(genes_under_orf)} genes)",
                                  fg='#888888', bg=orf_frame.cget('bg'),
                                  font=('TkDefaultFont', 9))
            count_label.pack(side=tk.LEFT)

    def _create_terminator_entry(self, parent, term_name: str):
        """Create a Terminator entry in the installed list."""
        # Check if this Terminator is selected
        is_selected = (self.selected_item and
                       self.selected_item[0] == 'terminator' and
                       self.selected_item[1] == term_name)

        # Terminator frame with selection highlighting
        term_frame = tk.Frame(parent)
        if is_selected:
            term_frame.configure(bg='#ffe6e6', relief=tk.SOLID, borderwidth=1)
        else:
            term_frame.configure(bg='#fff0f0')
        term_frame.pack(fill=tk.X, padx=2, pady=1)

        # Terminator indicator
        term_indicator = tk.Label(term_frame, text="[STOP]", font=('TkDefaultFont', 9, 'bold'),
                                 fg='#cc0000', bg=term_frame.cget('bg'))
        term_indicator.pack(side=tk.LEFT, padx=2)

        # Terminator name
        term_label = tk.Label(term_frame, text=term_name, cursor="hand2",
                             fg='#cc0000', bg=term_frame.cget('bg'),
                             font=('TkDefaultFont', 10, 'bold'))
        term_label.pack(side=tk.LEFT, padx=5)
        term_label.bind("<Button-1>", lambda e, name=term_name: self._select_terminator(name))

    def _select_terminator(self, term_name: str):
        """Select a Terminator and show its details."""
        self.selected_item = ('terminator', term_name)
        self._show_terminator_details(term_name)
        # Refresh gene lists to show selection
        self._update_available_genes()
        self._update_installed_genes()
        self._update_genome_visual()
        self._update_move_buttons()

    def _show_terminator_details(self, term_name: str):
        """Show Terminator details in the details panel."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete('1.0', tk.END)

        self.details_text.insert(tk.END, f"{term_name}\n", "title")
        self.details_text.insert(tk.END, f"\nType: ", "header")
        self.details_text.insert(tk.END, "Terminator\n", "value")

        self.details_text.insert(tk.END, f"\nRemoval Cost: ", "header")
        self.details_text.insert(tk.END, "Free\n", "value")

        self.details_text.insert(tk.END, f"\nDescription:\n", "header")
        self.details_text.insert(tk.END, "Terminators mark the end of Open Reading Frames (ORFs). "
                                        "All ORFs that precede this terminator will stop at this point. "
                                        "Terminators can be removed for free.\n", "value")

        self.details_text.config(state=tk.DISABLED)

    def _select_orf(self, orf_name: str):
        """Select an ORF and show its details."""
        self.selected_item = ('orf', orf_name)
        self._show_orf_details(orf_name)
        # Refresh gene lists to show selection
        self._update_available_genes()
        self._update_installed_genes()
        self._update_genome_visual()
        self._update_move_buttons()

    def _show_orf_details(self, orf_name: str):
        """Show ORF details in the details panel."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete('1.0', tk.END)

        self.details_text.insert(tk.END, f"{orf_name}\n", "title")
        self.details_text.insert(tk.END, f"\nType: ", "header")
        self.details_text.insert(tk.END, "Open Reading Frame\n", "value")

        # Find genes under this ORF
        orf_structure = self.game_state.get_orf_structure()
        genes_under_orf = []
        for orf_info in orf_structure:
            if orf_info['orf'] == orf_name:
                genes_under_orf = orf_info['genes']
                break

        self.details_text.insert(tk.END, f"\nGenes in this ORF ({len(genes_under_orf)}):\n", "header")
        if genes_under_orf:
            total_length = 0
            for gene_id in genes_under_orf:
                gene = self.game_state.get_gene(gene_id)
                if gene:
                    self.details_text.insert(tk.END, f"  - {gene.name} ({gene.length:,} bp)\n", "value")
                    total_length += gene.length
            self.details_text.insert(tk.END, f"\nTotal ORF length: ", "header")
            self.details_text.insert(tk.END, f"{total_length:,} bp\n", "value")
        else:
            self.details_text.insert(tk.END, "  (No genes - ORF will be hidden in visualization)\n", "value")

        self.details_text.insert(tk.END, f"\nDescription:\n", "header")
        self.details_text.insert(tk.END, "ORFs define reading frames for protein translation. "
                                        "All genes after this ORF (until the next Terminator or end of genome) "
                                        "will be translated together. Multiple ORFs can overlap if there's "
                                        "no Terminator between them.\n", "value")

        self.details_text.config(state=tk.DISABLED)

    def _toggle_gene(self, gene_id: int, panel: str):
        """Toggle gene expansion."""
        expanded_set = self.available_expanded if panel == 'available' else self.installed_expanded

        if gene_id in expanded_set:
            expanded_set.discard(gene_id)
        else:
            expanded_set.add(gene_id)

        if panel == 'available':
            self._update_available_genes()
        else:
            self._update_installed_genes()

    def _update_move_buttons(self):
        """Update move button states based on selected item."""
        # Default: enable both buttons
        can_move = True

        if self.selected_item:
            item_type, item_id = self.selected_item
            # Check if selected item is a UTR gene
            if item_type == 'gene':
                gene = self.game_state.get_gene(item_id)
                if gene and gene.is_utr:
                    can_move = False
            # Effects can't be moved
            elif item_type == 'effect':
                can_move = False
            # ORFs and terminators can be moved (no special restrictions)

        state = 'normal' if can_move else 'disabled'
        self.move_up_btn.config(state=state)
        self.move_down_btn.config(state=state)

    def _select_gene(self, gene: Gene, panel: str = None):
        """Select a gene and show its details."""
        self.selected_item = ('gene', gene.id)
        self._show_gene_details(gene)
        # Refresh gene lists to show selection
        self._update_available_genes()
        self._update_installed_genes()
        self._update_move_buttons()

    def _select_effect(self, effect: Effect):
        """Select an effect and show its details."""
        self.selected_item = ('effect', effect.id)
        self._show_effect_details(effect)
        self._update_move_buttons()

    def _move_item_up(self):
        """Move the selected installed item (gene, ORF, or Terminator) up in order."""
        if not self.selected_item:
            messagebox.showinfo("Select Item", "Please select an installed gene, ORF, or Terminator first.")
            return

        item_type, item_id = self.selected_item
        if item_type not in ('gene', 'orf', 'terminator'):
            messagebox.showinfo("Select Item", "Please select an installed gene, ORF, or Terminator.")
            return

        if item_id not in self.game_state.installed_genes:
            messagebox.showinfo("Select Item", "Please select an item from installed genes.")
            return

        if self.game_state.move_item_up(item_id):
            self._update_installed_genes()
            self._update_genome_visual()

    def _move_item_down(self):
        """Move the selected installed item (gene, ORF, or Terminator) down in order."""
        if not self.selected_item:
            messagebox.showinfo("Select Item", "Please select an installed gene, ORF, or Terminator first.")
            return

        item_type, item_id = self.selected_item
        if item_type not in ('gene', 'orf', 'terminator'):
            messagebox.showinfo("Select Item", "Please select an installed gene, ORF, or Terminator.")
            return

        if item_id not in self.game_state.installed_genes:
            messagebox.showinfo("Select Item", "Please select an item from installed genes.")
            return

        if self.game_state.move_item_down(item_id):
            self._update_installed_genes()
            self._update_genome_visual()

    def _add_orf(self):
        """Add a new ORF to installed genes."""
        can_install, reason = self.game_state.can_install_orf()
        if not can_install:
            messagebox.showerror("Cannot Add ORF", reason)
            return

        cost = self.game_state.get_orf_cost()
        if cost > 0:
            if not messagebox.askyesno("Add ORF",
                    f"Add a new ORF for {cost} EP?"):
                return

        success, message = self.game_state.install_orf()
        if success:
            self._refresh_all()
        else:
            messagebox.showerror("Error", message)

    def _add_terminator(self):
        """Add a new Terminator to installed genes."""
        can_install, reason = self.game_state.can_install_terminator()
        if not can_install:
            messagebox.showerror("Cannot Add Terminator", reason)
            return

        cost = self.game_state.terminator_cost
        if not messagebox.askyesno("Add Terminator",
                f"Add a new Terminator for {cost} EP?\n\n"
                "Terminators mark the end of ORFs. ORFs will stop at the next terminator."):
            return

        success, message = self.game_state.install_terminator()
        if success:
            self._refresh_all()
        else:
            messagebox.showerror("Error", message)

    def _remove_item(self):
        """Remove the selected item (gene, ORF, or Terminator) from installed genes."""
        if not self.selected_item:
            messagebox.showinfo("Select Item", "Please select an installed gene, ORF, or Terminator first.")
            return

        item_type, item_id = self.selected_item

        if item_type == 'orf':
            if item_id not in self.game_state.installed_genes:
                messagebox.showinfo("Select ORF", "Please select an ORF from installed genes.")
                return

            success, message = self.game_state.remove_orf(item_id)
            if success:
                self.selected_item = None
                self._refresh_all()
            else:
                messagebox.showerror("Cannot Remove", message)

        elif item_type == 'terminator':
            if item_id not in self.game_state.installed_genes:
                messagebox.showinfo("Select Terminator", "Please select a Terminator from installed genes.")
                return

            success, message = self.game_state.remove_terminator(item_id)
            if success:
                self.selected_item = None
                self._refresh_all()
            else:
                messagebox.showerror("Cannot Remove", message)

        elif item_type == 'gene':
            if item_id not in self.game_state.installed_genes:
                messagebox.showinfo("Select Gene", "Please select a gene from installed genes.")
                return

            success, message = self.game_state.remove_gene(item_id)
            if success:
                self.selected_item = None
                self._refresh_all()
            else:
                messagebox.showerror("Cannot Remove", message)
        else:
            messagebox.showinfo("Select Item", "Please select an installed gene, ORF, or Terminator.")

    def _show_gene_details(self, gene: Gene):
        """Show gene details in the details panel."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete('1.0', tk.END)

        self.details_text.insert(tk.END, f"{gene.name}\n", "title")
        self.details_text.insert(tk.END, f"\nSet: ", "header")
        self.details_text.insert(tk.END, f"{gene.set_name}\n", "value")
        self.details_text.insert(tk.END, f"Install Cost: ", "header")
        self.details_text.insert(tk.END, f"{gene.install_cost} EP\n", "value")
        self.details_text.insert(tk.END, f"Length: ", "header")
        self.details_text.insert(tk.END, f"{gene.length:,} bp\n", "value")

        if gene.is_utr:
            self.details_text.insert(tk.END, f"UTR: ", "header")
            self.details_text.insert(tk.END, "Yes (fixed at 5' end)\n", "value")

        gene_type_name = self.game_state.database.get_gene_type_name(gene)
        if gene_type_name != "None":
            self.details_text.insert(tk.END, f"Enables Type: ", "header")
            self.details_text.insert(tk.END, f"{gene_type_name}\n", "value")

        if gene.description:
            self.details_text.insert(tk.END, f"\nDescription:\n", "header")
            self.details_text.insert(tk.END, f"{gene.description}\n", "value")

        self.details_text.insert(tk.END, f"\nEffects ({len(gene.effect_ids)}):\n", "header")
        for effect_id in gene.effect_ids:
            effect = self.game_state.get_effect(effect_id)
            if effect:
                self.details_text.insert(tk.END, f"  - {effect.name} ({effect.effect_type})\n", "value")

        self.details_text.config(state=tk.DISABLED)

    def _show_effect_details(self, effect: Effect):
        """Show effect details in the details panel."""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete('1.0', tk.END)

        self.details_text.insert(tk.END, f"{effect.name}\n", "title")
        self.details_text.insert(tk.END, f"\nType: ", "header")
        self.details_text.insert(tk.END, f"{effect.effect_type}\n", "value")

        if effect.category:
            self.details_text.insert(tk.END, f"Category: ", "header")
            self.details_text.insert(tk.END, f"{effect.category}\n", "value")

        if effect.is_global:
            self.details_text.insert(tk.END, f"[GLOBAL EFFECT]\n", "header")

        if effect.description:
            self.details_text.insert(tk.END, f"\nDescription:\n", "header")
            self.details_text.insert(tk.END, f"{effect.description}\n", "value")

        if effect.effect_type == "Transition":
            self.details_text.insert(tk.END, f"\nChance: ", "header")
            self.details_text.insert(tk.END, f"{effect.chance}%\n", "value")

            if effect.inputs:
                self.details_text.insert(tk.END, f"\nInputs:\n", "header")
                for inp in effect.inputs:
                    entity = self.game_state.database.get_entity(inp.get('entity_id', 0))
                    name = entity.name if entity else f"ID:{inp.get('entity_id')}"
                    consumed = "consumed" if inp.get('consumed', True) else "kept"
                    self.details_text.insert(tk.END,
                        f"  {inp.get('amount', 1)}x {name} @ {inp.get('location')} ({consumed})\n", "value")

            if effect.outputs:
                self.details_text.insert(tk.END, f"\nOutputs:\n", "header")
                for out in effect.outputs:
                    if out.get('is_unpack_genome', False):
                        self.details_text.insert(tk.END,
                            f"  Unpack genome @ {out.get('location')}\n", "value")
                    else:
                        entity = self.game_state.database.get_entity(out.get('entity_id', 0))
                        name = entity.name if entity else f"ID:{out.get('entity_id')}"
                        self.details_text.insert(tk.END,
                            f"  {out.get('amount', 1)}x {name} @ {out.get('location')}\n", "value")

            if effect.interferon_production > 0:
                self.details_text.insert(tk.END, f"\nInterferon Production: ", "header")
                self.details_text.insert(tk.END, f"{effect.interferon_production}\n", "value")

            if effect.antibody_response > 0:
                self.details_text.insert(tk.END, f"Antibody Response: ", "header")
                self.details_text.insert(tk.END, f"{effect.antibody_response}\n", "value")

        elif effect.effect_type == "Modify transition":
            self.details_text.insert(tk.END, f"\nTarget: ", "header")
            if effect.target_effect_id:
                target = self.game_state.get_effect(effect.target_effect_id)
                target_name = target.name if target else f"Effect ID {effect.target_effect_id}"
                self.details_text.insert(tk.END, f"{target_name}\n", "value")
            elif effect.target_category:
                self.details_text.insert(tk.END, f"Category: {effect.target_category}\n", "value")

            if effect.chance_modifier != 0:
                self.details_text.insert(tk.END, f"Chance Modifier: ", "header")
                self.details_text.insert(tk.END, f"{effect.chance_modifier:+}%\n", "value")

        elif effect.effect_type == "Change location":
            entity = self.game_state.database.get_entity(effect.affected_entity_id) if effect.affected_entity_id else None
            if entity:
                self.details_text.insert(tk.END, f"\nAffects: ", "header")
                self.details_text.insert(tk.END, f"{entity.name}\n", "value")

            self.details_text.insert(tk.END, f"From: ", "header")
            self.details_text.insert(tk.END, f"{effect.source_location}\n", "value")
            self.details_text.insert(tk.END, f"To: ", "header")
            self.details_text.insert(tk.END, f"{effect.target_location}\n", "value")
            self.details_text.insert(tk.END, f"Chance: ", "header")
            self.details_text.insert(tk.END, f"{effect.location_change_chance}%\n", "value")

        self.details_text.config(state=tk.DISABLED)

    def _install_gene(self):
        """Install the selected gene."""
        if not self.selected_item or self.selected_item[0] != 'gene':
            messagebox.showinfo("Select Gene", "Please select a gene from available genes first.")
            return

        gene_id = self.selected_item[1]
        if gene_id not in self.game_state.available_genes:
            messagebox.showinfo("Select Gene", "Please select a gene from available genes.")
            return

        gene = self.game_state.get_gene(gene_id)

        # Check if gene requires a specific genome type
        if gene and gene.required_genome_type:
            current_genome = self.game_state.virus_config.get_genome_string()

            if not self.game_state.virus_config.is_locked:
                # Genome not locked - prompt user to lock it
                lock_cost = self.game_state.config_lock_cost
                result = messagebox.askyesnocancel(
                    "Genome Type Required",
                    f"This gene requires genome type: {gene.required_genome_type}\n\n"
                    f"Your current genome configuration is: {current_genome}\n\n"
                    f"Would you like to lock your genome configuration for {lock_cost} EP?\n\n"
                    f"Yes = Lock current config ({current_genome}) and install gene\n"
                    f"No = Install gene without locking (gene will be inactive)\n"
                    f"Cancel = Don't install"
                )
                if result is None:
                    return  # Cancel
                elif result is True:
                    # Lock configuration first
                    success, msg = self.game_state.lock_config()
                    if not success:
                        messagebox.showerror("Cannot Lock", msg)
                        return
                    self._refresh_all()
                    # Re-check compatibility after locking
                    current_genome = self.game_state.virus_config.get_genome_string()
                    if current_genome != gene.required_genome_type:
                        messagebox.showwarning(
                            "Genome Mismatch",
                            f"Your genome ({current_genome}) doesn't match the gene's requirement ({gene.required_genome_type}).\n\n"
                            f"The gene will be installed but its effects will be inactive."
                        )
                # If No, proceed with installation (gene will be inactive)

            elif current_genome != gene.required_genome_type:
                # Genome is locked to a different type
                result = messagebox.askyesno(
                    "Genome Type Mismatch",
                    f"This gene requires genome type: {gene.required_genome_type}\n"
                    f"Your genome is locked to: {current_genome}\n\n"
                    f"The gene can still be installed but its effects will be inactive.\n\n"
                    f"Install anyway?"
                )
                if not result:
                    return

        success, message = self.game_state.install_gene(gene_id)
        if success:
            self.selected_item = None
            self._refresh_all()
        else:
            messagebox.showerror("Cannot Install", message)

    def _show_blueprint(self):
        """Show the virus blueprint popup."""
        BlueprintDialog(self, self.game_state)

    def _on_play_round(self):
        """Start the play round."""
        if not self.game_state.installed_genes:
            messagebox.showwarning("No Genes", "You need to install at least one gene before playing.")
            return

        if self.game_state.has_pending_changes():
            result = messagebox.askyesnocancel(
                "Unsaved Config",
                "You have unsaved configuration changes.\n\n"
                "Yes = Lock changes (costs EP)\n"
                "No = Discard changes\n"
                "Cancel = Go back"
            )
            if result is True:
                success, msg = self.game_state.lock_config()
                if not success:
                    messagebox.showerror("Error", msg)
                    return
            elif result is None:
                return
            else:
                self.game_state.reset_pending_config()

        if self.on_play_callback:
            self.on_play_callback()


class BlueprintDialog(tk.Toplevel):
    """Dialog showing the virus blueprint."""

    def __init__(self, parent, game_state: GameState):
        super().__init__(parent)
        self.game_state = game_state

        self.title("Virus Blueprint")
        self.geometry("600x700")
        self.transient(parent)

        self._create_ui()

    def _create_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        ttk.Label(main_frame, text="Virus Blueprint",
                 font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 10))

        # Scrollable text
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text.yview)

        self.text.tag_configure("section", font=('TkDefaultFont', 12, 'bold'))
        self.text.tag_configure("header", font=('TkDefaultFont', 10, 'bold'))
        self.text.tag_configure("value", font=('TkDefaultFont', 10))

        self._populate()

        self.text.config(state=tk.DISABLED)

        # Close button
        ttk.Button(main_frame, text="Close", command=self.destroy).pack(pady=(10, 0))

    def _populate(self):
        """Populate the blueprint text."""
        gs = self.game_state
        config = gs.virus_config

        # Virus Configuration
        self.text.insert(tk.END, "VIRUS CONFIGURATION\n", "section")
        self.text.insert(tk.END, "=" * 40 + "\n\n")

        self.text.insert(tk.END, "Genome Type: ", "header")
        self.text.insert(tk.END, f"{config.get_genome_string()}\n", "value")

        self.text.insert(tk.END, "Virion Type: ", "header")
        self.text.insert(tk.END, f"{config.virion_type}\n", "value")

        # Show genome entities
        genome_ids = config.get_genome_entity_ids()
        self.text.insert(tk.END, "Genome Entities: ", "header")
        genome_names = []
        for gid in genome_ids:
            entity = gs.database.get_entity(gid)
            if entity:
                genome_names.append(entity.name)
        self.text.insert(tk.END, f"{', '.join(genome_names)}\n", "value")

        self.text.insert(tk.END, "Configuration Locked: ", "header")
        self.text.insert(tk.END, f"{'Yes' if config.is_locked else 'No'}\n\n", "value")

        # Genome
        self.text.insert(tk.END, "GENOME\n", "section")
        self.text.insert(tk.END, "=" * 40 + "\n\n")

        self.text.insert(tk.END, "Total Length: ", "header")
        self.text.insert(tk.END, f"{gs.get_total_genome_length():,} bp\n\n", "value")

        # Count actual genes (not ORFs or terminators)
        gene_count = sum(1 for item in gs.installed_genes if not gs.is_marker(item))
        orf_count = gs.get_installed_orf_count()
        term_count = gs.get_installed_terminator_count()

        # ORF Structure
        orf_structure = gs.get_orf_structure()
        if orf_structure:
            self.text.insert(tk.END, f"ORF Structure ({len(orf_structure)} ORFs with genes):\n", "header")
            for orf_info in orf_structure:
                orf_name = orf_info['orf']
                orf_genes = orf_info['genes']
                orf_length = sum(gs.get_gene(gid).length for gid in orf_genes if gs.get_gene(gid))
                self.text.insert(tk.END, f"\n  {orf_name} ({orf_length:,} bp):\n", "value")
                for gene_id in orf_genes:
                    gene = gs.get_gene(gene_id)
                    if gene:
                        self.text.insert(tk.END, f"    - ({gene.set_name}) {gene.name} [{gene.length:,} bp]\n", "value")
            self.text.insert(tk.END, "\n")

        # Installed Genes (flat list)
        self.text.insert(tk.END, f"Installed Genes ({gene_count} genes, {orf_count} ORFs, {term_count} Terminators):\n", "header")
        for item in gs.installed_genes:
            if gs.is_orf(item):
                self.text.insert(tk.END, f"  [{item}]\n", "value")
            elif gs.is_terminator(item):
                self.text.insert(tk.END, f"  [STOP: {item}]\n", "value")
            else:
                gene = gs.get_gene(item)
                if gene:
                    self.text.insert(tk.END, f"  - ({gene.set_name}) {gene.name} [{gene.length:,} bp]\n", "value")

        # Enabled Types
        enabled_types = gs.get_enabled_types()
        if enabled_types:
            self.text.insert(tk.END, f"\nEnabled Entity Types:\n", "header")
            for t in sorted(enabled_types):
                self.text.insert(tk.END, f"  - {t}\n", "value")

        # Effects
        self.text.insert(tk.END, "\n\nEFFECTS\n", "section")
        self.text.insert(tk.END, "=" * 40 + "\n\n")

        effects = gs.get_all_effects()
        global_effects = gs.get_global_effects()

        if global_effects:
            self.text.insert(tk.END, "Global Effects:\n", "header")
            for effect in global_effects:
                self.text.insert(tk.END, f"  - {effect.name} ({effect.effect_type})\n", "value")
            self.text.insert(tk.END, "\n")

        if effects:
            self.text.insert(tk.END, f"Gene Effects ({len(effects)}):\n", "header")
            for effect in effects:
                self.text.insert(tk.END, f"  - {effect.name} ({effect.effect_type})\n", "value")
