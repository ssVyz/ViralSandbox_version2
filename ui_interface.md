# UI Interface

This is the contract between a user interface and the rest of Viral Sandbox. A UI
built against it can replace the Tk UI (`main_menu.py`, `builder.py`,
`play_module.py`, `database_editor.py`) without touching game code.

## Adding a UI

1. Write a module with a `run(api: GameAPI) -> None` function that starts the UI
   and returns when it closes. The launcher creates the `GameAPI` and passes it in.
2. Register it in `UIS` in `main.py` (`"name": "module"`). It is then started with
   `uv run main.py --ui name`. Without `--ui`, `DEFAULT_UI` (tkinter) starts.
3. Add its modules to `UI_MODULES` in `tests/test_game_api.py` so the import
   boundary below is enforced for it.

**The database editor belongs to the Tk UI only.** Other UIs are gameplay only.
They must not import `database_editor` (`tests/test_launcher.py` checks every
registered UI) and must not call `GameAPI.create_content_database()`.

## The boundary

A UI module may import:

- `game_api`: the application layer. Everything the UI does goes through it.
- `models`: the content dataclasses (`Gene`, `Effect`, `ViralEntity`, `Milestone`)
  and enums (`EntityCategory`, `CellLocation`, `EffectType`, `MilestoneType`,
  `OrfTargeting`). These are shared vocabulary.

A UI module must not import `game_state`, `simulation`, `session`, `database` or
`settings`. `tests/test_game_api.py` enforces this for the modules in its
`UI_MODULES` list (the launcher and the Tk modules). `game_api` and the launcher
never import a UI toolkit, so the whole game runs headless.

## Conventions

| Situation | How it is reported |
|---|---|
| The player can't do something (not enough EP, two polymerases, ...) | `(ok, message)` tuple or a result enum. Show the message. |
| The UI called something in the wrong phase | `GameFlowError` is raised. This is a bug in the UI. |
| Offered gene that wasn't offered | `ValueError` is raised. |

