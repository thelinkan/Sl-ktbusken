# Design Document: Foster and Adoptive Parents

## Overview

This feature makes foster *and* adoptive parentage visible, first-class concepts in Släktbusken
without disturbing biological genealogy as the program's default spine. Foster and adoptive are
handled symmetrically. It builds on infrastructure that already exists:
`ParentChildLink.parentage_type` already accepts `"foster"` and `"adoptive"`, the logical
`RelationshipGraph` already carries `parentage_type` on every edge, the `RelationshipCalculator`
already honours a `blood_priority` policy and already special-cases adoptive, and the `adoption` event
type already exists (as a purely descriptive event). What is missing is: a Fosterhem event type; the
promotion of the Adoption event to a structural source of truth; a sync rule that keeps foster and
adoptive links in agreement with their events; visual differentiation and view controls in the three
diagram renderers; foster-aware kinship classification and terms; report annotation; GEDCOM
round-trip; and research-check awareness.

The organising principle, settled during discussion, is **a placement event is the single source of
truth for its links.** A Fosterhem event is the source of truth for `parentage_type="foster"` links;
the (extended) Adoption event is the source of truth for `parentage_type="adoptive"` links. The user
edits the event; the derived links are reconciled from it by a sync service. This keeps ordering (by
event date) and set membership (the one or two parents named in one event) unambiguous, identically
for both parentage types.

### Key Design Decisions

1. **One sync service reconciles both foster and adoptive links.** `slaktbusken/services/foster_sync.py`
   exposes `sync_parentage_links(project)` that makes the set of `parentage_type in {"foster",
   "adoptive"}` links in the project agree with the set of placement events (`foster_home` →
   `"foster"`, `adoption` → `"adoptive"`). It is idempotent and only ever touches foster and adoptive
   links; biological links and every other parentage type are left exactly as found. Everywhere a
   placement event is created, edited, or deleted — the event editor save path and the GEDCOM import
   path — calls this one function afterwards. The two parentage types share one code path parameterised
   by a small table mapping event type → parentage type → roles, so foster and adoptive cannot drift
   apart in behaviour (Requirements 2.1, 2.2, 2.3, 2.8).

2. **The event ↔ family mapping reuses the existing Family grouping, for both types.** `ParentService`
   already prefers grouping links of the same `parentage_type` into the same `Family` and already
   models one-or-two parents per set via `FamilyPartner` roles. The sync service reuses this: each
   placement event maps to a dedicated derived `Family` for that (child, event) pair, recording the
   originating event id in the existing `Family.event_ids` list. The sync keys off that: a derived
   family whose `event_ids` points at a still-existing placement event is updated in place; one whose
   event is gone is deleted. A derived family's parentage type is fixed by its event's type, so foster
   and adoptive derived families never mix (Requirements 2.2, 2.4).

3. **A project-level per-child override, now three-valued.** The override answers "for *this child*,
   which parent set should the diagram draw", keyed by child id. The design adds
   `ProjectData.connection_overrides: dict[str, str]` from child id to one of `"biological"` /
   `"foster"` / `"adoptive"`. Absent key means no override. It serializes as an omitted/empty dict for
   untouched projects, satisfying backward compatibility (Requirements 5.1, 5.5, 13.1, 13.2).

4. **Show_Level, badge, and fallback are application settings on `DiagramSettings`.** They are view
   preferences, global and not project-specific, so they belong in
   `slaktbusken/persistence/settings_io.py:DiagramSettings` alongside `ancestry_depth` and
   `background_color`, persisting through `app_settings_io.py` with no new persistence machinery. New
   fields: `parentage_show_level: str = "biological"` (one of `"biological"`/`"non_biological"`/
   `"all"`), `parentage_badge: bool = False`, `parentage_fallback: bool = True` (Requirements 7.4,
   4.5, 6.1).

