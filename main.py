"""
Viral Sandbox - Main Application
An educational game/simulator for building virtual viruses.

The Tk user interface. It talks to the game only through game_api.GameAPI.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from database_editor import DatabaseEditor
from game_api import (GameAPI, GeneOffer, RoundOutcome, StartResult,
                      HAND_SIZE_MIN, HAND_SIZE_MAX)
from builder import BuilderModule, GENE_COLOR_CATEGORY_COLORS, DEFAULT_GENE_COLOR
from play_module import PlayModule


class MainMenu(tk.Tk):
    """Main menu window for Viral Sandbox."""

    def __init__(self):
        super().__init__()

        self.title("Viral Sandbox")
        self.geometry("600x600")
        self.minsize(500, 550)

        # Center the window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

        # Track open windows
        self.database_editor = None
        self.builder_module = None
        self.play_module = None

        # The API owns everything that isn't presentation: settings, the
        # playthrough, rounds and gene offers.
        self.api = GameAPI()

        self._create_ui()

    @property
    def window_mode(self) -> str:
        return self.api.settings["display"]["window_mode"]

    def _create_ui(self):
        """Create the main menu UI."""
        # Main frame with padding
        main_frame = ttk.Frame(self, padding=40)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 40))

        title_label = ttk.Label(
            title_frame,
            text="VIRAL SANDBOX",
            font=('TkDefaultFont', 28, 'bold')
        )
        title_label.pack()

        subtitle_label = ttk.Label(
            title_frame,
            text="Build. Infect. Evolve.",
            font=('TkDefaultFont', 12, 'italic')
        )
        subtitle_label.pack(pady=(5, 0))

        # Description
        desc_frame = ttk.Frame(main_frame)
        desc_frame.pack(fill=tk.X, pady=(0, 30))

        description = (
            "Simulate your own virtual viruses!\n"
            "Preview version: Work in progress.\n"
            "Written by Claude Opus 4.5."
        )
        desc_label = ttk.Label(
            desc_frame,
            text=description,
            justify=tk.CENTER,
            font=('TkDefaultFont', 10)
        )
        desc_label.pack()

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.BOTH, expand=True)

        # Style for larger buttons
        style = ttk.Style()
        style.configure('Large.TButton', font=('TkDefaultFont', 12), padding=15)

        # New Game button
        new_game_btn = ttk.Button(
            button_frame,
            text="New Game",
            style='Large.TButton',
            command=self._new_game,
            width=25
        )
        new_game_btn.pack(pady=10)

        # Continue Game button
        continue_btn = ttk.Button(
            button_frame,
            text="Continue Game",
            style='Large.TButton',
            command=self._continue_game,
            width=25
        )
        continue_btn.pack(pady=10)

        # Database Editor button
        editor_btn = ttk.Button(
            button_frame,
            text="Database Editor",
            style='Large.TButton',
            command=self._open_database_editor,
            width=25
        )
        editor_btn.pack(pady=10)

        # Settings button
        settings_btn = ttk.Button(
            button_frame,
            text="Settings",
            style='Large.TButton',
            command=self._open_settings,
            width=25
        )
        settings_btn.pack(pady=10)

        # Exit button
        exit_btn = ttk.Button(
            button_frame,
            text="Exit",
            style='Large.TButton',
            command=self._exit_game,
            width=25
        )
        exit_btn.pack(pady=10)

        # Version info at bottom
        version_label = ttk.Label(
            main_frame,
            text=f"Version {self.api.version} - Development Build",
            font=('TkDefaultFont', 8)
        )
        version_label.pack(side=tk.BOTTOM, pady=(20, 0))

    def _new_game(self):
        """Start a new game."""
        # Try default database first
        filepath = self.api.default_database_path()

        if filepath is None:
            # Default database not found, ask user to select one
            filepath = filedialog.askopenfilename(
                title="Select Game Database",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )

            if not filepath:
                return

        # Hand off to the API, then present whatever it reports.
        result = self.api.new_game(filepath)

        if result is StartResult.LOAD_FAILED:
            messagebox.showerror("Error", "Failed to load database file.")
            return

        if result is StartResult.NO_GENES:
            messagebox.showerror(
                "Empty Database",
                "The selected database has no genes.\n\n"
                "Please create genes in the Database Editor first."
            )
            return

        if result is StartResult.NOT_ENOUGH_GENES:
            messagebox.showerror(
                "Not Enough Genes",
                "The database doesn't have enough genes to start a game."
            )
            return

        # Open the builder module
        self._open_builder()

    def _continue_game(self):
        """Continue a saved game."""
        # Check if there's a game in progress
        if self.api.is_game_active and self.builder_module and self.builder_module.winfo_exists():
            self.builder_module.lift()
            self.builder_module.focus_force()
            return

        messagebox.showinfo(
            "No Game in Progress",
            "There is no game currently in progress.\n\n"
            "Click 'New Game' to start a new game."
        )

    def _open_builder(self):
        """Open the builder module."""
        if self.builder_module is None or not self.builder_module.winfo_exists():
            self.builder_module = BuilderModule(
                self,
                self.api,
                on_play=self._on_play_round,
                on_quit=self._on_game_quit,
                window_mode=self.window_mode
            )
            # Hide main menu while playing
            self.withdraw()
        else:
            self.builder_module.lift()
            self.builder_module.focus_force()

    def _on_play_round(self):
        """Handle play round callback from builder."""
        self.api.start_round()

        # Hide the builder module
        if self.builder_module:
            self.builder_module.withdraw()

        # Open the play module
        self.play_module = PlayModule(
            self,
            self.api,
            on_return=self._on_play_return,
            window_mode=self.window_mode
        )

    def _on_play_return(self):
        """Handle return from play module."""
        # Hide the play module first to avoid window conflicts
        if self.play_module:
            self.play_module.withdraw()

        self.play_module = None

        outcome = self.api.finish_round()

        if outcome is RoundOutcome.VICTORY:
            messagebox.showinfo(
                "Victory!",
                "Congratulations! Your virus has achieved a runaway reaction!\n\n"
                f"Final EP: {self.api.status().evolution_points}"
            )
            self._quit_game()
            return

        if outcome is RoundOutcome.OUT_OF_ROUNDS:
            status = self.api.status()
            messagebox.showinfo(
                "Game Over",
                f"You have completed all {status.max_rounds} play rounds.\n\n"
                "Unfortunately, your virus did not achieve a runaway reaction.\n"
                f"Final EP: {status.evolution_points}"
            )
            self._quit_game()
            return

        # Show the builder module first (so dialog has a visible parent context)
        if self.builder_module:
            self.builder_module.deiconify()
            if self.window_mode == "maximized":
                self.builder_module.state('zoomed')
            self.builder_module.update()  # Process pending events

        # Offer new genes for next round
        self._offer_new_genes()

        # Finalize builder display
        if self.builder_module:
            self.builder_module.refresh()
            self.builder_module.lift()
            self.builder_module.focus_force()

    def _offer_new_genes(self):
        """Offer new genes to the player after a play round."""
        offer = self.api.gene_offer

        if offer is None:
            messagebox.showinfo("No More Genes",
                               "There are no more genes available to offer.")
            return

        # Show selection dialog (use builder_module as parent if available, otherwise self)
        parent = self.builder_module if self.builder_module else self
        dialog = GeneOfferDialog(parent, offer)
        parent.wait_window(dialog)

        if dialog.selected_gene is not None:
            self.api.accept_offered_gene(dialog.selected_gene)
        else:
            self.api.decline_gene_offer()

    def _quit_game(self):
        """End the game after victory or the last round and close the builder."""
        if self.builder_module and self.builder_module.winfo_exists():
            self.builder_module.destroy()
        self._on_game_quit()

    def _on_game_quit(self):
        """Handle game quit callback."""
        self.api.end_game()
        self.builder_module = None
        self.deiconify()  # Show main menu again

    def _open_database_editor(self):
        """Open the database editor."""
        if self.database_editor is None or not self.database_editor.winfo_exists():
            self.database_editor = DatabaseEditor(self, self.api.create_content_database(),
                                                  on_close=self._on_editor_close)
        else:
            # Bring existing window to front
            self.database_editor.lift()
            self.database_editor.focus_force()

    def _on_editor_close(self):
        """Handle database editor close."""
        self.database_editor = None

    def _open_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self, self.api)
        self.wait_window(dialog)

    def _exit_game(self):
        """Exit the application."""
        if self.api.is_game_active:
            if not messagebox.askyesno(
                "Exit",
                "You have a game in progress. Are you sure you want to exit?\n\n"
                "Your progress will be lost."
            ):
                return
        elif not messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            return

        self.quit()


class SettingsDialog(tk.Toplevel):
    """Settings dialog window."""

    def __init__(self, parent, api: GameAPI):
        super().__init__(parent)
        self.api = api
        self.settings = api.settings
        self.title("Settings")
        self.geometry("400x300")
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f'+{x}+{y}')

        self._create_ui()

    def _create_ui(self):
        """Create the settings UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        ttk.Label(
            main_frame,
            text="Settings",
            font=('TkDefaultFont', 14, 'bold')
        ).pack(pady=(0, 20))

        # Settings notebook (tabs for future expansion)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Display tab
        display_frame = ttk.Frame(notebook, padding=10)
        notebook.add(display_frame, text="Display")

        ttk.Label(display_frame, text="Window Mode:").grid(row=0, column=0, sticky='w', pady=5)
        current_mode = self.settings["display"]["window_mode"]
        self.window_mode_var = tk.StringVar(value=current_mode.capitalize())
        ttk.Combobox(display_frame, textvariable=self.window_mode_var,
                     values=["Maximized", "Windowed"], state='readonly', width=15).grid(
            row=0, column=1, sticky='w', padx=(10, 0), pady=5)

        # Game tab
        game_frame = ttk.Frame(notebook, padding=10)
        notebook.add(game_frame, text="Game")

        ttk.Label(game_frame, text="Starting Hand Size:").grid(row=0, column=0, sticky='w', pady=5)
        self.hand_size_var = tk.StringVar(value=str(self.settings["game"]["starting_hand_size"]))
        ttk.Spinbox(game_frame, textvariable=self.hand_size_var,
                    from_=HAND_SIZE_MIN, to=HAND_SIZE_MAX,
                    width=8).grid(row=0, column=1, sticky='w', padx=(10, 0), pady=5)

        ttk.Label(game_frame, text="Use database:").grid(row=1, column=0, sticky='w', pady=5)
        self.default_db_var = tk.StringVar(value=self.settings["game"]["default_database"])
        ttk.Entry(game_frame, textvariable=self.default_db_var,
                  width=25).grid(row=1, column=1, sticky='w', padx=(10, 0), pady=5)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _save(self):
        """Save settings; the API validates them."""
        try:
            hand_size = int(self.hand_size_var.get())
        except ValueError:
            hand_size = None  # Not a number - the API reports why it is invalid

        self.settings["display"]["window_mode"] = self.window_mode_var.get().lower()
        self.settings["game"]["starting_hand_size"] = hand_size
        self.settings["game"]["default_database"] = self.default_db_var.get().strip()

        saved, message = self.api.save_settings(self.settings)
        if not saved:
            messagebox.showerror("Invalid Setting", message)
            return
        self.destroy()


