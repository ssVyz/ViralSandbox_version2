"""
Database Editor for Viral Sandbox.
Allows creating, editing, and saving game databases.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Callable
from database import GameDatabase
from models import (
    ViralEntity, Effect, Gene, Milestone,
    EntityCategory, CellLocation,
    EffectType, MilestoneType, OrfTargeting
)


class DatabaseEditor(tk.Toplevel):
    """Database editor window."""

    def __init__(self, parent, on_close: Optional[Callable] = None):
        super().__init__(parent)
        self.title("Viral Sandbox - Database Editor")
        self.geometry("1200x800")
        self.minsize(1000, 600)

        self.database = GameDatabase()
        self.on_close_callback = on_close
        self.current_selection = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._create_menu()
        self._create_ui()

    def _on_close(self):
        """Handle window close."""
        if self.database.modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?"
            )
            if result is True:  # Yes
                if not self._save_database():
                    return
            elif result is None:  # Cancel
                return

        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()

    def _create_menu(self):
        """Create the menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Database", command=self._new_database)
        file_menu.add_command(label="Open Database...", command=self._open_database)
        file_menu.add_command(label="Save", command=self._save_database)
        file_menu.add_command(label="Save As...", command=self._save_database_as)
        file_menu.add_separator()
        file_menu.add_command(label="Close Editor", command=self._on_close)

    def _create_ui(self):
        """Create the main UI layout."""
        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Status bar at top
        self.status_var = tk.StringVar(value="No database loaded")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(0, 5))

        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs
        self.entities_tab = self._create_entities_tab()
        self.effects_tab = self._create_effects_tab()
        self.genes_tab = self._create_genes_tab()
        self.milestones_tab = self._create_milestones_tab()
        self.settings_tab = self._create_settings_tab()

        self.notebook.add(self.entities_tab, text="Entities")
        self.notebook.add(self.effects_tab, text="Effects")
        self.notebook.add(self.genes_tab, text="Genes")
        self.notebook.add(self.milestones_tab, text="Milestones")
        self.notebook.add(self.settings_tab, text="Global Settings")

    def _create_list_frame(self, parent, search_callback, select_callback) -> tuple:
        """Create a standard list frame with search and filter."""
        frame = ttk.Frame(parent)

        # Search bar
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_var.trace('w', lambda *args: search_callback())

        # Listbox with scrollbar
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, exportselection=False)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        listbox.bind('<<ListboxSelect>>', lambda e: select_callback())

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        return frame, search_var, listbox, btn_frame

    # ==================== ENTITIES TAB ====================

    def _create_entities_tab(self) -> ttk.Frame:
        """Create the entities tab."""
        tab = ttk.Frame(self.notebook)

        # Split into left (list) and right (editor)
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel - list
        left_frame, self.entity_search_var, self.entity_listbox, btn_frame = \
            self._create_list_frame(tab, self._filter_entities, self._on_entity_select)
        left_frame.config(width=350)

        ttk.Button(btn_frame, text="New Entity", command=self._new_entity).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_entity).pack(side=tk.LEFT, padx=2)

        paned.add(left_frame, weight=1)

        # Right panel - editor
        right_frame = ttk.Frame(tab)
        right_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(right_frame, text="Entity Editor", font=('TkDefaultFont', 12, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 10))

        row += 1
        ttk.Label(right_frame, text="ID:").grid(row=row, column=0, sticky='w', pady=2)
        self.entity_id_var = tk.StringVar()
        ttk.Label(right_frame, textvariable=self.entity_id_var).grid(row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Name:").grid(row=row, column=0, sticky='w', pady=2)
        self.entity_name_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.entity_name_var, width=40).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Category:").grid(row=row, column=0, sticky='w', pady=2)
        self.entity_category_var = tk.StringVar()
        category_combo = ttk.Combobox(right_frame, textvariable=self.entity_category_var,
                                       values=[c.value for c in EntityCategory], state='readonly', width=37)
        category_combo.grid(row=row, column=1, sticky='w', pady=2)
        category_combo.bind('<<ComboboxSelected>>', self._on_entity_category_change)

        row += 1
        ttk.Label(right_frame, text="Type:").grid(row=row, column=0, sticky='w', pady=2)
        self.entity_type_var = tk.StringVar()
        self.entity_type_label = ttk.Label(right_frame, text="(Auto-set for proteins)")
        self.entity_type_label.grid(row=row, column=1, sticky='w', pady=2)
        self.entity_type_label.grid_remove()  # Hidden by default

        row += 1
        ttk.Label(right_frame, text="Description:").grid(row=row, column=0, sticky='nw', pady=2)
        self.entity_desc_text = tk.Text(right_frame, width=40, height=4)
        self.entity_desc_text.grid(row=row, column=1, sticky='w', pady=2)

        row += 1
        btn_row = ttk.Frame(right_frame)
        btn_row.grid(row=row, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Button(btn_row, text="Save Entity", command=self._save_entity).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Clear", command=self._clear_entity_form).pack(side=tk.LEFT, padx=2)

        paned.add(right_frame, weight=2)

        return tab

    def _filter_entities(self):
        """Filter the entity list based on search."""
        search = self.entity_search_var.get().lower()
        self.entity_listbox.delete(0, tk.END)
        for entity in sorted(self.database.entities.values(), key=lambda e: e.id):
            if search in entity.name.lower() or search in entity.category.lower():
                # Mark protected entities with a lock symbol
                protected = "[*] " if self.database.is_protected_entity(entity.id) else ""
                self.entity_listbox.insert(tk.END, f"{protected}[{entity.id}] {entity.name} ({entity.category})")

    def _on_entity_category_change(self, event=None):
        """Handle entity category change - show/hide type field for proteins."""
        category = self.entity_category_var.get()
        if category == EntityCategory.PROTEIN.value:
            # For proteins, show label indicating type is auto-set
            name = self.entity_name_var.get().strip()
            self.entity_type_var.set(name if name else "(will use entity name)")
            self.entity_type_label.config(text=f"Type: {name if name else '(will use entity name)'}")
            self.entity_type_label.grid()
        else:
            # For non-proteins, type is always "None"
            self.entity_type_var.set("None")
            self.entity_type_label.grid_remove()

    def _on_entity_select(self):
        """Handle entity selection."""
        selection = self.entity_listbox.curselection()
        if not selection:
            return
        text = self.entity_listbox.get(selection[0])
        # Handle protected entity prefix [*]
        if text.startswith("[*] "):
            text = text[4:]
        entity_id = int(text.split(']')[0][1:])
        entity = self.database.get_entity(entity_id)
        if entity:
            self.entity_id_var.set(str(entity.id))
            self.entity_name_var.set(entity.name)
            self.entity_category_var.set(entity.category)
            self.entity_type_var.set(entity.entity_type)
            self.entity_desc_text.delete('1.0', tk.END)
            self.entity_desc_text.insert('1.0', entity.description)
            self.current_selection = ('entity', entity.id)
            # Update type field display based on category
            self._on_entity_category_change()

    def _new_entity(self):
        """Create a new entity."""
        self._clear_entity_form()
        self.entity_id_var.set(str(self.database.get_next_entity_id()))
        self.current_selection = ('entity', 0)

    def _clear_entity_form(self):
        """Clear the entity form."""
        self.entity_id_var.set("")
        self.entity_name_var.set("")
        self.entity_category_var.set("")
        self.entity_type_var.set("None")
        self.entity_desc_text.delete('1.0', tk.END)
        self.entity_type_label.grid_remove()
        self.current_selection = None

    def _save_entity(self):
        """Save the current entity."""
        name = self.entity_name_var.get().strip()
        category = self.entity_category_var.get()

        if not name:
            messagebox.showerror("Error", "Entity name is required.")
            return
        if not category:
            messagebox.showerror("Error", "Entity category is required.")
            return

        entity_id_str = self.entity_id_var.get()
        entity_id = int(entity_id_str) if entity_id_str else 0

        entity = ViralEntity(
            id=entity_id,
            name=name,
            category=category,
            entity_type=self.entity_type_var.get() or "None",
            description=self.entity_desc_text.get('1.0', tk.END).strip()
        )

        if entity_id in self.database.entities:
            self.database.update_entity(entity)
        else:
            self.database.add_entity(entity)

        self._filter_entities()
        self._update_status()

        # Update gene type dropdown if a protein was saved
        if category == EntityCategory.PROTEIN.value:
            self._update_gene_type_values()

        messagebox.showinfo("Success", f"Entity '{name}' saved.")

    def _delete_entity(self):
        """Delete the selected entity."""
        if not self.current_selection or self.current_selection[0] != 'entity':
            return
        entity_id = self.current_selection[1]
        if entity_id == 0:
            return

        # Check if entity is protected
        if self.database.is_protected_entity(entity_id):
            messagebox.showwarning(
                "Protected Entity",
                "This is a predefined starter entity and cannot be deleted."
            )
            return

        entity = self.database.get_entity(entity_id)
        if entity and messagebox.askyesno("Confirm Delete",
                                          f"Delete entity '{entity.name}'?"):
            was_protein = entity.category == EntityCategory.PROTEIN.value
            self.database.delete_entity(entity_id)
            self._clear_entity_form()
            self._filter_entities()
            self._update_status()

            # Update gene type dropdown if a protein was deleted
            if was_protein:
                self._update_gene_type_values()

    # ==================== EFFECTS TAB ====================

    def _create_effects_tab(self) -> ttk.Frame:
        """Create the effects tab."""
        tab = ttk.Frame(self.notebook)

        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel - list
        left_frame, self.effect_search_var, self.effect_listbox, btn_frame = \
            self._create_list_frame(tab, self._filter_effects, self._on_effect_select)

        ttk.Button(btn_frame, text="New Effect", command=self._new_effect).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_effect).pack(side=tk.LEFT, padx=2)

        paned.add(left_frame, weight=1)

        # Right panel - editor with scrollable frame
        right_container = ttk.Frame(tab)

        canvas = tk.Canvas(right_container)
        scrollbar = ttk.Scrollbar(right_container, orient="vertical", command=canvas.yview)
        right_frame = ttk.Frame(canvas)

        right_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=right_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        right_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(right_frame, text="Effect Editor", font=('TkDefaultFont', 12, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 10))

        row += 1
        ttk.Label(right_frame, text="ID:").grid(row=row, column=0, sticky='w', pady=2)
        self.effect_id_var = tk.StringVar()
        ttk.Label(right_frame, textvariable=self.effect_id_var).grid(row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Name:").grid(row=row, column=0, sticky='w', pady=2)
        self.effect_name_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.effect_name_var, width=40).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Effect Type:").grid(row=row, column=0, sticky='w', pady=2)
        self.effect_type_var = tk.StringVar()
        effect_type_combo = ttk.Combobox(right_frame, textvariable=self.effect_type_var,
                                          values=[t.value for t in EffectType], state='readonly', width=37)
        effect_type_combo.grid(row=row, column=1, sticky='w', pady=2)
        effect_type_combo.bind('<<ComboboxSelected>>', self._on_effect_type_change)

        row += 1
        ttk.Label(right_frame, text="Category (optional):").grid(row=row, column=0, sticky='w', pady=2)
        self.effect_category_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.effect_category_var, width=40).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        self.effect_global_var = tk.BooleanVar()
        ttk.Checkbutton(right_frame, text="Global effect (always applies)",
                        variable=self.effect_global_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Description:").grid(row=row, column=0, sticky='nw', pady=2)
        self.effect_desc_text = tk.Text(right_frame, width=40, height=3)
        self.effect_desc_text.grid(row=row, column=1, sticky='w', pady=2)

        # Transition-specific fields
        row += 1
        self.transition_frame = ttk.LabelFrame(right_frame, text="Transition Settings")
        self.transition_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=10)

        ttk.Label(self.transition_frame, text="Chance (%):").grid(row=0, column=0, sticky='w', pady=2, padx=5)
        self.effect_chance_var = tk.StringVar(value="100.0")
        ttk.Entry(self.transition_frame, textvariable=self.effect_chance_var, width=10).grid(
            row=0, column=1, sticky='w', pady=2)

        ttk.Label(self.transition_frame, text="Interferon Production:").grid(row=1, column=0, sticky='w', pady=2, padx=5)
        self.effect_interferon_var = tk.StringVar(value="0.0")
        ttk.Entry(self.transition_frame, textvariable=self.effect_interferon_var, width=10).grid(
            row=1, column=1, sticky='w', pady=2)

        ttk.Label(self.transition_frame, text="Antibody Response:").grid(row=2, column=0, sticky='w', pady=2, padx=5)
        self.effect_antibody_var = tk.StringVar(value="0.0")
        ttk.Entry(self.transition_frame, textvariable=self.effect_antibody_var, width=10).grid(
            row=2, column=1, sticky='w', pady=2)

        ttk.Label(self.transition_frame, text="Requires Genome Type:").grid(row=3, column=0, sticky='w', pady=2, padx=5)
        self.effect_genome_type_var = tk.StringVar()
        ttk.Entry(self.transition_frame, textvariable=self.effect_genome_type_var, width=20).grid(
            row=3, column=1, sticky='w', pady=2)

        # Inputs
        ttk.Label(self.transition_frame, text="Inputs:").grid(row=4, column=0, sticky='nw', pady=2, padx=5)
        self.inputs_listbox = tk.Listbox(self.transition_frame, height=4, width=50)
        self.inputs_listbox.grid(row=4, column=1, columnspan=2, sticky='w', pady=2)

        input_btn_frame = ttk.Frame(self.transition_frame)
        input_btn_frame.grid(row=5, column=1, sticky='w')
        ttk.Button(input_btn_frame, text="Add Input", command=self._add_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(input_btn_frame, text="Remove Input", command=self._remove_input).pack(side=tk.LEFT, padx=2)

        # Outputs
        ttk.Label(self.transition_frame, text="Outputs:").grid(row=6, column=0, sticky='nw', pady=2, padx=5)
        self.outputs_listbox = tk.Listbox(self.transition_frame, height=4, width=50)
        self.outputs_listbox.grid(row=6, column=1, columnspan=2, sticky='w', pady=2)

        output_btn_frame = ttk.Frame(self.transition_frame)
        output_btn_frame.grid(row=7, column=1, sticky='w')
        ttk.Button(output_btn_frame, text="Add Output", command=self._add_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(output_btn_frame, text="Add Unpack Genome", command=self._add_unpack_genome_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(output_btn_frame, text="Remove Output", command=self._remove_output).pack(side=tk.LEFT, padx=2)

        # Modify transition fields
        row += 1
        self.modify_frame = ttk.LabelFrame(right_frame, text="Modify Transition Settings")
        self.modify_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=10)

        ttk.Label(self.modify_frame, text="Target Effect ID:").grid(row=0, column=0, sticky='w', pady=2, padx=5)
        self.modify_target_id_var = tk.StringVar()
        ttk.Entry(self.modify_frame, textvariable=self.modify_target_id_var, width=10).grid(
            row=0, column=1, sticky='w', pady=2)

        ttk.Label(self.modify_frame, text="OR Target Category:").grid(row=1, column=0, sticky='w', pady=2, padx=5)
        self.modify_target_cat_var = tk.StringVar()
        ttk.Entry(self.modify_frame, textvariable=self.modify_target_cat_var, width=20).grid(
            row=1, column=1, sticky='w', pady=2)

        ttk.Label(self.modify_frame, text="Chance Modifier (%):").grid(row=2, column=0, sticky='w', pady=2, padx=5)
        self.modify_chance_var = tk.StringVar(value="0.0")
        ttk.Entry(self.modify_frame, textvariable=self.modify_chance_var, width=10).grid(
            row=2, column=1, sticky='w', pady=2)

        ttk.Label(self.modify_frame, text="Interferon Modifier:").grid(row=3, column=0, sticky='w', pady=2, padx=5)
        self.modify_interferon_var = tk.StringVar(value="0.0")
        ttk.Entry(self.modify_frame, textvariable=self.modify_interferon_var, width=10).grid(
            row=3, column=1, sticky='w', pady=2)

        ttk.Label(self.modify_frame, text="Antibody Modifier:").grid(row=4, column=0, sticky='w', pady=2, padx=5)
        self.modify_antibody_var = tk.StringVar(value="0.0")
        ttk.Entry(self.modify_frame, textvariable=self.modify_antibody_var, width=10).grid(
            row=4, column=1, sticky='w', pady=2)

        # Change location fields
        row += 1
        self.location_frame = ttk.LabelFrame(right_frame, text="Change Location Settings")
        self.location_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=10)

        ttk.Label(self.location_frame, text="Affected Entity ID:").grid(row=0, column=0, sticky='w', pady=2, padx=5)
        self.location_entity_var = tk.StringVar()
        ttk.Entry(self.location_frame, textvariable=self.location_entity_var, width=10).grid(
            row=0, column=1, sticky='w', pady=2)

        ttk.Label(self.location_frame, text="Source Location:").grid(row=1, column=0, sticky='w', pady=2, padx=5)
        self.location_source_var = tk.StringVar()
        ttk.Combobox(self.location_frame, textvariable=self.location_source_var,
                     values=[loc.value for loc in CellLocation], state='readonly', width=17).grid(
            row=1, column=1, sticky='w', pady=2)

        ttk.Label(self.location_frame, text="Target Location:").grid(row=2, column=0, sticky='w', pady=2, padx=5)
        self.location_target_var = tk.StringVar()
        ttk.Combobox(self.location_frame, textvariable=self.location_target_var,
                     values=[loc.value for loc in CellLocation], state='readonly', width=17).grid(
            row=2, column=1, sticky='w', pady=2)

        ttk.Label(self.location_frame, text="Chance (%):").grid(row=3, column=0, sticky='w', pady=2, padx=5)
        self.location_chance_var = tk.StringVar(value="100.0")
        ttk.Entry(self.location_frame, textvariable=self.location_chance_var, width=10).grid(
            row=3, column=1, sticky='w', pady=2)

        # Translation fields
        row += 1
        self.translation_frame = ttk.LabelFrame(right_frame, text="Translation Settings")
        self.translation_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=10)

        ttk.Label(self.translation_frame, text="Chance (%):").grid(row=0, column=0, sticky='w', pady=2, padx=5)
        self.translation_chance_var = tk.StringVar(value="100.0")
        ttk.Entry(self.translation_frame, textvariable=self.translation_chance_var, width=10).grid(
            row=0, column=1, sticky='w', pady=2)

        ttk.Label(self.translation_frame, text="ORF Targeting:").grid(row=1, column=0, sticky='w', pady=2, padx=5)
        self.orf_targeting_var = tk.StringVar(value="Random ORF")
        ttk.Combobox(self.translation_frame, textvariable=self.orf_targeting_var,
                     values=[t.value for t in OrfTargeting], state='readonly', width=17).grid(
            row=1, column=1, sticky='w', pady=2)

        # Templates (RNA inputs that are never consumed)
        ttk.Label(self.translation_frame, text="Templates (RNA):").grid(row=2, column=0, sticky='nw', pady=2, padx=5)
        self.templates_listbox = tk.Listbox(self.translation_frame, height=4, width=50)
        self.templates_listbox.grid(row=2, column=1, columnspan=2, sticky='w', pady=2)

        template_btn_frame = ttk.Frame(self.translation_frame)
        template_btn_frame.grid(row=3, column=1, sticky='w')
        ttk.Button(template_btn_frame, text="Add Template", command=self._add_template).pack(side=tk.LEFT, padx=2)
        ttk.Button(template_btn_frame, text="Remove Template", command=self._remove_template).pack(side=tk.LEFT, padx=2)

        # Save buttons
        row += 1
        btn_row = ttk.Frame(right_frame)
        btn_row.grid(row=row, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Button(btn_row, text="Save Effect", command=self._save_effect).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Clear", command=self._clear_effect_form).pack(side=tk.LEFT, padx=2)

        paned.add(right_container, weight=2)

        # Initially hide all type-specific frames
        self._on_effect_type_change()

        return tab

    def _on_effect_type_change(self, event=None):
        """Show/hide effect type specific fields."""
        effect_type = self.effect_type_var.get()

        # Hide all
        self.transition_frame.grid_remove()
        self.modify_frame.grid_remove()
        self.location_frame.grid_remove()
        self.translation_frame.grid_remove()

        if effect_type == EffectType.TRANSITION.value:
            self.transition_frame.grid()
        elif effect_type == EffectType.MODIFY_TRANSITION.value:
            self.modify_frame.grid()
        elif effect_type == EffectType.CHANGE_LOCATION.value:
            self.location_frame.grid()
        elif effect_type == EffectType.TRANSLATION.value:
            self.translation_frame.grid()

    def _filter_effects(self):
        """Filter the effect list based on search."""
        search = self.effect_search_var.get().lower()
        self.effect_listbox.delete(0, tk.END)
        for effect in sorted(self.database.effects.values(), key=lambda e: e.id):
            display = f"[{effect.id}] {effect.name} ({effect.effect_type})"
            if effect.is_global:
                display += " [GLOBAL]"
            if search in effect.name.lower() or search in effect.effect_type.lower():
                self.effect_listbox.insert(tk.END, display)

    def _on_effect_select(self):
        """Handle effect selection."""
        selection = self.effect_listbox.curselection()
        if not selection:
            return
        text = self.effect_listbox.get(selection[0])
        effect_id = int(text.split(']')[0][1:])
        effect = self.database.get_effect(effect_id)
        if effect:
            self._populate_effect_form(effect)
            self.current_selection = ('effect', effect.id)

    def _populate_effect_form(self, effect: Effect):
        """Populate the effect form with data."""
        self.effect_id_var.set(str(effect.id))
        self.effect_name_var.set(effect.name)
        self.effect_type_var.set(effect.effect_type)
        self.effect_category_var.set(effect.category)
        self.effect_global_var.set(effect.is_global)
        self.effect_desc_text.delete('1.0', tk.END)
        self.effect_desc_text.insert('1.0', effect.description)

        # Transition fields
        self.effect_chance_var.set(str(effect.chance))
        self.effect_interferon_var.set(str(effect.interferon_production))
        self.effect_antibody_var.set(str(effect.antibody_response))
        self.effect_genome_type_var.set(effect.requires_genome_type)

        self.inputs_listbox.delete(0, tk.END)
        self._current_inputs = list(effect.inputs)  # Copy the inputs list
        for inp in effect.inputs:
            entity = self.database.get_entity(inp.get('entity_id', 0))
            name = entity.name if entity else f"ID:{inp.get('entity_id')}"
            consumed = "consumed" if inp.get('consumed', True) else "kept"
            self.inputs_listbox.insert(tk.END,
                f"{inp.get('amount', 1)}x {name} @ {inp.get('location', 'Any')} ({consumed})")

        self.outputs_listbox.delete(0, tk.END)
        self._current_outputs = list(effect.outputs)  # Copy the outputs list
        for out in effect.outputs:
            if out.get('is_unpack_genome', False):
                self.outputs_listbox.insert(tk.END,
                    f"[UNPACK GENOME] @ {out.get('location', 'Cytosol')}")
            else:
                entity = self.database.get_entity(out.get('entity_id', 0))
                name = entity.name if entity else f"ID:{out.get('entity_id')}"
                self.outputs_listbox.insert(tk.END,
                    f"{out.get('amount', 1)}x {name} @ {out.get('location', 'Same')}")

        # Modify fields
        self.modify_target_id_var.set(str(effect.target_effect_id) if effect.target_effect_id else "")
        self.modify_target_cat_var.set(effect.target_category)
        self.modify_chance_var.set(str(effect.chance_modifier))
        self.modify_interferon_var.set(str(effect.interferon_modifier))
        self.modify_antibody_var.set(str(effect.antibody_modifier))

        # Location fields
        self.location_entity_var.set(str(effect.affected_entity_id) if effect.affected_entity_id else "")
        self.location_source_var.set(effect.source_location)
        self.location_target_var.set(effect.target_location)
        self.location_chance_var.set(str(effect.location_change_chance))

        # Translation fields
        self.translation_chance_var.set(str(effect.translation_chance))
        self.orf_targeting_var.set(effect.orf_targeting)
        self.templates_listbox.delete(0, tk.END)
        self._current_templates = list(effect.templates)
        for tmpl in effect.templates:
            entity = self.database.get_entity(tmpl.get('entity_id', 0))
            name = entity.name if entity else f"ID:{tmpl.get('entity_id')}"
            self.templates_listbox.insert(tk.END,
                f"{name} @ {tmpl.get('location', 'Cytosol')}")

        self._on_effect_type_change()

    def _new_effect(self):
        """Create a new effect."""
        self._clear_effect_form()
        self.effect_id_var.set(str(self.database.get_next_effect_id()))
        self.current_selection = ('effect', 0)

    def _clear_effect_form(self):
        """Clear the effect form."""
        self.effect_id_var.set("")
        self.effect_name_var.set("")
        self.effect_type_var.set("")
        self.effect_category_var.set("")
        self.effect_global_var.set(False)
        self.effect_desc_text.delete('1.0', tk.END)
        self.effect_chance_var.set("100.0")
        self.effect_interferon_var.set("0.0")
        self.effect_antibody_var.set("0.0")
        self.effect_genome_type_var.set("")
        self.inputs_listbox.delete(0, tk.END)
        self.outputs_listbox.delete(0, tk.END)
        self._current_inputs = []
        self._current_outputs = []
        self.modify_target_id_var.set("")
        self.modify_target_cat_var.set("")
        self.modify_chance_var.set("0.0")
        self.modify_interferon_var.set("0.0")
        self.modify_antibody_var.set("0.0")
        self.location_entity_var.set("")
        self.location_source_var.set("")
        self.location_target_var.set("")
        self.location_chance_var.set("100.0")
        # Translation fields
        self.translation_chance_var.set("100.0")
        self.orf_targeting_var.set("Random ORF")
        self.templates_listbox.delete(0, tk.END)
        self._current_templates = []
        self._on_effect_type_change()
        self.current_selection = None

    # Store inputs/outputs/templates data
    _current_inputs = []
    _current_outputs = []
    _current_templates = []

    def _add_input(self):
        """Add an input to the current effect."""
        dialog = InputOutputDialog(self, "Add Input", self.database, is_input=True)
        self.wait_window(dialog)
        if dialog.result:
            if not hasattr(self, '_current_inputs'):
                self._current_inputs = []
            self._current_inputs.append(dialog.result)
            entity = self.database.get_entity(dialog.result['entity_id'])
            name = entity.name if entity else f"ID:{dialog.result['entity_id']}"
            consumed = "consumed" if dialog.result.get('consumed', True) else "kept"
            self.inputs_listbox.insert(tk.END,
                f"{dialog.result['amount']}x {name} @ {dialog.result['location']} ({consumed})")

    def _remove_input(self):
        """Remove selected input."""
        selection = self.inputs_listbox.curselection()
        if selection:
            idx = selection[0]
            self.inputs_listbox.delete(idx)
            if hasattr(self, '_current_inputs') and idx < len(self._current_inputs):
                self._current_inputs.pop(idx)

    def _add_output(self):
        """Add an output to the current effect."""
        dialog = InputOutputDialog(self, "Add Output", self.database, is_input=False)
        self.wait_window(dialog)
        if dialog.result:
            if not hasattr(self, '_current_outputs'):
                self._current_outputs = []
            self._current_outputs.append(dialog.result)
            entity = self.database.get_entity(dialog.result['entity_id'])
            name = entity.name if entity else f"ID:{dialog.result['entity_id']}"
            self.outputs_listbox.insert(tk.END,
                f"{dialog.result['amount']}x {name} @ {dialog.result['location']}")

    def _add_unpack_genome_output(self):
        """Add an 'Unpack genome' output to the current effect."""
        dialog = UnpackGenomeDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            if not hasattr(self, '_current_outputs'):
                self._current_outputs = []
            self._current_outputs.append(dialog.result)
            self.outputs_listbox.insert(tk.END,
                f"[UNPACK GENOME] @ {dialog.result['location']}")

    def _remove_output(self):
        """Remove selected output."""
        selection = self.outputs_listbox.curselection()
        if selection:
            idx = selection[0]
            self.outputs_listbox.delete(idx)
            if hasattr(self, '_current_outputs') and idx < len(self._current_outputs):
                self._current_outputs.pop(idx)

    def _add_template(self):
        """Add a template (RNA entity) to the current Translation effect."""
        dialog = TemplateDialog(self, self.database)
        self.wait_window(dialog)
        if dialog.result:
            if not hasattr(self, '_current_templates'):
                self._current_templates = []
            self._current_templates.append(dialog.result)
            entity = self.database.get_entity(dialog.result['entity_id'])
            name = entity.name if entity else f"ID:{dialog.result['entity_id']}"
            self.templates_listbox.insert(tk.END,
                f"{name} @ {dialog.result['location']}")

    def _remove_template(self):
        """Remove selected template."""
        selection = self.templates_listbox.curselection()
        if selection:
            idx = selection[0]
            self.templates_listbox.delete(idx)
            if hasattr(self, '_current_templates') and idx < len(self._current_templates):
                self._current_templates.pop(idx)

    def _save_effect(self):
        """Save the current effect."""
        name = self.effect_name_var.get().strip()
        effect_type = self.effect_type_var.get()

        if not name:
            messagebox.showerror("Error", "Effect name is required.")
            return
        if not effect_type:
            messagebox.showerror("Error", "Effect type is required.")
            return

        effect_id_str = self.effect_id_var.get()
        effect_id = int(effect_id_str) if effect_id_str else 0

        # Get inputs/outputs/templates from instance or existing effect
        inputs = getattr(self, '_current_inputs', [])
        outputs = getattr(self, '_current_outputs', [])
        templates = getattr(self, '_current_templates', [])

        effect = Effect(
            id=effect_id,
            name=name,
            effect_type=effect_type,
            category=self.effect_category_var.get(),
            description=self.effect_desc_text.get('1.0', tk.END).strip(),
            is_global=self.effect_global_var.get(),
            inputs=inputs,
            outputs=outputs,
            chance=float(self.effect_chance_var.get() or 100),
            interferon_production=float(self.effect_interferon_var.get() or 0),
            antibody_response=float(self.effect_antibody_var.get() or 0),
            requires_genome_type=self.effect_genome_type_var.get(),
            target_effect_id=int(self.modify_target_id_var.get()) if self.modify_target_id_var.get() else None,
            target_category=self.modify_target_cat_var.get(),
            chance_modifier=float(self.modify_chance_var.get() or 0),
            interferon_modifier=float(self.modify_interferon_var.get() or 0),
            antibody_modifier=float(self.modify_antibody_var.get() or 0),
            source_location=self.location_source_var.get(),
            target_location=self.location_target_var.get(),
            affected_entity_id=int(self.location_entity_var.get()) if self.location_entity_var.get() else None,
            location_change_chance=float(self.location_chance_var.get() or 100),
            templates=templates,
            translation_chance=float(self.translation_chance_var.get() or 100),
            orf_targeting=self.orf_targeting_var.get() or "Random ORF"
        )

        if effect_id in self.database.effects:
            self.database.update_effect(effect)
        else:
            self.database.add_effect(effect)

        self._filter_effects()
        self._update_status()
        messagebox.showinfo("Success", f"Effect '{name}' saved.")

    def _delete_effect(self):
        """Delete the selected effect."""
        if not self.current_selection or self.current_selection[0] != 'effect':
            return
        effect_id = self.current_selection[1]
        if effect_id == 0:
            return

        effect = self.database.get_effect(effect_id)
        if effect:
            genes = self.database.get_genes_with_effect(effect_id)
            warning = f"Delete effect '{effect.name}'?"
            if genes:
                warning += f"\n\nThis effect is used by {len(genes)} gene(s)."

            if messagebox.askyesno("Confirm Delete", warning):
                self.database.delete_effect(effect_id)
                self._clear_effect_form()
                self._filter_effects()
                self._update_status()

    # ==================== GENES TAB ====================

    def _create_genes_tab(self) -> ttk.Frame:
        """Create the genes tab."""
        tab = ttk.Frame(self.notebook)

        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel - list
        left_frame, self.gene_search_var, self.gene_listbox, btn_frame = \
            self._create_list_frame(tab, self._filter_genes, self._on_gene_select)

        ttk.Button(btn_frame, text="New Gene", command=self._new_gene).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_gene).pack(side=tk.LEFT, padx=2)

        paned.add(left_frame, weight=1)

        # Right panel - editor
        right_frame = ttk.Frame(tab)
        right_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(right_frame, text="Gene Editor", font=('TkDefaultFont', 12, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 10))

        row += 1
        ttk.Label(right_frame, text="ID:").grid(row=row, column=0, sticky='w', pady=2)
        self.gene_id_var = tk.StringVar()
        ttk.Label(right_frame, textvariable=self.gene_id_var).grid(row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Name:").grid(row=row, column=0, sticky='w', pady=2)
        self.gene_name_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.gene_name_var, width=40).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Set Name:").grid(row=row, column=0, sticky='w', pady=2)
        self.gene_set_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.gene_set_var, width=40).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Install Cost (EP):").grid(row=row, column=0, sticky='w', pady=2)
        self.gene_cost_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.gene_cost_var, width=10).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Length (bp):").grid(row=row, column=0, sticky='w', pady=2)
        self.gene_length_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.gene_length_var, width=10).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Type (enables):").grid(row=row, column=0, sticky='w', pady=2)
        self.gene_type_var = tk.StringVar()
        self.gene_type_combo = ttk.Combobox(right_frame, textvariable=self.gene_type_var,
                     values=["None"], state='readonly', width=37)
        self.gene_type_combo.grid(row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Description:").grid(row=row, column=0, sticky='nw', pady=2)
        self.gene_desc_text = tk.Text(right_frame, width=40, height=3)
        self.gene_desc_text.grid(row=row, column=1, sticky='w', pady=2)

        # Effects section
        row += 1
        ttk.Label(right_frame, text="Attached Effects:").grid(row=row, column=0, sticky='nw', pady=2)

        effects_frame = ttk.Frame(right_frame)
        effects_frame.grid(row=row, column=1, sticky='w', pady=2)

        self.gene_effects_listbox = tk.Listbox(effects_frame, height=6, width=50)
        self.gene_effects_listbox.pack(side=tk.LEFT)

        effects_btn_frame = ttk.Frame(effects_frame)
        effects_btn_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(effects_btn_frame, text="Add Effect", command=self._add_gene_effect).pack(pady=2)
        ttk.Button(effects_btn_frame, text="Remove Effect", command=self._remove_gene_effect).pack(pady=2)

        row += 1
        btn_row = ttk.Frame(right_frame)
        btn_row.grid(row=row, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Button(btn_row, text="Save Gene", command=self._save_gene).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Clear", command=self._clear_gene_form).pack(side=tk.LEFT, padx=2)

        paned.add(right_frame, weight=2)

        return tab

    def _update_gene_type_values(self):
        """Update the gene type combobox with current protein entities."""
        protein_entities = self.database.get_protein_entities()
        values = ["None"] + [f"[{e.id}] {e.name}" for e in sorted(protein_entities, key=lambda e: e.id)]
        self.gene_type_combo['values'] = values

    def _filter_genes(self):
        """Filter the gene list based on search."""
        # Update gene type dropdown values
        self._update_gene_type_values()

        search = self.gene_search_var.get().lower()
        self.gene_listbox.delete(0, tk.END)
        for gene in sorted(self.database.genes.values(), key=lambda g: g.id):
            display = f"[{gene.id}] ({gene.set_name}) {gene.name}"
            if search in gene.name.lower() or search in gene.set_name.lower():
                self.gene_listbox.insert(tk.END, display)

    def _on_gene_select(self):
        """Handle gene selection."""
        selection = self.gene_listbox.curselection()
        if not selection:
            return
        text = self.gene_listbox.get(selection[0])
        gene_id = int(text.split(']')[0][1:])
        gene = self.database.get_gene(gene_id)
        if gene:
            self._populate_gene_form(gene)
            self.current_selection = ('gene', gene.id)

    def _populate_gene_form(self, gene: Gene):
        """Populate the gene form with data."""
        self.gene_id_var.set(str(gene.id))
        self.gene_name_var.set(gene.name)
        self.gene_set_var.set(gene.set_name)
        self.gene_cost_var.set(str(gene.install_cost))
        self.gene_length_var.set(str(gene.length))

        # Set gene type based on entity ID
        if gene.gene_type_entity_id is not None:
            entity = self.database.get_entity(gene.gene_type_entity_id)
            if entity and entity.category == "Protein":
                self.gene_type_var.set(f"[{entity.id}] {entity.name}")
            else:
                self.gene_type_var.set("None")
        else:
            self.gene_type_var.set("None")

        self.gene_desc_text.delete('1.0', tk.END)
        self.gene_desc_text.insert('1.0', gene.description)

        self.gene_effects_listbox.delete(0, tk.END)
        self._current_gene_effects = list(gene.effect_ids)
        for eid in gene.effect_ids:
            effect = self.database.get_effect(eid)
            if effect:
                self.gene_effects_listbox.insert(tk.END, f"[{effect.id}] {effect.name}")

    def _new_gene(self):
        """Create a new gene."""
        self._clear_gene_form()
        self.gene_id_var.set(str(self.database.get_next_gene_id()))
        self.current_selection = ('gene', 0)

    def _clear_gene_form(self):
        """Clear the gene form."""
        self.gene_id_var.set("")
        self.gene_name_var.set("")
        self.gene_set_var.set("")
        self.gene_cost_var.set("")
        self.gene_length_var.set("")
        self.gene_type_var.set("None")
        self.gene_desc_text.delete('1.0', tk.END)
        self.gene_effects_listbox.delete(0, tk.END)
        self._current_gene_effects = []
        self.current_selection = None

    _current_gene_effects = []

    def _add_gene_effect(self):
        """Add an effect to the current gene."""
        dialog = SelectEffectDialog(self, self.database)
        self.wait_window(dialog)
        if dialog.result:
            effect_id = dialog.result
            if effect_id not in self._current_gene_effects:
                self._current_gene_effects.append(effect_id)
                effect = self.database.get_effect(effect_id)
                if effect:
                    self.gene_effects_listbox.insert(tk.END, f"[{effect.id}] {effect.name}")

    def _remove_gene_effect(self):
        """Remove selected effect from gene."""
        selection = self.gene_effects_listbox.curselection()
        if selection:
            idx = selection[0]
            self.gene_effects_listbox.delete(idx)
            if idx < len(self._current_gene_effects):
                self._current_gene_effects.pop(idx)

    def _save_gene(self):
        """Save the current gene."""
        name = self.gene_name_var.get().strip()
        set_name = self.gene_set_var.get().strip()

        if not name:
            messagebox.showerror("Error", "Gene name is required.")
            return
        if not set_name:
            messagebox.showerror("Error", "Set name is required.")
            return

        try:
            cost = int(self.gene_cost_var.get() or 0)
            length = int(self.gene_length_var.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Cost and length must be integers.")
            return

        gene_id_str = self.gene_id_var.get()
        gene_id = int(gene_id_str) if gene_id_str else 0

        # Parse gene type entity ID from selection
        gene_type_selection = self.gene_type_var.get()
        gene_type_entity_id = None
        if gene_type_selection and gene_type_selection != "None":
            try:
                # Format is "[id] name"
                gene_type_entity_id = int(gene_type_selection.split(']')[0][1:])
            except (ValueError, IndexError):
                pass

        gene = Gene(
            id=gene_id,
            name=name,
            set_name=set_name,
            install_cost=cost,
            length=length,
            gene_type_entity_id=gene_type_entity_id,
            effect_ids=list(self._current_gene_effects),
            description=self.gene_desc_text.get('1.0', tk.END).strip()
        )

        if gene_id in self.database.genes:
            self.database.update_gene(gene)
        else:
            self.database.add_gene(gene)

        self._filter_genes()
        self._update_status()
        messagebox.showinfo("Success", f"Gene '{name}' saved.")

    def _delete_gene(self):
        """Delete the selected gene."""
        if not self.current_selection or self.current_selection[0] != 'gene':
            return
        gene_id = self.current_selection[1]
        if gene_id == 0:
            return

        gene = self.database.get_gene(gene_id)
        if gene and messagebox.askyesno("Confirm Delete", f"Delete gene '{gene.name}'?"):
            self.database.delete_gene(gene_id)
            self._clear_gene_form()
            self._filter_genes()
            self._update_status()

    # ==================== MILESTONES TAB ====================

    def _create_milestones_tab(self) -> ttk.Frame:
        """Create the milestones tab."""
        tab = ttk.Frame(self.notebook)

        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel - list
        left_frame, self.milestone_search_var, self.milestone_listbox, btn_frame = \
            self._create_list_frame(tab, self._filter_milestones, self._on_milestone_select)

        ttk.Button(btn_frame, text="New Milestone", command=self._new_milestone).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_milestone).pack(side=tk.LEFT, padx=2)

        paned.add(left_frame, weight=1)

        # Right panel - editor
        right_frame = ttk.Frame(tab)
        right_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(right_frame, text="Milestone Editor", font=('TkDefaultFont', 12, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 10))

        row += 1
        ttk.Label(right_frame, text="ID:").grid(row=row, column=0, sticky='w', pady=2)
        self.milestone_id_var = tk.StringVar()
        ttk.Label(right_frame, textvariable=self.milestone_id_var).grid(row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Name:").grid(row=row, column=0, sticky='w', pady=2)
        self.milestone_name_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.milestone_name_var, width=40).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Milestone Type:").grid(row=row, column=0, sticky='w', pady=2)
        self.milestone_type_var = tk.StringVar()
        milestone_type_combo = ttk.Combobox(right_frame, textvariable=self.milestone_type_var,
                                             values=[t.value for t in MilestoneType], state='readonly', width=37)
        milestone_type_combo.grid(row=row, column=1, sticky='w', pady=2)
        milestone_type_combo.bind('<<ComboboxSelected>>', self._on_milestone_type_change)

        row += 1
        ttk.Label(right_frame, text="Reward (EP):").grid(row=row, column=0, sticky='w', pady=2)
        self.milestone_reward_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.milestone_reward_var, width=10).grid(
            row=row, column=1, sticky='w', pady=2)

        row += 1
        ttk.Label(right_frame, text="Description:").grid(row=row, column=0, sticky='nw', pady=2)
        self.milestone_desc_text = tk.Text(right_frame, width=40, height=3)
        self.milestone_desc_text.grid(row=row, column=1, sticky='w', pady=2)

        # Type-specific fields
        row += 1
        self.milestone_params_frame = ttk.LabelFrame(right_frame, text="Parameters")
        self.milestone_params_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=10)

        # Compartment field
        ttk.Label(self.milestone_params_frame, text="Target Compartment:").grid(
            row=0, column=0, sticky='w', pady=2, padx=5)
        self.milestone_compartment_var = tk.StringVar()
        self.milestone_compartment_combo = ttk.Combobox(
            self.milestone_params_frame, textvariable=self.milestone_compartment_var,
            values=[loc.value for loc in CellLocation], state='readonly', width=17)
        self.milestone_compartment_combo.grid(row=0, column=1, sticky='w', pady=2)

        # Entity category field
        ttk.Label(self.milestone_params_frame, text="Target Entity Category:").grid(
            row=1, column=0, sticky='w', pady=2, padx=5)
        self.milestone_entity_cat_var = tk.StringVar()
        self.milestone_entity_cat_combo = ttk.Combobox(
            self.milestone_params_frame, textvariable=self.milestone_entity_cat_var,
            values=[c.value for c in EntityCategory], state='readonly', width=17)
        self.milestone_entity_cat_combo.grid(row=1, column=1, sticky='w', pady=2)

        # Count field
        ttk.Label(self.milestone_params_frame, text="Target Count:").grid(
            row=2, column=0, sticky='w', pady=2, padx=5)
        self.milestone_count_var = tk.StringVar()
        self.milestone_count_entry = ttk.Entry(
            self.milestone_params_frame, textvariable=self.milestone_count_var, width=10)
        self.milestone_count_entry.grid(row=2, column=1, sticky='w', pady=2)

        # Turns field
        ttk.Label(self.milestone_params_frame, text="Target Turns:").grid(
            row=3, column=0, sticky='w', pady=2, padx=5)
        self.milestone_turns_var = tk.StringVar()
        self.milestone_turns_entry = ttk.Entry(
            self.milestone_params_frame, textvariable=self.milestone_turns_var, width=10)
        self.milestone_turns_entry.grid(row=3, column=1, sticky='w', pady=2)

        row += 1
        btn_row = ttk.Frame(right_frame)
        btn_row.grid(row=row, column=0, columnspan=2, sticky='w', pady=10)
        ttk.Button(btn_row, text="Save Milestone", command=self._save_milestone).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Clear", command=self._clear_milestone_form).pack(side=tk.LEFT, padx=2)

        paned.add(right_frame, weight=2)

        return tab

    def _on_milestone_type_change(self, event=None):
        """Show/hide milestone type specific fields."""
        milestone_type = self.milestone_type_var.get()

        # Disable all first
        self.milestone_compartment_combo.config(state='disabled')
        self.milestone_entity_cat_combo.config(state='disabled')
        self.milestone_count_entry.config(state='disabled')
        self.milestone_turns_entry.config(state='disabled')

        if milestone_type == MilestoneType.ENTER_COMPARTMENT.value:
            self.milestone_compartment_combo.config(state='readonly')
        elif milestone_type == MilestoneType.PRODUCE_FIRST_ENTITY.value:
            self.milestone_entity_cat_combo.config(state='readonly')
        elif milestone_type == MilestoneType.PRODUCE_ENTITY_COUNT.value:
            self.milestone_entity_cat_combo.config(state='readonly')
            self.milestone_count_entry.config(state='normal')
        elif milestone_type == MilestoneType.SURVIVE_TURNS.value:
            self.milestone_turns_entry.config(state='normal')

    def _filter_milestones(self):
        """Filter the milestone list based on search."""
        search = self.milestone_search_var.get().lower()
        self.milestone_listbox.delete(0, tk.END)
        for milestone in sorted(self.database.milestones.values(), key=lambda m: m.id):
            display = f"[{milestone.id}] {milestone.name} (+{milestone.reward_ep} EP)"
            if search in milestone.name.lower() or search in milestone.milestone_type.lower():
                self.milestone_listbox.insert(tk.END, display)

    def _on_milestone_select(self):
        """Handle milestone selection."""
        selection = self.milestone_listbox.curselection()
        if not selection:
            return
        text = self.milestone_listbox.get(selection[0])
        milestone_id = int(text.split(']')[0][1:])
        milestone = self.database.get_milestone(milestone_id)
        if milestone:
            self._populate_milestone_form(milestone)
            self.current_selection = ('milestone', milestone.id)

    def _populate_milestone_form(self, milestone: Milestone):
        """Populate the milestone form with data."""
        self.milestone_id_var.set(str(milestone.id))
        self.milestone_name_var.set(milestone.name)
        self.milestone_type_var.set(milestone.milestone_type)
        self.milestone_reward_var.set(str(milestone.reward_ep))
        self.milestone_desc_text.delete('1.0', tk.END)
        self.milestone_desc_text.insert('1.0', milestone.description)
        self.milestone_compartment_var.set(milestone.target_compartment)
        self.milestone_entity_cat_var.set(milestone.target_entity_category)
        self.milestone_count_var.set(str(milestone.target_count) if milestone.target_count else "")
        self.milestone_turns_var.set(str(milestone.target_turns) if milestone.target_turns else "")
        self._on_milestone_type_change()

    def _new_milestone(self):
        """Create a new milestone."""
        self._clear_milestone_form()
        self.milestone_id_var.set(str(self.database.get_next_milestone_id()))
        self.current_selection = ('milestone', 0)

    def _clear_milestone_form(self):
        """Clear the milestone form."""
        self.milestone_id_var.set("")
        self.milestone_name_var.set("")
        self.milestone_type_var.set("")
        self.milestone_reward_var.set("")
        self.milestone_desc_text.delete('1.0', tk.END)
        self.milestone_compartment_var.set("")
        self.milestone_entity_cat_var.set("")
        self.milestone_count_var.set("")
        self.milestone_turns_var.set("")
        self._on_milestone_type_change()
        self.current_selection = None

    def _save_milestone(self):
        """Save the current milestone."""
        name = self.milestone_name_var.get().strip()
        milestone_type = self.milestone_type_var.get()

        if not name:
            messagebox.showerror("Error", "Milestone name is required.")
            return
        if not milestone_type:
            messagebox.showerror("Error", "Milestone type is required.")
            return

        try:
            reward = int(self.milestone_reward_var.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Reward must be an integer.")
            return

        milestone_id_str = self.milestone_id_var.get()
        milestone_id = int(milestone_id_str) if milestone_id_str else 0

        milestone = Milestone(
            id=milestone_id,
            name=name,
            milestone_type=milestone_type,
            reward_ep=reward,
            description=self.milestone_desc_text.get('1.0', tk.END).strip(),
            target_compartment=self.milestone_compartment_var.get(),
            target_entity_category=self.milestone_entity_cat_var.get(),
            target_count=int(self.milestone_count_var.get()) if self.milestone_count_var.get() else 0,
            target_turns=int(self.milestone_turns_var.get()) if self.milestone_turns_var.get() else 0
        )

        if milestone_id in self.database.milestones:
            self.database.update_milestone(milestone)
        else:
            self.database.add_milestone(milestone)

        self._filter_milestones()
        self._update_status()
        messagebox.showinfo("Success", f"Milestone '{name}' saved.")

    def _delete_milestone(self):
        """Delete the selected milestone."""
        if not self.current_selection or self.current_selection[0] != 'milestone':
            return
        milestone_id = self.current_selection[1]
        if milestone_id == 0:
            return

        milestone = self.database.get_milestone(milestone_id)
        if milestone and messagebox.askyesno("Confirm Delete", f"Delete milestone '{milestone.name}'?"):
            self.database.delete_milestone(milestone_id)
            self._clear_milestone_form()
            self._filter_milestones()
            self._update_status()

    # ==================== GLOBAL SETTINGS TAB ====================

    def _create_settings_tab(self) -> ttk.Frame:
        """Create the global settings tab."""
        tab = ttk.Frame(self.notebook)

        # Create a canvas with scrollbar for the settings
        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Main container with padding
        main_frame = ttk.Frame(scrollable_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ===== DEGRADATION SECTION =====
        ttk.Label(main_frame, text="Degradation Chances",
                  font=('TkDefaultFont', 12, 'bold')).pack(anchor='w', pady=(0, 5))

        ttk.Label(main_frame, text="Set the base degradation chance (%) per turn for each entity category at each location.",
                  wraplength=800).pack(anchor='w', pady=(0, 10))

        # Create a frame for the degradation grid
        grid_frame = ttk.LabelFrame(main_frame, text="Degradation % per Turn")
        grid_frame.pack(fill=tk.X)

        # Column headers (locations)
        locations = [loc.value for loc in CellLocation]
        categories = [cat.value for cat in EntityCategory]

        # Store entry widgets for later access
        self.degradation_entries = {}

        # Header row
        ttk.Label(grid_frame, text="Category \\ Location", font=('TkDefaultFont', 9, 'bold'),
                  width=15).grid(row=0, column=0, padx=5, pady=5, sticky='w')

        for col, location in enumerate(locations, start=1):
            ttk.Label(grid_frame, text=location, font=('TkDefaultFont', 9, 'bold'),
                      width=12).grid(row=0, column=col, padx=2, pady=5)

        # Data rows
        for row, category in enumerate(categories, start=1):
            ttk.Label(grid_frame, text=category, width=15).grid(
                row=row, column=0, padx=5, pady=2, sticky='w')

            for col, location in enumerate(locations, start=1):
                var = tk.StringVar()
                entry = ttk.Entry(grid_frame, textvariable=var, width=8)
                entry.grid(row=row, column=col, padx=2, pady=2)

                # Store reference
                self.degradation_entries[(category, location)] = var

        # ===== INTERFERON MODIFIER SECTION =====
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=15)

        ttk.Label(main_frame, text="Interferon Degradation Modifiers",
                  font=('TkDefaultFont', 12, 'bold')).pack(anchor='w', pady=(0, 5))

        ttk.Label(main_frame, text="Set the % increase in degradation chance at maximum interferon level (100) for each category. "
                  "100% means degradation doubles. The modifier scales linearly with interferon level.",
                  wraplength=800).pack(anchor='w', pady=(0, 10))

        # Create a frame for the interferon modifiers
        ifn_frame = ttk.LabelFrame(main_frame, text="Interferon Modifier % (at max interferon)")
        ifn_frame.pack(fill=tk.X)

        # Store interferon modifier entries
        self.interferon_entries = {}

        # Create entries for each category
        for row, category in enumerate(categories):
            ttk.Label(ifn_frame, text=category, width=15).grid(
                row=row, column=0, padx=5, pady=2, sticky='w')

            var = tk.StringVar()
            entry = ttk.Entry(ifn_frame, textvariable=var, width=10)
            entry.grid(row=row, column=1, padx=5, pady=2, sticky='w')

            ttk.Label(ifn_frame, text="%").grid(row=row, column=2, padx=2, pady=2, sticky='w')

            self.interferon_entries[category] = var

        # ===== BUTTONS =====
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=15)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="Apply All Changes",
                   command=self._apply_all_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Reset All to Defaults",
                   command=self._reset_all_settings_to_defaults).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Reload from Database",
                   command=self._load_all_settings).pack(side=tk.LEFT, padx=5)

        # Info label
        info_text = ("Example: If RNA has base degradation 6% in Cytosol and interferon modifier 100%, "
                     "at interferon level 50, actual degradation = 6% * (1 + 100% * 50/100) = 9%. "
                     "Final degradation is capped at 100%.")
        ttk.Label(main_frame, text=info_text, wraplength=800,
                  font=('TkDefaultFont', 9, 'italic')).pack(anchor='w', pady=10)

        return tab

    def _load_degradation_values(self):
        """Load degradation values from the database into the entry fields."""
        for (category, location), var in self.degradation_entries.items():
            value = self.database.get_degradation_chance(category, location)
            var.set(f"{value:.1f}")

    def _load_interferon_values(self):
        """Load interferon modifier values from the database into the entry fields."""
        for category, var in self.interferon_entries.items():
            value = self.database.get_interferon_modifier(category)
            var.set(f"{value:.1f}")

    def _load_all_settings(self):
        """Load all settings from the database."""
        self._load_degradation_values()
        self._load_interferon_values()

    def _apply_all_settings(self):
        """Apply all settings changes to the database."""
        errors = []

        # Validate and apply degradation chances
        for (category, location), var in self.degradation_entries.items():
            value_str = var.get().strip()
            try:
                value = float(value_str)
                if value < 0 or value > 100:
                    errors.append(f"Degradation {category}/{location}: Value must be between 0 and 100")
                else:
                    self.database.set_degradation_chance(category, location, value)
            except ValueError:
                errors.append(f"Degradation {category}/{location}: Invalid number '{value_str}'")

        # Validate and apply interferon modifiers (can be > 100)
        for category, var in self.interferon_entries.items():
            value_str = var.get().strip()
            try:
                value = float(value_str)
                if value < 0:
                    errors.append(f"Interferon {category}: Value must be >= 0")
                else:
                    self.database.set_interferon_modifier(category, value)
            except ValueError:
                errors.append(f"Interferon {category}: Invalid number '{value_str}'")

        if errors:
            messagebox.showerror("Validation Errors",
                                "The following errors were found:\n\n" + "\n".join(errors[:10]))
        else:
            self._update_status()
            messagebox.showinfo("Success", "All settings updated.")

    def _reset_all_settings_to_defaults(self):
        """Reset all settings to default values."""
        if messagebox.askyesno("Reset Defaults",
                               "Reset all degradation and interferon settings to default values?"):
            self.database.reset_degradation_to_defaults()
            self.database.reset_interferon_modifiers_to_defaults()
            self._load_all_settings()
            self._update_status()
            messagebox.showinfo("Reset", "All settings reset to defaults.")

    # ==================== DATABASE OPERATIONS ====================

    def _new_database(self):
        """Create a new database."""
        if self.database.modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before creating a new database?"
            )
            if result is True:
                if not self._save_database():
                    return
            elif result is None:
                return

        self.database.new_database()
        self._refresh_all_lists()
        self._update_status()

    def _open_database(self):
        """Open an existing database."""
        if self.database.modified:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before opening another database?"
            )
            if result is True:
                if not self._save_database():
                    return
            elif result is None:
                return

        filepath = filedialog.askopenfilename(
            title="Open Database",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            if self.database.load(filepath):
                self._refresh_all_lists()
                self._update_status()
                messagebox.showinfo("Success", "Database loaded successfully.")
            else:
                messagebox.showerror("Error", "Failed to load database.")

    def _save_database(self) -> bool:
        """Save the current database."""
        if not self.database.filepath:
            return self._save_database_as()

        if self.database.save():
            self._update_status()
            return True
        else:
            messagebox.showerror("Error", "Failed to save database.")
            return False

    def _save_database_as(self) -> bool:
        """Save the database to a new file."""
        filepath = filedialog.asksaveasfilename(
            title="Save Database As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filepath:
            if self.database.save(filepath):
                self._update_status()
                return True
            else:
                messagebox.showerror("Error", "Failed to save database.")
                return False
        return False

    def _refresh_all_lists(self):
        """Refresh all list views."""
        self._filter_entities()
        self._filter_effects()
        self._filter_genes()
        self._filter_milestones()
        self._load_all_settings()

    def _update_status(self):
        """Update the status bar."""
        if self.database.filepath:
            status = f"Database: {self.database.filepath.name}"
        else:
            status = "New database (unsaved)"

        if self.database.modified:
            status += " *"

        counts = (f"Entities: {len(self.database.entities)} | "
                  f"Effects: {len(self.database.effects)} | "
                  f"Genes: {len(self.database.genes)} | "
                  f"Milestones: {len(self.database.milestones)}")

        self.status_var.set(f"{status}  |  {counts}")


class InputOutputDialog(tk.Toplevel):
    """Dialog for adding input/output entities to transitions."""

    def __init__(self, parent, title: str, database: GameDatabase, is_input: bool):
        super().__init__(parent)
        self.title(title)
        self.database = database
        self.is_input = is_input
        self.result = None

        self.transient(parent)
        self.grab_set()

        self._create_ui()
        self.geometry("350x250")

    def _create_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Entity selection
        ttk.Label(frame, text="Entity:").grid(row=0, column=0, sticky='w', pady=5)
        self.entity_var = tk.StringVar()
        entities = [(e.id, f"[{e.id}] {e.name}") for e in self.database.entities.values()]
        self.entity_combo = ttk.Combobox(frame, textvariable=self.entity_var,
                                          values=[e[1] for e in entities], width=30)
        self.entity_combo.grid(row=0, column=1, sticky='w', pady=5)

        # Amount
        ttk.Label(frame, text="Amount:").grid(row=1, column=0, sticky='w', pady=5)
        self.amount_var = tk.StringVar(value="1")
        ttk.Entry(frame, textvariable=self.amount_var, width=10).grid(row=1, column=1, sticky='w', pady=5)

        # Location
        ttk.Label(frame, text="Location:").grid(row=2, column=0, sticky='w', pady=5)
        self.location_var = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.location_var,
                     values=[loc.value for loc in CellLocation], state='readonly', width=17).grid(
            row=2, column=1, sticky='w', pady=5)

        # Consumed (only for inputs)
        if self.is_input:
            self.consumed_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(frame, text="Consumed", variable=self.consumed_var).grid(
                row=3, column=0, columnspan=2, sticky='w', pady=5)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _ok(self):
        entity_text = self.entity_var.get()
        if not entity_text:
            messagebox.showerror("Error", "Please select an entity.")
            return

        try:
            entity_id = int(entity_text.split(']')[0][1:])
            amount = int(self.amount_var.get())
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Invalid entity or amount.")
            return

        location = self.location_var.get()
        if not location:
            messagebox.showerror("Error", "Please select a location.")
            return

        self.result = {
            'entity_id': entity_id,
            'amount': amount,
            'location': location
        }
        if self.is_input:
            self.result['consumed'] = self.consumed_var.get()

        self.destroy()


class SelectEffectDialog(tk.Toplevel):
    """Dialog for selecting an effect to attach to a gene."""

    def __init__(self, parent, database: GameDatabase):
        super().__init__(parent)
        self.title("Select Effect")
        self.database = database
        self.result = None

        self.transient(parent)
        self.grab_set()

        self._create_ui()
        self.geometry("400x350")

    def _create_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Search
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_var.trace('w', lambda *args: self._filter())

        # Listbox
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        self._filter()

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Select", command=self._select).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _filter(self):
        search = self.search_var.get().lower()
        self.listbox.delete(0, tk.END)
        for effect in sorted(self.database.effects.values(), key=lambda e: e.id):
            if not effect.is_global:  # Don't show global effects
                display = f"[{effect.id}] {effect.name} ({effect.effect_type})"
                if search in effect.name.lower() or search in effect.effect_type.lower():
                    self.listbox.insert(tk.END, display)

    def _select(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "Please select an effect.")
            return

        text = self.listbox.get(selection[0])
        self.result = int(text.split(']')[0][1:])
        self.destroy()


class UnpackGenomeDialog(tk.Toplevel):
    """Dialog for adding an 'Unpack genome' output to a transition."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Unpack Genome Output")
        self.result = None

        self.transient(parent)
        self.grab_set()

        self._create_ui()
        self.geometry("300x150")

    def _create_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="This output will spawn the virus's genome\nentity when the transition fires.",
                  wraplength=250).grid(row=0, column=0, columnspan=2, pady=10)

        # Location
        ttk.Label(frame, text="Location:").grid(row=1, column=0, sticky='w', pady=5)
        self.location_var = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.location_var,
                     values=[loc.value for loc in CellLocation], state='readonly', width=17).grid(
            row=1, column=1, sticky='w', pady=5)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _ok(self):
        location = self.location_var.get()
        if not location:
            messagebox.showerror("Error", "Please select a location.")
            return

        self.result = {
            'entity_id': 0,  # Not used for unpack genome
            'amount': 1,  # Will spawn all genome entities
            'location': location,
            'is_unpack_genome': True
        }
        self.destroy()


class TemplateDialog(tk.Toplevel):
    """Dialog for adding RNA template entities to Translation effects."""

    def __init__(self, parent, database: GameDatabase):
        super().__init__(parent)
        self.title("Add Template (RNA)")
        self.database = database
        self.result = None

        self.transient(parent)
        self.grab_set()

        self._create_ui()
        self.geometry("350x200")

    def _create_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Templates are RNA entities that can be\nused for translation. They are never consumed.",
                  wraplength=300).grid(row=0, column=0, columnspan=2, pady=10)

        # Entity selection - only RNA entities
        ttk.Label(frame, text="RNA Entity:").grid(row=1, column=0, sticky='w', pady=5)
        self.entity_var = tk.StringVar()
        rna_entities = [(e.id, f"[{e.id}] {e.name}")
                        for e in self.database.entities.values()
                        if e.category == EntityCategory.RNA.value]
        self.entity_combo = ttk.Combobox(frame, textvariable=self.entity_var,
                                          values=[e[1] for e in rna_entities], width=30)
        self.entity_combo.grid(row=1, column=1, sticky='w', pady=5)

        # Location
        ttk.Label(frame, text="Location:").grid(row=2, column=0, sticky='w', pady=5)
        self.location_var = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.location_var,
                     values=[loc.value for loc in CellLocation], state='readonly', width=17).grid(
            row=2, column=1, sticky='w', pady=5)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _ok(self):
        entity_text = self.entity_var.get()
        if not entity_text:
            messagebox.showerror("Error", "Please select an RNA entity.")
            return

        try:
            entity_id = int(entity_text.split(']')[0][1:])
        except (ValueError, IndexError):
            messagebox.showerror("Error", "Invalid entity selection.")
            return

        location = self.location_var.get()
        if not location:
            messagebox.showerror("Error", "Please select a location.")
            return

        self.result = {
            'entity_id': entity_id,
            'location': location
        }
        self.destroy()