5. **Visual differentiation lives entirely in `ConnectionType` + `ConnectionLineItem`; the views only
   choose the type.** Two new enum members, `FOSTER` and `ADOPTIVE`, each get their own dashed pen and
   distinct colour in `connection_line.py`. The three views already decide which child hangs off which
   parent by reading `parent_child_links`; the only change there is to read the matching link's
   `parentage_type` and pass the corresponding `ConnectionType` into the `ConnectionLineItem` they
   already construct. Styling is defined once (Requirements 3.1–3.5).

6. **A single shared "which parents to draw" resolver, used by all three views.** Given a child, the
   Show_Level, the override map, and the fallback flag, which parent links should be drawn and with
   which style is factored into one pure function
   `slaktbusken/ui/views/parent_display.py:resolve_parent_display(...)` returning the links to draw
   plus their connection types. Each view calls it rather than re-implementing the precedence
   (override > show-level > fallback). This makes Requirement 4.6 (identical across views) hold by
   construction, and it treats foster and adoptive uniformly as "non-biological" except where an
   override or a per-type style distinguishes them.

7. **Foster becomes a fourth relationship classification; adoptive keeps its existing one; both stay
   strictly below blood.** The calculator already filters non-blood edges under `blood_priority`;
   `is_blood_parentage` is already `False` for both foster and adoptive, so both are already
   deprioritised. The only change in `_classify_relationship_type` is to add a foster branch returning
   `"foster"`, placed *after* the all-blood check and alongside the existing adoptive branch, so a
   mixed blood/non-blood path still classifies as blood (Requirements 8.1, 8.2, 9.1, 9.3).
   `kinship_terms.py` gains foster terms for the `"foster"` classification; the adoption terms are
   untouched (Requirements 9.2, 9.4).

8. **GEDCOM pedigree goes on the individual's `FAMC`, which the exporter must start emitting.** In
   GEDCOM 5.5.1 the `PEDI` tag is a subordinate of the child's `FAMC` link, not of the family's
   `CHIL`. The current exporter writes `CHIL` under `FAM` but does not write `FAMC` under `INDI` at
   all. The design adds `FAMC`/`FAMS` emission in `_write_person`, and for each `FAMC` corresponding to
   a foster or adoptive link it adds `2 PEDI foster` or `2 PEDI adopted`. The importer gains a `PEDI`
   reader that sets the created link's `parentage_type` (Requirements 11.1–11.5).

## Data Model Changes

### `slaktbusken/model/event.py`
No structural change. A Fosterhem event is an ordinary `Event` with `type="foster_home"`; an Adoption
event is `type="adoption"`. Both carry participants in a child role (`"fosterbarn"` / `"adopterad"`)
and one or two parents in a parent role (`"fosterförälder"` / `"adoptivförälder"`), plus optional
`date`/`place`.

### `slaktbusken/model/family.py`
No field change to `ParentChildLink` or `Family`. Derived families reuse the existing `event_ids`
list to record their originating placement event.

### `slaktbusken/model/project.py`
Add `connection_overrides: dict[str, str] = field(default_factory=dict)` to `ProjectData`, mapping a
child's person id to `"biological"`, `"foster"`, or `"adoptive"`. Empty for new and pre-feature
projects.

### `slaktbusken/persistence/settings_io.py`
Add to `DiagramSettings`:
- `parentage_show_level: str = "biological"` — one of `"biological"`, `"non_biological"`, `"all"`.
- `parentage_badge: bool = False`.
- `parentage_fallback: bool = True`.

## Event Type Registration (Requirement 1)

Four event types are involved: the new start type `foster_home`, the existing (extended) start type
`adoption`, and the two new end types `foster_home_ended` and `adoption_ended`. Each is registered in
the same places `adoption` already is, treating `adoption` as the template:

| File | What to add |
| --- | --- |
| `ui/editors/event_editor.py` | `"foster_home"`, `"foster_home_ended"`, `"adoption_ended"` in `INDIVIDUAL_EVENT_TYPES`; roles in `EVENT_TYPE_ROLES`: `"foster_home": "fosterbarn"`, `"foster_home_ended": "fosterbarn"`, `"adoption_ended": "adopterad"` (adoption already maps to `"adopterad"`) |
| `ui/swedish_locale.py` | labels `"foster_home": "Fosterhem"`, `"foster_home_ended": "Fosterhem upphörde"`, `"adoption_ended": "Adoption upphörde"` |
| `ui/dialogs/filter_dialog.py` | the three tuples with their Swedish labels |
| `ui/person_detail_panel.py` | the three labels |
| `ui/icons/icon_registry.py` | `"foster_home": "foster_home.svg"` and end-type icons (fall back to generic icon if asset missing) |
| `reports/ansedel.py` | the three labels |
| `reports/kallrapport.py` | the three labels |

The event editor additionally learns the parent role for each placement type so the "add participant"
flow offers `"fosterförälder"` for foster types and `"adoptivförälder"` for adoptive types.
Participant-count validation (one child-role, one or two parent-role) is added for the **start** types
with the exact per-type messages from Requirements 1.4–1.6. Requirement 1.9/13.5: an Adoption start
event with no parent-role participant stays valid and derives nothing.

### End-event pairing and validation (Requirement 2A)
A Placement_End_Event is paired to a Placement_Start_Event by **Parent_Set**: same child, same parent
set, same Derived_Parentage_Type. The derived `Family` that the sync service created for the start
event is the anchor, and the end event's `event_ids` membership on that family is how the pairing is
persisted (the end event id is appended to the same derived family's `event_ids`, alongside the start
event id). This makes "which start does this end close" unambiguous even when a child has several
placements of the same type, and even when the same parents later take the child again (each start has
its own derived family, so each has its own end slot).

The event validator adds, for end events:
- **Orphan check** (Req 2A.4): an end event whose (child, parent set, type) matches no start event's
  Parent_Set yields the exact per-type error message.
- **At-most-one-end** (Req 2A.3): a second end event for a start whose derived family already has an
  end yields an error.
- **End-before-start warning** (Req 2A.6): a warning-level finding, not a hard error, mirroring the
  residence spec's soft chronology findings.

The editor turns the orphan error into a one-click fix (Req 2A.5): creating an end event with no
matching start offers to create a dateless start of the matching type with the same child and parents
in the same step, then pairs the end to it.

### Participant picker: disambiguation and plausibility filtering (Requirement 1B)

Two editor-display refinements make the participant combos usable on a large file. Both live in
`ui/editors/event_editor.py` and both are **display concerns only**: they touch neither the model, the
event validator, nor the Parentage_Sync_Service.

**Birth–death disambiguation.** `_get_person_display` today returns only "Given Surname", so a father
and his same-named son are indistinguishable. It is extended to append the person's life years in
parentheses: "Janne Karlsson (1914–1978)". The years come from the same source the Ansedel report
already uses — the person's birth and death events, looked up by
`_find_event_by_type(person_id, "birth"/"death", data)` — taking the year portion (first four
characters) of the event's `date.value`. A small helper, e.g.
`_life_year_suffix(person_id) -> str`, derives the two years and formats the suffix with the degradation
rules: both years known → `" (1914–1978)"`; birth only → `" (1914–)"`; death only → `" (–1978)"`; neither
known → `""` (no parentheses at all). The separator is the en dash `–` (U+2013), matching the
project's existing date-range formatting (`format_date_range` / `RESIDENCE_INTERVAL_DASH` in
`ui/swedish_locale.py`). Because both `_populate_combos` and the participant table build their labels
through `_get_person_display`, the suffix appears everywhere a person is shown in the editor with no
further change.

**Plausibility filter on the parent-candidate list.** A pure, Qt-free predicate decides whether a
candidate may be a parent of a given child:

```
def is_plausible_parent(candidate_birth_year: int | None,
                        candidate_death_year: int | None,
                        child_birth_year: int | None) -> bool:
    """False only when KNOWN dates prove the candidate cannot be the child's parent.

    Excludes a candidate when its known birth year is not strictly earlier than the
    child's birth year (the parent must be strictly older — any positive gap), or when
    its known death year is earlier than the child's birth year (died before the child
    was born). Unknown/partial dates never exclude: missing data keeps the candidate.
    When the child's birth year is unknown, no judgement is possible, so every candidate
    is plausible.
    """
    if child_birth_year is None:
        return True
    if candidate_birth_year is not None and candidate_birth_year >= child_birth_year:
        return False
    if candidate_death_year is not None and candidate_death_year < child_birth_year:
        return False
    return True
```