class GeneOfferDialog(tk.Toplevel):
    """Dialog for selecting a new gene after a play round."""

    def __init__(self, parent, offer: GeneOffer):
        super().__init__(parent)
        self.offer = offer
        self.genes_by_id = {gene.id: gene for gene in offer.genes}
        self.selected_gene = None

        self.title("Select a Gene")
        self.geometry("500x550")
        self.transient(parent)
        self.grab_set()

        # Handle window close (treat as skip)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f'+{x}+{y}')

        self._create_ui()

    def _on_close(self):
        """Handle window close button."""
        self.selected_gene = None
        self.destroy()

    def _create_ui(self):
        """Create the dialog UI."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        ttk.Label(
            main_frame,
            text="Choose a Gene to Add to Your Hand",
            font=('TkDefaultFont', 12, 'bold')
        ).pack(pady=(0, 15))

        ttk.Label(
            main_frame,
            text=f"Round {self.offer.completed_round}/{self.offer.max_rounds} complete!"
        ).pack()

        # Gene list with color-coded names
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.gene_list_inner = tk.Frame(canvas)

        self.gene_list_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.gene_list_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Track selection state
        self._gene_rows = []  # list of (gene_id, row_frame, label_widgets)
        self._selected_index = None

        # Populate list
        for i, gene in enumerate(self.offer.genes):
            self._create_gene_offer_row(gene, i)

        # Details area
        details_frame = ttk.LabelFrame(main_frame, text="Gene Details")
        details_frame.pack(fill=tk.X, pady=10)

        self.details_text = tk.Text(details_frame, height=4, wrap=tk.WORD,
                                     state='disabled')
        self.details_text.pack(fill=tk.X, padx=5, pady=5)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Select Gene",
                   command=self._select_gene).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Skip",
                   command=self._skip).pack(side=tk.RIGHT, padx=5)

    def _create_gene_offer_row(self, gene, index: int):
        """Create a single gene row with color-coded name."""
        row_frame = tk.Frame(self.gene_list_inner, cursor="hand2")
        row_frame.pack(fill=tk.X, padx=2, pady=1)

        name_fg = GENE_COLOR_CATEGORY_COLORS.get(gene.color_category, DEFAULT_GENE_COLOR)
        base_fg = DEFAULT_GENE_COLOR
        bg = row_frame.cget('bg')

        prefix_label = tk.Label(row_frame, text=f"({gene.set_name}) ",
                                fg=base_fg, bg=bg, font=('TkDefaultFont', 11),
                                cursor="hand2")
        prefix_label.pack(side=tk.LEFT)

        name_label = tk.Label(row_frame, text=gene.name,
                              fg=name_fg, bg=bg, font=('TkDefaultFont', 11),
                              cursor="hand2")
        name_label.pack(side=tk.LEFT)

        suffix_label = tk.Label(row_frame, text=f" - {gene.install_cost} EP, {gene.length} bp",
                                fg=base_fg, bg=bg, font=('TkDefaultFont', 11),
                                cursor="hand2")
        suffix_label.pack(side=tk.LEFT)

        labels = [prefix_label, name_label, suffix_label]
        self._gene_rows.append((gene.id, row_frame, labels, name_fg))

        # Bind click on row and all labels
        for widget in [row_frame] + labels:
            widget.bind("<Button-1>", lambda e, idx=index: self._on_row_click(idx))

    def _on_row_click(self, index: int):
        """Handle clicking a gene row."""
        # Deselect previous
        if self._selected_index is not None and self._selected_index < len(self._gene_rows):
            _, prev_frame, prev_labels, prev_name_fg = self._gene_rows[self._selected_index]
            prev_bg = 'SystemButtonFace'  # default tk bg
            prev_frame.configure(bg=prev_bg, relief=tk.FLAT, borderwidth=0)
            for i, lbl in enumerate(prev_labels):
                fg = prev_name_fg if i == 1 else DEFAULT_GENE_COLOR
                lbl.configure(bg=prev_bg, fg=fg)

        # Select new
        self._selected_index = index
        gene_id, row_frame, labels, _ = self._gene_rows[index]
        sel_bg = '#cce5ff'
        sel_fg = '#004085'
        row_frame.configure(bg=sel_bg, relief=tk.SOLID, borderwidth=1)
        for lbl in labels:
            lbl.configure(bg=sel_bg, fg=sel_fg)

        # Update details
        gene = self.genes_by_id.get(gene_id)
        if gene:
            self.details_text.configure(state='normal')
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert('1.0',
                f"{gene.description}\n\nEffects: {len(gene.effect_ids)}")
            self.details_text.configure(state='disabled')

    def _select_gene(self):
        """Select the highlighted gene."""
        if self._selected_index is None:
            messagebox.showwarning("No Selection", "Please select a gene.")
            return

        gene_id = self._gene_rows[self._selected_index][0]
        self.selected_gene = gene_id
        self.destroy()

    def _skip(self):
        """Skip gene selection."""
        if messagebox.askyesno("Skip", "Are you sure you want to skip gene selection?"):
            self.selected_gene = None
            self.destroy()


def main():
    """Main entry point."""
    app = MainMenu()
    app.mainloop()


if __name__ == "__main__":
    main()
