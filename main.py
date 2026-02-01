"""
Viral Sandbox - Main Application
An educational game/simulator for building virtual viruses.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from database_editor import DatabaseEditor
from database import GameDatabase
from game_state import GameState
from builder import BuilderModule
from play_module import PlayModule


class MainMenu(tk.Tk):
    """Main menu window for Viral Sandbox."""

    def __init__(self):
        super().__init__()

        self.title("Viral Sandbox")
        self.geometry("600x500")
        self.minsize(500, 400)

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

        # Current game state
        self.game_state = None
        self.current_database = None

        self._create_ui()

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
            "Create your own virtual viruses by selecting and combining genes.\n"
            "Simulate your virus infecting a cell and achieve a runaway reaction\n"
            "while managing limited resources and build cycles."
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
            text="Version 0.1.0 - Development Build",
            font=('TkDefaultFont', 8)
        )
        version_label.pack(side=tk.BOTTOM, pady=(20, 0))

    def _new_game(self):
        """Start a new game."""
        # Open file dialog to select database
        filepath = filedialog.askopenfilename(
            title="Select Game Database",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if not filepath:
            return

        # Load the database
        database = GameDatabase()
        if not database.load(filepath):
            messagebox.showerror("Error", "Failed to load database file.")
            return

        # Check if database has genes
        if not database.genes:
            messagebox.showerror(
                "Empty Database",
                "The selected database has no genes.\n\n"
                "Please create genes in the Database Editor first."
            )
            return

        # Create new game state
        self.current_database = database
        self.game_state = GameState.new_game(
            database=database,
            starting_ep=100,
            starting_hand_size=7
        )

        # Check if enough genes were drawn
        if not self.game_state.available_genes:
            messagebox.showerror(
                "Not Enough Genes",
                "The database doesn't have enough genes to start a game."
            )
            self.game_state = None
            self.current_database = None
            return

        # Open the builder module
        self._open_builder()

    def _continue_game(self):
        """Continue a saved game."""
        # Check if there's a game in progress
        if self.game_state and self.builder_module and self.builder_module.winfo_exists():
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
                self.game_state,
                on_play=self._on_play_round,
                on_quit=self._on_game_quit
            )
            # Hide main menu while playing
            self.withdraw()
        else:
            self.builder_module.lift()
            self.builder_module.focus_force()

    def _on_play_round(self):
        """Handle play round callback from builder."""
        # Hide the builder module
        if self.builder_module:
            self.builder_module.withdraw()

        # Open the play module
        self.play_module = PlayModule(
            self,
            self.game_state,
            on_return=self._on_play_return
        )

    def _on_play_return(self, victory: bool = False):
        """Handle return from play module."""
        # Hide the play module first to avoid window conflicts
        if self.play_module:
            self.play_module.withdraw()

        self.play_module = None

        if victory:
            # Player won the game!
            messagebox.showinfo(
                "Victory!",
                "Congratulations! Your virus has achieved a runaway reaction!\n\n"
                f"Final EP: {self.game_state.evolution_points}"
            )
            self._on_game_quit()
            return

        # Check if max rounds reached
        self.game_state.complete_play_round()

        if self.game_state.game_over:
            messagebox.showinfo(
                "Game Over",
                f"You have completed all {self.game_state.max_rounds} play rounds.\n\n"
                "Unfortunately, your virus did not achieve a runaway reaction.\n"
                f"Final EP: {self.game_state.evolution_points}"
            )
            self._on_game_quit()
            return

        # Show the builder module first (so dialog has a visible parent context)
        if self.builder_module:
            self.builder_module.deiconify()
            self.builder_module.update()  # Process pending events

        # Offer new genes for next round
        self._offer_new_genes()

        # Finalize builder display
        if self.builder_module:
            self.builder_module._refresh_all()
            self.builder_module.lift()
            self.builder_module.focus_force()

    def _offer_new_genes(self):
        """Offer new genes to the player after a play round."""
        # Get random genes not in hand or installed
        all_gene_ids = list(self.game_state.database.genes.keys())
        available_ids = [gid for gid in all_gene_ids
                        if gid not in self.game_state.available_genes
                        and gid not in self.game_state.installed_genes]

        if not available_ids:
            messagebox.showinfo("No More Genes",
                               "There are no more genes available to offer.")
            return

        import random
        offer_count = min(self.game_state.genes_offered_per_round, len(available_ids))
        offered = random.sample(available_ids, offer_count)

        # Show selection dialog (use builder_module as parent if available, otherwise self)
        parent = self.builder_module if self.builder_module else self
        dialog = GeneOfferDialog(parent, self.game_state, offered)
        parent.wait_window(dialog)

        if dialog.selected_gene:
            self.game_state.available_genes.append(dialog.selected_gene)

    def _on_game_quit(self):
        """Handle game quit callback."""
        self.game_state = None
        self.current_database = None
        self.builder_module = None
        self.deiconify()  # Show main menu again

    def _open_database_editor(self):
        """Open the database editor."""
        if self.database_editor is None or not self.database_editor.winfo_exists():
            self.database_editor = DatabaseEditor(self, on_close=self._on_editor_close)
        else:
            # Bring existing window to front
            self.database_editor.lift()
            self.database_editor.focus_force()

    def _on_editor_close(self):
        """Handle database editor close."""
        self.database_editor = None

    def _open_settings(self):
        """Open settings dialog."""
        SettingsDialog(self)

    def _exit_game(self):
        """Exit the application."""
        if self.game_state:
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

    def __init__(self, parent):
        super().__init__(parent)
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
            text="Game Settings",
            font=('TkDefaultFont', 14, 'bold')
        ).pack(pady=(0, 20))

        # Settings notebook
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Game tab
        game_frame = ttk.Frame(notebook, padding=10)
        notebook.add(game_frame, text="Game")

        ttk.Label(game_frame, text="Starting Evolution Points:").grid(row=0, column=0, sticky='w', pady=5)
        self.starting_ep_var = tk.StringVar(value="100")
        ttk.Entry(game_frame, textvariable=self.starting_ep_var, width=10).grid(row=0, column=1, sticky='w', pady=5)

        ttk.Label(game_frame, text="Starting Hand Size:").grid(row=1, column=0, sticky='w', pady=5)
        self.hand_size_var = tk.StringVar(value="7")
        ttk.Entry(game_frame, textvariable=self.hand_size_var, width=10).grid(row=1, column=1, sticky='w', pady=5)

        ttk.Label(game_frame, text="Max Play Rounds:").grid(row=2, column=0, sticky='w', pady=5)
        self.max_rounds_var = tk.StringVar(value="10")
        ttk.Entry(game_frame, textvariable=self.max_rounds_var, width=10).grid(row=2, column=1, sticky='w', pady=5)

        ttk.Label(game_frame, text="Win Threshold (Virions):").grid(row=3, column=0, sticky='w', pady=5)
        self.win_threshold_var = tk.StringVar(value="10000")
        ttk.Entry(game_frame, textvariable=self.win_threshold_var, width=10).grid(row=3, column=1, sticky='w', pady=5)

        # Display tab
        display_frame = ttk.Frame(notebook, padding=10)
        notebook.add(display_frame, text="Display")

        ttk.Label(display_frame, text="Simulation Speed:").grid(row=0, column=0, sticky='w', pady=5)
        self.sim_speed_var = tk.StringVar(value="Normal")
        ttk.Combobox(display_frame, textvariable=self.sim_speed_var,
                     values=["Slow", "Normal", "Fast", "Maximum"], state='readonly', width=15).grid(
            row=0, column=1, sticky='w', pady=5)

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _save(self):
        """Save settings."""
        # TODO: Actually save settings to a config file
        messagebox.showinfo("Settings", "Settings saved successfully.")
        self.destroy()


class GeneOfferDialog(tk.Toplevel):
    """Dialog for selecting a new gene after a play round."""

    def __init__(self, parent, game_state: GameState, offered_gene_ids: list):
        super().__init__(parent)
        self.game_state = game_state
        self.offered_gene_ids = offered_gene_ids
        self.selected_gene = None

        self.title("Select a Gene")
        self.geometry("500x400")
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
            text=f"Round {self.game_state.current_round}/{self.game_state.max_rounds} complete!"
        ).pack()

        # Gene list
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.gene_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                        font=('TkDefaultFont', 11), height=8)
        self.gene_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.gene_listbox.yview)

        # Populate list
        for gene_id in self.offered_gene_ids:
            gene = self.game_state.database.get_gene(gene_id)
            if gene:
                self.gene_listbox.insert(tk.END,
                    f"({gene.set_name}) {gene.name} - {gene.install_cost} EP, {gene.length} bp")

        self.gene_listbox.bind('<<ListboxSelect>>', self._on_select)

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

    def _on_select(self, event):
        """Handle gene selection."""
        selection = self.gene_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        gene_id = self.offered_gene_ids[idx]
        gene = self.game_state.database.get_gene(gene_id)

        if gene:
            self.details_text.configure(state='normal')
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert('1.0',
                f"{gene.description}\n\nEffects: {len(gene.effect_ids)}")
            self.details_text.configure(state='disabled')

    def _select_gene(self):
        """Select the highlighted gene."""
        selection = self.gene_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a gene.")
            return

        idx = selection[0]
        self.selected_gene = self.offered_gene_ids[idx]
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