Factoring the predicate as a module-level function over three optional ints (not over `Person`/`Event`
objects) keeps it unit-testable without a Qt event loop or a full project; the editor supplies the
years via the same year-derivation helper used for the display suffix.

**Rebuilding the Parent_Role list.** The editor already knows the current event type and the
participants added so far. When the current type is a placement type (`foster_home`,
`foster_home_ended`, `adoption`, `adoption_ended`) and a Child_Role participant is present
(`"fosterbarn"`/`"adopterad"`), the editor resolves the child's birth year and rebuilds the person
combo used for adding a Parent_Role participant to include only candidates for which
`is_plausible_parent(...)` is true. If no child is chosen yet, or the child's birth year is unknown, or
the current type is not a placement type, the combo is populated from the full person list exactly as
today. The Child_Role picker is never filtered. In practice this means the parent combo is repopulated
whenever the event type changes or the Child_Role participant set changes, reusing the existing
`_populate_combos` path with an optional candidate-filter argument.

## Parentage Sync Service (Requirement 2)

New module `slaktbusken/services/foster_sync.py`.

```
# Parameterisation table — the single place foster/adoptive behaviour is defined.
# Only START types derive links. END types annotate an existing placement and
# are deliberately absent from this table so the sync ignores them for link
# existence (Requirement 2.10 / 2A.2).
_PLACEMENT_START = {
    "foster_home": {"parentage": "foster",   "child_role": "fosterbarn", "parent_role": "fosterförälder"},
    "adoption":    {"parentage": "adoptive", "child_role": "adopterad",  "parent_role": "adoptivförälder"},
}
_PLACEMENT_END = {
    "foster_home_ended": "foster_home",   # end type -> the start type it closes
    "adoption_ended":    "adoption",
}

def sync_parentage_links(project: ProjectData) -> None:
    """Make the set of foster/adoptive links agree with placement START events.

    - Collect every start event (type in _PLACEMENT_START) that names a valid child
      and one or two parents in the configured roles.
    - For each such event, ensure a derived Family exists keyed by the event id
      (found via Family.event_ids), containing the parents as partners, the child
      in children, and one ParentChildLink per (parent -> child) with the event's
      parentage type.
    - Delete derived (foster/adoptive) Families whose originating START event no longer exists.
    - END events never create or remove a link; they are paired to the derived family of
      their matching start (their id is appended to that family's event_ids) so the pairing
      persists, but a missing/extra end never changes a link.
    - Never touch biological links or any link whose parentage is neither foster nor adoptive.
    - Idempotent.
    """
```

End events are reconciled alongside: the sync ensures each end event is attached (via `event_ids`) to
the derived family whose start it matches by Parent_Set, and detaches an end event whose start no
longer exists (leaving the orphan end for the validator to flag rather than deleting user data).

Ordering of Parent_Sets (Requirement 2.5) is computed when the diagram or report needs it, by sorting
a child's placement events of a given type on `date.value` with undated events last in project order;
the sort does not mutate stored data.

Backward-compatibility guard (Requirement 13.3): if the project contains foster or adoptive links with
no backing placement event, the first sync does not delete those orphan links. Instead, on load, a
project-format migration back-fills a dateless placement event for each orphan Parent_Set (a Fosterhem
event for orphan foster families, an Adoption event for orphan adoptive families), then
`sync_parentage_links` adopts them, establishing the invariant without data loss.

### Person editor (Requirements 2.6, 2.7)
`ui/editors/person_editor.py` stops offering `foster` and `adoptive` as directly addable parentage
types. Those links appear in the parent table as read-only rows labelled
"fosterförälder (via händelse)" / "adoptivförälder (via händelse)". Choosing to add a foster or
adoptive parent routes the user to create the corresponding placement event (opening the event editor
pre-populated with the child in the right child role).