- **Model objects** (`Gene`, `Effect`, `ViralEntity`, `Milestone`) returned by the
  API are the game's own objects. Read them, never modify them. The database editor
  is the only exception (see [Content editing](#content-editing)).
- **Everything else** the API returns is an immutable snapshot (frozen dataclass)
  or a copy. Changing it has no effect, and it does not update itself. Ask again
  after a change.
- **IDs and keys.** Genes, effects, entities and milestones are identified by `int`
  IDs. Installed-genome entries are identified by `InstalledItem.key`: the gene ID
  for genes, and the marker name (`"ORF-1"`, `"Term-2"`) for ORFs and terminators.
  Treat keys as opaque. Markers are renumbered by position, so a key can change
  after a move. See `move_item_up`.
- String values for config options, locations and categories are the values listed
  in the constants and enums below. Labels are the UI's choice.

## Phases

`api.phase` is a `GamePhase`. Each call is valid only in certain phases.

```
NO_GAME ──new_game──▶ BUILDING ──start_round──▶ PLAYING ──finish_round──┬─▶ GENE_OFFER  (CONTINUE, genes to offer)
                         ▲                                               ├─▶ BUILDING    (CONTINUE, nothing left to offer)
                         │                                               └─▶ GAME_OVER   (VICTORY or OUT_OF_ROUNDS)
                         └── accept_offered_gene / decline_gene_offer ── GENE_OFFER

any phase ──end_game──▶ NO_GAME
```

| Phase | Meaning | Typical UI |
|---|---|---|
| `NO_GAME` | No game in progress | Main menu |
| `BUILDING` | Genome can be edited, a round can start | Builder |
| `PLAYING` | `api.current_round` is running | Play screen |
| `GENE_OFFER` | `api.gene_offer` is waiting for a choice | Gene offer dialog |
| `GAME_OVER` | Victory or all rounds used; reads still work | Final message, then `end_game()` |

## A UI's main loop

```python
# inside run(api) - the launcher passes in a ready GameAPI
path = api.default_database_path() or ask_user_for_a_file()
if api.new_game(path) is not StartResult.OK: ...        # show why

# BUILDING: edit through api.builder, then resolve readiness
match api.round_readiness():
    case RoundReadiness.NO_GENES: ...                    # tell the player
    case RoundReadiness.CONFIG_NOT_LOCKED: api.builder.lock_config()
    case RoundReadiness.CONFIG_CHANGES_PENDING: ...      # lock_config() or reset_config()

rnd = api.start_round()                                   # PLAYING
while not rnd.is_over and player_keeps_watching():
    result = rnd.step()                                   # one turn, paced by the UI
    draw(result.snapshot)
summary = rnd.summary()                                   # end-of-round screen

match api.finish_round():                                 # ends early if still running
    case RoundOutcome.VICTORY | RoundOutcome.OUT_OF_ROUNDS:
        show_final(api.status()); api.end_game()
    case RoundOutcome.CONTINUE:
        if api.phase is GamePhase.GENE_OFFER:
            offer = api.gene_offer
            api.accept_offered_gene(offer.genes[0].id)    # or api.decline_gene_offer()
```

---

## Reference

### Module level (`game_api`)

| Name | Description |
|---|---|
| `get_version() -> str` | Game version, read from `pyproject.toml` (its only declaration) |
| `WINDOW_MODES` | `("maximized", "windowed")` |
| `HAND_SIZE_MIN`, `HAND_SIZE_MAX` | Allowed starting hand size (1, 20) |
| `NUCLEIC_ACIDS` | `("RNA", "DNA")` |
| `STRANDEDNESS_OPTIONS` | `("single", "double")` |
| `POLARITIES` | `("positive", "negative")` |
| `VIRION_TYPES` | `("Enveloped", "Unenveloped")` |
| `TERMINATOR_CHANCE_MIN`, `TERMINATOR_CHANCE_MAX` | Terminator chance range in % (1, 100) |
| `INTERFERON_MAX` | Cap of the interferon level (100000) |
| `POPULATION_GROUPS` | `("Virion", "RNA", "DNA", "Protein", "Antibodies")`: keys of round history |

### `GameAPI`

Create one per application run: `GameAPI(rng=None)`. Pass a `random.Random` to
make gene offers and simulations reproducible.

**Application**

| Member | Phase | Description |
|---|---|---|
| `version: str` | any | Same as `get_version()` |
| `settings: dict` | any | Copy of the settings (schema below) |
| `save_settings(settings) -> (ok, message)` | any | Validates, then saves. Nothing is saved if invalid. Pass `None` for a value the UI couldn't parse; the message explains. |
| `default_database_path() -> str \| None` | any | The settings' database file, or `None` if it doesn't exist (ask the user for one) |
| `create_content_database() -> GameDatabase` | any | Empty content database for the Tk UI's editor only (see [Content editing](#content-editing)) |

Settings schema:

```python
{"display": {"window_mode": "maximized" | "windowed"},
 "game":    {"starting_hand_size": int,        # HAND_SIZE_MIN..HAND_SIZE_MAX, used by the next new_game
             "default_database": str}}          # file name relative to the app folder
```

**Game lifecycle**

| Member | Phase | Description |
|---|---|---|
| `phase: GamePhase` | any | Current phase |
| `is_game_active: bool` | any | A game exists (any phase except `NO_GAME`) |
| `new_game(database_path) -> StartResult` | any | Start a game. Any game in progress is replaced only if this succeeds. |
| `end_game()` | any | Discard the game, back to `NO_GAME` |
| `status() -> GameStatus` | game | EP, round, genome length |

**Content lookups.** These return shared model objects; read only.

| Member | Phase | Description |
|---|---|---|
| `get_gene(id) -> Gene \| None` | game | |
| `get_effect(id) -> Effect \| None` | game | |
| `get_entity(id) -> ViralEntity \| None` | game | |
| `get_milestone(id) -> Milestone \| None` | game | |
| `gene_type_name(gene_id) -> str` | game | Protein type the gene enables, or `"None"` |

**Rounds and offers**

| Member | Phase | Description |
|---|---|---|
| `builder: Builder` | game | Genome editor of this game |
| `round_readiness() -> RoundReadiness` | game | Whether `start_round()` will be accepted, and what is in the way |
| `start_round() -> Round` | `BUILDING`, readiness `READY` | Starts a round. Moves to `PLAYING`. |
| `current_round: Round \| None` | any | The round in progress, else `None` |
| `finish_round() -> RoundOutcome` | `PLAYING` | Ends the round early if it is still running. The outcome comes from the simulation, not from the UI. |
| `gene_offer: GeneOffer \| None` | any | The pending offer in `GENE_OFFER`, else `None` |
| `accept_offered_gene(gene_id)` | `GENE_OFFER` | Adds the gene to the hand. Moves to `BUILDING`. |
| `decline_gene_offer()` | `GENE_OFFER` | Takes nothing. Moves to `BUILDING`. |

### `Builder` (`api.builder`)

Reads work in any phase. Changes need `BUILDING` and raise `GameFlowError` otherwise,
or if the builder belongs to a game that has ended.

**Reading**

| Member | Returns |
|---|---|
| `hand()` | `list[Gene]`: genes in hand, installable |
| `in_hand(gene_id)` | `bool` |
| `installed()` | `list[InstalledItem]`: the genome in order. Position 0 is the 5' end, where a UTR sits. |
| `is_installed(key)` | `bool` |
| `orf_spans()` | `list[OrfSpan]`: ORFs covering at least one gene, in genome order |
| `config()` | `ConfigView`: pending options and lock state |
| `blueprint()` | `Blueprint`: full report of the virus as it will play |
| `terminator_chance` | `int`, % |
| `terminator_cost` | `int`, EP |
| `orf_cost()` | `int`, EP for the next ORF (first one free) |
| `can_afford(gene_id)` | `bool`: install cost ≤ EP |
| `can_install_gene(gene_id)` | `(ok, reason)`: all install rules (EP, one UTR, one polymerase) |
| `genome_fit(gene_id)` | `GenomeFit`: the gene's genome requirement compared with the locked genome |
| `is_movable(key)` | `bool`: installed and not a UTR (UTRs stay at the 5' end) |
| `can_lock_config()` | `(ok, reason)` |
| `can_add_orf()` | `(ok, reason)` |
| `can_add_terminator()` | `(ok, reason)` |

**Changing** (`BUILDING` only)

| Member | Returns | Notes |
|---|---|---|
| `set_config(nucleic_acid=, strandedness=, polarity=, virion_type=)` | `(ok, message)` | Changes the *pending* config. Omitted fields are unchanged. All-or-nothing on invalid values. |
| `lock_config()` | `(ok, message)` | Locks the pending config in for play. Costs `config().lock_cost`. |
| `reset_config()` | – | Discards pending changes |
| `set_terminator_chance(value)` | `int` | Clamped to range. Returns the value applied. |
| `install_gene(gene_id)` | `(ok, message)` | UTR genes go to the 5' end. Genes with a mismatched genome type install but stay inactive. |
| `remove_item(key)` | `(ok, message)` | Gene goes back to the hand. ORF and terminator removal is free and not refunded. |
| `add_orf()` / `add_terminator()` | `(ok, message)` | Appended after the last item |
| `move_item_up(key)` / `move_item_down(key)` | `(moved, rename_map)` | `rename_map` maps old marker keys to new ones. Update any key you hold. |

Typical install flow for a gene with a genome requirement (`genome_fit`):
`UNLOCKED` → offer to `lock_config()` first, or install anyway (inactive until a
matching genome is locked). `MISMATCH` → warn, install only if confirmed.
`ANY` / `MATCH` → install.

### `Round` (`api.current_round`)

The UI paces the round. Call `step()` once per turn, at whatever speed it likes.
Pausing means not calling it.

| Member | Returns / meaning |
|---|---|
| `number` | Round number (1-based) |
| `turn` | Current turn (0 before the first step) |
| `is_over` | Ended by victory, extinction or `end_early()` |
| `win_threshold` | Virions needed for victory |
| `interferon_max` | = `INTERFERON_MAX` |
| `population_groups` | = `POPULATION_GROUPS` |
| `step() -> TurnResult` | Runs one turn. Does nothing once the round is over (`ended` is then `False`). |
| `end_early()` | Stops the round now. Optional: `finish_round()` does it too. |
| `snapshot() -> RoundSnapshot` | Current state without advancing |
| `history(last=None) -> list[(turn, {group: count})]` | Per-turn population counts by `POPULATION_GROUPS`, optionally the last *n* turns. The count dicts are shared; don't modify them. |
| `log() -> list[str]` | Turn-by-turn log lines (copy) |
| `tracked_milestones() -> list[MilestoneStatus]` | Milestones worth showing: achieved ones and active ones (prerequisite met), by ID |
| `summary() -> RoundSummary` | Result for an end-of-round screen |

### Enums

| Enum | Values |
|---|---|
| `GamePhase` | `NO_GAME`, `BUILDING`, `PLAYING`, `GENE_OFFER`, `GAME_OVER` |
| `StartResult` | `OK`, `LOAD_FAILED`, `NO_GENES` (database has none), `NOT_ENOUGH_GENES` (no hand could be dealt) |
| `RoundOutcome` | `CONTINUE`, `VICTORY`, `OUT_OF_ROUNDS` |
| `RoundReadiness` | `READY`, `NO_GENES` (markers alone don't count), `CONFIG_NOT_LOCKED`, `CONFIG_CHANGES_PENDING` |
| `GenomeFit` | `ANY` (no requirement), `MATCH`, `UNLOCKED` (requirement, nothing locked yet), `MISMATCH` |
| `ItemKind` | `GENE`, `ORF`, `TERMINATOR` (values `"gene"`, `"orf"`, `"terminator"`) |

### Snapshot types

All are frozen dataclasses.

**`GameStatus`**: `phase`, `evolution_points`, `current_round`, `max_rounds`,
`genome_length` (bp of installed genes). After `OUT_OF_ROUNDS`, `current_round` is
`max_rounds + 1`.

**`ConfigView`**

| Field | Meaning |
|---|---|
| `nucleic_acid`, `strandedness`, `polarity`, `virion_type` | Pending (editable) values |
| `genome_string` | Of the pending config, e.g. `"(+)ssRNA"`, `"dsDNA"` |
| `polarity_applies` | `False` for double-stranded genomes (disable the polarity choice) |
| `is_locked` | A config has been locked at least once |
| `locked_genome_string` | Genome string of the locked config. Gene requirements compare against this. |
| `has_pending_changes` | Pending differs from locked |
| `needs_lock` | Lock (or reset) before a round can start |
| `lock_cost` | EP. 0 for the first lock. |

**`InstalledItem`**

| Field | Meaning |
|---|---|
| `kind` | `ItemKind` |
| `key` | Pass back to `Builder` calls |
| `name` | Gene name or marker name |
| `position` | Index in the genome |
| `gene` | `Gene` for genes, else `None` |
| `genome_compatible` | `False`: gene needs a different genome type (or one that is not locked yet) |
| `domain_active` | `False`: domain gene without its partner protein's gene next to it |
| `domain_partner` | Name of the entity a domain gene needs next to it (`""` if not a domain gene) |
| `orf_gene_ids` | ORFs only: gene IDs the ORF translates (up to the next terminator) |
| `is_active` (property) | `genome_compatible and domain_active` |

**`OrfSpan`**: `name`, `gene_ids` (translated when every terminator stops
translation), `readthrough_gene_ids` (reached only by reading through a
terminator; empty at 100 % terminator chance).

**`Blueprint`**: `genome_string`, `virion_type`, `genome_entity_names`, `is_locked`
(all of the *locked* config), `total_length`, `gene_count`, `orf_count`,
`terminator_count`, `orf_spans` (only those with `gene_ids`), `items`
(`InstalledItem`s), `enabled_types` (protein type names, sorted), `gene_effects`
and `global_effects` (the `Effect`s that will actually apply).

**`GeneOffer`**: `genes` (`Gene`s), `completed_round`, `max_rounds`.

**`RoundSnapshot`**

| Field | Meaning |
|---|---|
| `turn` | |
| `total_entities` | Every entity and polyprotein. 0 means extinction. |
| `virion_count` | Virions and viral complexes, compared with `win_threshold` |
| `interferon_level` | 0..`INTERFERON_MAX` |
| `antibodies_active`, `antibodies_stored` | |
| `population` | `PopulationEntry`s, one per entity/location (unsorted) |
| `is_over`, `is_victory`, `is_extinct` | |

**`PopulationEntry`**: `location` (`CellLocation` value), `name`, `category`
(`EntityCategory` value, `""` if unknown; polyproteins report `"Protein"`), `count`,
`is_polyprotein` (polyproteins are always in the cytosol, and their `name` lists
their proteins).

**`TurnResult`**: `snapshot`, `milestones_achieved` (IDs achieved this turn),
`milestones_changed` (the `tracked_milestones()` list changed; redraw it), `ended`
(this turn ended the round).

**`MilestoneStatus`**: `milestone` (`Milestone`), `achieved` (`False` = active).

**`RoundSummary`**: `is_victory`, `is_extinct`, `ended_early`, `turns`,
`milestones_achieved` (`Milestone`s achieved during this round), `evolution_points`
(total after the round).

### Content editing

Tk UI only: other UIs don't offer content editing. The database editor
(`database_editor.py`) works on a content file rather than a game.
`api.create_content_database()` returns a `GameDatabase`. Unlike game objects,
the editor owns this one and its model objects: it builds `ViralEntity`, `Effect`,
`Gene` and `Milestone` instances and hands them to these methods.

| Group | Members |
|---|---|
| File | `new_database()`, `load(path) -> bool`, `save(path=None) -> bool`, `filepath`, `modified` (unsaved changes) |
| Collections (read) | `entities`, `effects`, `genes`, `milestones`: `dict[id, model]` |
| Entities | `add_entity(e) -> id`, `update_entity(e)`, `delete_entity(id) -> bool`, `get_entity(id)`, `get_next_entity_id()`, `is_protected_entity(id)` (the six starter entities can't be deleted), `get_protein_entities()` |
| Effects | `add_effect(e) -> id`, `update_effect(e)`, `delete_effect(id)`, `get_effect(id)`, `get_next_effect_id()`, `get_global_effects()`, `get_genes_with_effect(id)` |
| Genes | `add_gene(g) -> id`, `update_gene(g)`, `delete_gene(id)`, `get_gene(id)`, `get_next_gene_id()`, `get_effects_for_gene(id)`, `get_gene_type_name(gene)` |
| Milestones | `add_milestone(m) -> id`, `update_milestone(m)`, `delete_milestone(id)`, `get_milestone(id)`, `get_next_milestone_id()` |
| Global settings | `get/set_degradation_chance(category, location[, chance])`, `reset_degradation_to_defaults()`, `get/set_interferon_modifier(category[, modifier])`, `reset_interferon_modifiers_to_defaults()`, `get/set_interferon_decay([decay])`, `reset_interferon_decay_to_default()`, `get/set_antibody_per_10_degraded([value])`, `get/set_antibody_manifest_delay([value])`, `reset_antibody_settings_to_defaults()` |

---

## What stays in the UI

The API decides what is allowed and what happened. The UI decides how it looks and
in which order the player sees it:

- Layout, colors, fonts, labels and wording, including how option values are
  labelled (`"positive"` → "Positive (+)").
- Turn pacing (the Tk UI's Normal/Fast/Max speeds) and pausing.
- Selection state, and which confirmations to ask before calling the API (e.g.
  "Add a terminator for 10 EP?").
- How to resolve a non-`READY` `round_readiness()` with the player.
- Drawing conventions such as the 5'/3' orientation of the genome view.
- Parsing user input. Pass the parsed value (or `None`) and let the API validate.
