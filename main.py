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
        # For now, just show a message since Play module isn't implemented yet
        messagebox.showinfo(
            "Play Module",
            "The Play module is under development.\n\n"
            "For now, you can continue building your virus.\n"
            "The simulation will be added in a future phase."
        )

        # In the future, this will:
        # 1. Close/hide the builder
        # 2. Open the play module
        # 3. Run the simulation
        # 4. Return to builder when done

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


def main():
    """Main entry point."""
    app = MainMenu()
    app.mainloop()


if __name__ == "__main__":
    main()