## Visual Layer (Requirement 3)

### `ui/widgets/connection_line.py`
`ConnectionType` gains `FOSTER` and `ADOPTIVE`. New style constants:
- `_FOSTER_COLOR` (distinct from grey and dark red; e.g. a teal/green), dashed pen (`Qt.DashLine`),
  width ~1.5.
- `_ADOPTIVE_COLOR` (distinct again; e.g. a purple/blue), dashed pen, width ~1.5.

`ConnectionLineItem` gains an optional `badge_text`: when set, it paints the text near the midpoint of
its path. Views pass `badge_text="foster"`/`"adoptiv"` only when `DiagramSettings.parentage_badge` is
true (Requirements 3.6, 3.7).

### `ui/views/parent_display.py` (new, shared resolver)
```
@dataclass
class ParentDisplay:
    links_to_draw: list[ParentChildLink]
    connection_type_for: dict[str, ConnectionType]  # keyed by link identity

def resolve_parent_display(
    child_id, parent_links, show_level, override, fallback_enabled
) -> ParentDisplay: ...
```
Precedence: a Connection_Override for the child wins (Requirement 5.2); otherwise the Show_Level
decides (Requirement 4.2–4.4); the Parentage_Fallback applies only under Show_Level biological when
there are no biological parents (Requirement 6.2). "non_biological" draws both foster and adoptive. An
override naming a parent set the child lacks is ignored (Requirement 5.6). Connection type is chosen
from each drawn link's `parentage_type` (biological → `PARENT_CHILD`, foster → `FOSTER`, adoptive →
`ADOPTIVE`). Under fallback with both foster and adoptive parents present, both are drawn
(Requirement 6.6).

The resolver returns the drawn links **grouped by Parent_Set** (the derived family a link belongs to),
and marks the cardinality of each set, so the view knows whether a set is a one-parent or two-parent
set. This is what lets the view obey the single-parent rule below without re-deriving set membership.

### Single-parent Parent_Sets (Requirement 3.8–3.10)
The existing parent-row code in `family_view.py` always lays out a father slot and a mother slot,
filling an empty slot with a `PlaceholderBoxItem(FATHER/MOTHER)` and always drawing a `PARTNER`
connector between the two slots. That is correct for a **biological** pair with one unknown parent (a
child has two biological parents even when one is unknown — Requirement 3.10 preserves this). It is
wrong for a foster/adoptive Parent_Set that deliberately holds a single parent: there is no implied
second foster/adoptive parent to add.

The design therefore distinguishes, at draw time, a *biological parent pair* from a *derived
Parent_Set*:
- A biological parent pair keeps the current two-slot layout with placeholders for the unknown slot.
- A derived Parent_Set with **one** parent draws exactly one parent box, with **no** partner connector
  and **no** second-parent placeholder; the parent-child connector runs directly from that single
  parent (or its set's junction point) down to the child/sibling bar.
- A derived Parent_Set with **two** parents draws both boxes and the partner connector between them,
  exactly like a biological pair minus the placeholders.

Because all three views route through `resolve_parent_display`, which reports set cardinality, this
single-parent rule is applied uniformly. The view's geometry for a one-parent set positions the single
box over its child junction rather than in a fixed father/mother slot, so the drop line is centred on
the one parent rather than on the midpoint of an absent pair. The same applies when a single-parent set
is shown as a *partner family* parent (a sibling's foster/adoptive child) in STEP 4 of the layout: the
spouse-missing `PlaceholderBoxItem` is suppressed for derived single-parent sets.

### The three views
`family_view.py`, `ancestry_view.py`, `descendants_view.py` each: (a) read `DiagramSettings` for
show-level/badge/fallback, (b) read `ProjectData.connection_overrides` for the child, (c) call
`resolve_parent_display`, (d) construct the `ConnectionLineItem`s with the returned connection type and
optional badge. Existing geometry/positioning is unchanged.

### Context action for the override (Requirement 5.4)
A right-click on a child's parent connector offers "Visa biologiska föräldrar" / "Visa fosterföräldrar"
/ "Visa adoptivföräldrar" / "Återställ till standard", which write/clear
`ProjectData.connection_overrides[child_id]` and trigger a redraw.

## Settings Dialog (Requirement 7)

`ui/dialogs/settings_dialog.py` Diagram tab gains:
- A combo/radio for `parentage_show_level` (Biologiska / Icke-biologiska / Alla).
- A checkbox for `parentage_badge` (default off).
- A checkbox for `parentage_fallback` (default on).

Changing any writes `DiagramSettings` through `app_settings_io.py` and asks the active diagram to
redraw (Requirement 7.5).

## Relationship Calculator & Kinship Terms (Requirements 8, 9)

### `relationship/calculator.py`
`_classify_relationship_type` becomes:
```
if not parentage_types: return "legal"
if all(is_blood_parentage(pt) for pt in parentage_types): return "blood"   # blood priority first
if any(pt == "adoptive" for pt in parentage_types): return "adoption"
if any(pt == "foster" for pt in parentage_types): return "foster"
return "legal"
```
Blood priority at the path-selection level is already provided by `blood_priority` + the
`is_blood_parentage` edge filter; both foster and adoptive are already non-blood, so no change is
needed there.

### `relationship/kinship_terms.py`
`SwedishKinshipTerms.get_term` gains handling for `relationship_type == "foster"`: immediate relations
render as "fosterfar"/"fostermor"/"fosterbarn"; more distant foster relations prefix the base term with
"foster-" (e.g. "fosterbror"). The existing `"adoption"` branch is untouched (Requirement 9.4).

## Reports (Requirement 10)

`reports/ansedel.py`: when listing a child's parents, append the Swedish parentage label from
`swedish_locale.PARENTAGE_TYPE_LABELS` ("Foster", "Adoptiv") for non-biological parents; biological
parents are listed unannotated; foster and adoptive are annotated distinctly from each other
(Requirements 10.1–10.3). The Fosterhem and Adoption events render via their labels (10.4).
`reports/kallrapport.py` picks up the Fosterhem label automatically.

## GEDCOM (Requirement 11)

### Exporter (`gedcom/exporter.py`)
The exporter has three gaps today, found by reading the code: `_write_person` emits no `FAMC`/`FAMS`
at all; the `adoption` event type is absent from `_EVENT_TYPE_TO_TAG`, so Adoption events are silently
dropped on export; and there is no Fosterhem handling. Exporting only a `PEDI` tag would preserve the
*structural* foster/adoptive link but would lose the Placement_Event's **date and place** — the fields
that order and distinguish Parent_Sets in our model. The exporter must therefore write both the
pedigree tag and the event.

**Pedigree on FAMC.** `_write_person` starts emitting the individual's family links:
- For each family where the person is a child: `1 FAMC @Fxx@`, and if the person's `ParentChildLink`
  for that family is foster → `2 PEDI foster`; if adoptive → `2 PEDI adopted`. Biological links emit
  `FAMC` with no `PEDI`.
- For each family where the person is a partner: `1 FAMS @Fxx@`.

**Adoption event.** Add `"adoption": "ADOP"` to `_EVENT_TYPE_TO_TAG` so the existing event-writing loop
in `_write_person` emits `1 ADOP` with `2 DATE`/`2 PLAC` via `_write_event_detail`. `ADOP` is a
first-class GEDCOM 5.5.1 individual event, so this is the faithful mapping (Requirement 11.2a).

**Fosterhem event.** GEDCOM 5.5.1 has no foster event tag, so Fosterhem exports as a custom event
exactly like the existing Flytt export: a new `_write_foster_event` emitting `1 EVEN` / `2 TYPE
Fosterhem` / `2 DATE` / `2 PLAC`, mirroring `_write_flytt_event`. `_write_person` routes
`event.type == "foster_home"` to it, the same way it already routes `"flytt"` (Requirement 11.2b).

**Parent-set linkage.** Both the `ADOP` and the Fosterhem `EVEN` structure get a subordinate `3 FAMC
@Fxx@` pointing at the derived family for the Parent_Set the event produced, so a re-import can rebuild
*which* parents the placement names rather than only that the child was fostered/adopted
(Requirement 11.2c). One structure is emitted per Placement_Start_Event, so multiple Parent_Sets of the
same type round-trip as multiple structures with their ordering intact (Requirement 11.2d).

**End date on the paired structure.** GEDCOM has no native "fostering ended"/"adoption ended" slot. The
end date of a Placement_End_Event therefore rides on the *same* `ADOP`/`EVEN` structure as its paired
start rather than as a separate structure (Requirement 11.2e). The faithful encoding is a GEDCOM date
*period* on the structure's `DATE` line when both start and end dates are known (`FROM <start> TO
<end>`), degrading to `FROM <start>` or `TO <end>` when only one is known; when the date cannot be
expressed that way it is written as a labelled `NOTE` ("Avslutades: <end>") and the structure loss is
recorded in the export log, exactly as `_write_flytt_event` logs the `from_place` note. On import, a
`DATE` period's upper bound (or the labelled note) reconstructs the paired Placement_End_Event with the
same child and parents as the start (Requirement 11.10).

On re-import these structures are what the back-fill helper prefers as the source of date/place and
parent linkage (Requirements 11.7, 11.7a), closing the round-trip: a Fosterhem/Adoption event exported
with its date, place, and parents comes back as the same event rather than as a dateless stub.

### Importer (`gedcom/importer.py`)
Today the importer reads only family-level `CHIL` cross-references and hardcodes every link to
`biological`; it does not read the GEDCOM 5.5.1 `PEDI` tag, which lives under the *individual's*
`FAMC`. The importer therefore gains FAMC/PEDI reading: for each child, map the pedigree value
`foster` → `parentage_type="foster"`, `adopted` → `"adoptive"`, anything else/absent → `"biological"`.

**Import ordering is critical.** A bare imported foster/adoptive link has no backing placement event,
and `sync_parentage_links` deletes unbacked foster/adoptive links (Design Decision 1). Running the sync
immediately after import would therefore silently drop every imported `PEDI foster`/`PEDI adopted`
relationship. The importer must instead:

1. Create the typed links while reading FAMC/PEDI (foster/adoptive/biological).
2. **Before** reconciling, back-fill a placement event for each imported foster/adoptive link that is
   not already backed by an imported placement event: a Fosterhem event for foster links, an Adoption
   event for adoptive links, naming the child in the child role and the parent(s) in the parent role.
   Foster/adoptive parents sharing the same GEDCOM family for the same child are grouped into one
   back-filled event so they form a single Parent_Set (Requirement 11.8). Any date/place available from
   the GEDCOM context — notably an `ADOP` event's `DATE`/`PLAC`, which the importer already maps to a
   descriptive adoption event — is carried onto the back-filled event; otherwise the event is dateless
   (Requirement 11.7).
3. Run `sync_parentage_links`, which now finds every imported foster/adoptive link backed by an event
   and so preserves it, giving the event precedence where both describe the same (child, parent) pair
   (Requirements 11.6, 11.9).

This mirrors the on-load migration (Requirement 13.3): in both paths, orphan foster/adoptive links are
rescued by back-filling the event that the new model requires as their source of truth, so no
relationship is lost. The two paths share the same back-fill helper to avoid divergence. Note the
interaction with the existing `ADOP` → descriptive-adoption-event mapping: when a GEDCOM record has
both a `PEDI adopted` link and an `ADOP` event, the importer reuses that `ADOP`-derived Adoption event
as the backing event (adding the adoptive-parent participants to it) rather than creating a second
Adoption event for the same adoption.

## Person Checks & Detail Panel (Requirement 12)

`services/person_check_engine.py` splits its `parents_of` derivation so checks distinguish foster and
adoptive from biological parents; "saknar föräldrar"-type findings consider a person with only
non-biological parents as having parents (12.1, 12.2); age-gap/chronology checks skip foster links, and
skip adoptive links where the same check would be meaningless (12.4).
`ui/person_detail_panel.py` labels foster and adoptive parents distinctly in "Föräldrar och syskon"
(12.3).

## Persistence & Migration (Requirement 13)

- `ProjectData.connection_overrides` serializes as a dict, omitted/empty when unused (13.2).
- A project-format migration establishes the source-of-truth invariant for pre-feature projects that
  already contain foster or adoptive links: for each orphan derived family with no backing placement
  event, create the matching dateless placement event (Fosterhem for foster, Adoption for adoptive),
  then let `sync_parentage_links` adopt it (13.3). No foster or adoptive data is deleted.
- Pre-feature descriptive Adoption events are preserved; an Adoption event naming no adoptive-parent
  participant derives nothing and is not altered (13.5).
- `_VALID_PARENTAGE_TYPES` already contains `"foster"`/`"adoptive"`; unchanged (13.4).

## Correctness Properties

1. **Sync idempotence.** `sync_parentage_links` applied twice equals applied once (Req 2.8).
2. **Foster/adoptive-only reconciliation.** `sync_parentage_links` never changes any biological link or
   any link whose parentage is neither foster nor adoptive (Req 2.2).
3. **Event ⇒ link coverage, both types.** After sync, every placement event has exactly the links of
   its type that it implies, and no foster/adoptive link lacks a backing event — except
   migration-adopted ones, which gain an event (Reqs 2.1, 2.2, 13.3).
4. **Set cap, project no-cap.** A child may have >2 foster parents and >2 adoptive parents across
   events, but no single Parent_Set exceeds 2 (Req 2.9).
5. **Display precedence and set cardinality.** `resolve_parent_display`: override wins over show-level
   wins over fallback; an override for a missing set is ignored; non_biological draws both foster and
   adoptive; each drawn set reports its cardinality (one or two parents) so the view suppresses the
   partner connector and second-parent placeholder for a one-parent derived set (Reqs 3.8–3.10, 4, 5,
   6).
6. **Blood priority & classification.** When any all-blood path exists, no foster/adoptive path is
   returned; a mixed path classifies as blood; a pure foster path classifies as "foster"; a pure
   adoptive path classifies as "adoption" (Reqs 8, 9.1, 9.3).
7. **GEDCOM round-trip with no loss.** Export then import of a foster/adoptive/biological link
   preserves its `parentage_type`; the Placement_Event's date and place survive via the exported
   `ADOP`/`EVEN TYPE Fosterhem` structure and its `FAMC` parent linkage; every imported foster/adoptive
   link is backed by a back-filled or reused placement event before the post-import sync, so the sync
   never deletes it; parents sharing a GEDCOM family form one Parent_Set; multiple Parent_Sets of a
   type round-trip as multiple ordered structures (Req 11).
8. **Backward compatibility.** Loading a pre-feature project with foster/adoptive links loses none of
   them; descriptive adoption events are preserved; `connection_overrides` defaults empty (Reqs 13.1,
   13.3, 13.5).
9. **End events annotate, never mutate links.** Creating, editing, or deleting a Placement_End_Event
   leaves every Derived_Link unchanged; an end event pairs to exactly one start by Parent_Set; a start
   has at most one end; an orphan end is flagged, not silently dropped; end-before-start is a warning
   (Req 2A).

## Out of Scope / Follow-ups

- **Barnhemsplacering (institutional / children's-home stays) is modelled with the existing Boende
  (Residence_Fact) entity, not by this feature.** An institution is a place, not a parent, and a stay
  is an interval, not a point, so it does not fit the Parent_Set model. A children's-home stay is a
  Boende at the institution's place with its own interval; the person's timeline interleaves Placements
  (foster/adoptive start+end) and Boende stays in chronological order, so a sequence such as "foster
  family 1 → barnhem → foster family 2" reads correctly without any new entity here.
- Directly editing foster or adoptive links in the person editor (deliberately read-only this
  iteration; revisit if the event-only flow proves awkward — Settled Decision 12).
- Foster/adoptive-specific layout changes for many simultaneous Parent_Sets beyond what the existing
  stacking geometry already supports; the override + show-level controls are the mechanism for managing
  visual density.
