# Requirements Document

## Introduction

Släktbusken already records the *nature* of a parent-child relationship through the
`parentage_type` field on `ParentChildLink` ("biological", "adoptive", "foster", "step", "donation",
"legal", "unknown_donor"). Foster and adoptive parentage are therefore already valid structural
values, but they are invisible in practice: there is no händelsetyp for fostering, the existing
"Adoption" event is purely descriptive and has no structural effect, the family diagram draws a foster
or adoptive edge exactly like a biological one, the user cannot choose which parent set a view shows,
the kinship calculator folds foster into the generic "legal" bucket, and the Ansedel report does not
say which parent is a foster or adoptive parent.

This feature makes foster *and* adoptive parentage first-class, visible concepts while leaving
biological genealogy as the default spine of the program. Foster and adoptive are handled
symmetrically throughout.

The central design choice, settled during discussion, is that **a parentage event is the single
source of truth for its placements.** A new "Fosterhem" event names the foster child and one or two
foster parents; the existing "Adoption" event is extended to name the adoptee and one or two adoptive
parents the same way. The structural `parentage_type="foster"` and `parentage_type="adoptive"` links
in the family model are *derived and kept in sync* from these events rather than being added directly
in the person editor. An event's date establishes the ordering of placements, and the grouping of
parents within one event is what distinguishes one *set* of parents from another. A child may have any
number of such events, hence any number of distinct non-biological parent sets.

Visualization gains a dashed, differently coloured connector for foster and adoptive edges (each in
its own colour), plus an optional text badge toggled from the Diagram tab of Inställningar. The three
diagram views (Familj, Anor, Ättlingar) gain a global show-level — biological, non-biological, or all
— and individual connections may carry a stored override that wins over the global show-level. When
the show-level is "biological" but a person has no known biological parents, a settable fallback shows
their foster/adoptive parents instead of empty placeholders.

Blood genealogy keeps priority everywhere it matters: the kinship calculator prefers blood paths over
foster and adoptive paths, and only falls back to a non-blood path when no blood path exists. Foster
and adoptive relationships receive distinct Swedish kinship terms so a foster or adoptive relative is
never mistaken for a blood relative.

Foster and adoptive parentage round-trip through GEDCOM using the standard `PEDI foster` and
`PEDI adopted` pedigree tags.

## Glossary

- **Parentage_Type**: The existing `ParentChildLink.parentage_type` string. The values this feature
  concerns are `"biological"`, `"foster"`, and `"adoptive"`. The authoritative valid set lives in
  `slaktbusken/model/validators.py` (`_VALID_PARENTAGE_TYPES`).
- **Derived_Parentage_Type**: Either `"foster"` or `"adoptive"` — the two parentage types this
  feature derives from events. Used when a requirement applies identically to both.
- **Placement_Event**: A Placement_Start_Event or a Placement_End_Event. The umbrella term for the
  events of a placement. Each Placement_Event has one Derived_Parentage_Type: Fosterhem → `"foster"`,
  Adoption → `"adoptive"`.
- **Placement_Start_Event**: A Fosterhem_Event or an Adoption_Event (as defined below). It is the
  single source of truth for a set of Derived_Links and its Parent_Set. "Start" distinguishes it from
  the paired end event; where this document says "Placement_Event" without qualification in the
  link-derivation context, it means the start event.
- **Placement_End_Event**: A Fosterhem_Ended_Event or an Adoption_Ended_Event. It records when a
  placement ended. It never creates or removes a Derived_Link; it only annotates an existing placement
  with a close date. Each Placement_End_Event is paired to exactly one Placement_Start_Event through
  that start event's Parent_Set.
- **Placement**: One Placement_Start_Event together with its optional paired Placement_End_Event, for
  one child and one Parent_Set over time. A child may have many Placements, ordered by start date.
- **Derived_Link**: A `ParentChildLink` whose `parentage_type` is a Derived_Parentage_Type. This
  feature treats Derived_Links as *derived state*: they are created, updated, and removed only as a
  consequence of Placement_Events, never edited directly in the person editor.
- **Fosterhem_Event**: An `Event` of the new individual händelsetyp `foster_home`, displayed in
  Swedish as "Fosterhem". It names one foster child and one or two foster parents as participants and
  may carry a `date` and `place`. It is the single source of truth for `"foster"` links.
- **Adoption_Event**: An `Event` of the existing individual händelsetyp `adoption`, displayed in
  Swedish as "Adoption". Extended by this feature to name one adoptee and one or two adoptive parents
  as participants and to be the single source of truth for `"adoptive"` links.
- **Fosterhem_Ended_Event**: An `Event` of the new individual händelsetyp `foster_home_ended`,
  displayed in Swedish as "Fosterhem upphörde". It records when a foster placement ended and is paired
  to a Fosterhem_Event. It names the same child and foster parents as its start event (symmetric
  participants) and may carry a `date` and `place`.
- **Adoption_Ended_Event**: An `Event` of the new individual händelsetyp `adoption_ended`, displayed
  in Swedish as "Adoption upphörde". It records when an adoptive placement ended and is paired to an
  Adoption_Event, with symmetric participants and an optional `date`/`place`.
- **Parent_Set**: The one or two non-biological parents named in a single Placement_Event, taken
  together. A Parent_Set is complete whether it holds one parent or two; a one-parent set is not a
  half-filled two-parent set. Two Placement_Events of the same Derived_Parentage_Type for the same
  child express two distinct Parent_Sets, ordered by their event dates.
- **Child_Role**: The participant role identifying the placed child within a Placement_Event. Its
  value is `"fosterbarn"` for a Fosterhem_Event and `"adopterad"` for an Adoption_Event (the latter is
  already the default role for the adoption type).
- **Parent_Role**: The participant role identifying a non-biological parent within a Placement_Event.
  Its value is `"fosterförälder"` for a Fosterhem_Event and `"adoptivförälder"` for an Adoption_Event.
- **Parentage_Sync_Service**: The service that reads all Placement_Events and brings the set of
  Derived_Links in the Project into agreement with them, without disturbing biological links or any
  other link whose parentage is neither `"foster"` nor `"adoptive"`.
- **Show_Level**: A per-diagram view setting with the three values biological, non-biological, and
  all, controlling which parentage types the diagram draws. Internal values `"biological"`,
  `"non_biological"`, `"all"`. It is a view/application setting, not stored per project.
- **Connection_Override**: A stored, per-connection instruction that overrides the Show_Level for one
  specific child, naming which parent set that child's connection should display regardless of the
  global Show_Level. It travels with the project.
- **Parentage_Fallback**: The settable behaviour whereby, when the Show_Level is biological and a
  person has no biological parents but does have foster or adoptive parents, the diagram shows the
  non-biological parents (styled per type) rather than empty parent placeholders.
- **Connection_Type**: The visual edge classification in
  `slaktbusken/ui/widgets/connection_line.py` (`ConnectionType` enum), today limited to
  `PARENT_CHILD` and `PARTNER`.
- **Diagram_Views**: The three renderers that draw person boxes and connectors:
  `slaktbusken/ui/views/family_view.py` (Familj), `slaktbusken/ui/views/ancestry_view.py` (Anor),
  and `slaktbusken/ui/views/descendants_view.py` (Ättlingar).
- **Relationship_Graph**: The logical adjacency graph built by
  `slaktbusken/relationship/graph_builder.py`, whose edges carry `parentage_type`.
- **Relationship_Calculator**: `slaktbusken/relationship/calculator.py`, which finds and classifies
  kinship paths and already honours a `blood_priority` policy.
- **Kinship_Terms**: `slaktbusken/relationship/kinship_terms.py`, which maps a classified
  relationship to a Swedish term and today understands `relationship_type` values `"blood"`,
  `"legal"`, and `"adoption"`.
- **Person_Check_Engine**: `slaktbusken/services/person_check_engine.py`, which derives per-person
  parent lists and runs research checks over them.
- **Ansedel_Report**: `slaktbusken/reports/ansedel.py`, the standard family-sheet report.
- **Källrapport_Report**: `slaktbusken/reports/kallrapport.py`, the source report.
- **GEDCOM_Importer** / **GEDCOM_Exporter**: `slaktbusken/gedcom/importer.py` and
  `slaktbusken/gedcom/exporter.py`.
- **Settings_Dialog**: `slaktbusken/ui/dialogs/settings_dialog.py` and its Diagram tab.
- **App_Settings**: The persisted application settings handled by
  `slaktbusken/persistence/app_settings_io.py`.
- **Project**: The root container `ProjectData`.

## Requirements

### Requirement 1: Fosterhem händelsetyp and extended Adoption händelsetyp

**User Story:** As a genealogist, I want a dedicated "Fosterhem" event type and an "Adoption" event that names the adoptive parents, so that I can record who fostered or adopted a child and when, in one place.

#### Acceptance Criteria

1. THE application SHALL define individual händelsetyper with internal keys `foster_home` ("Fosterhem"), `foster_home_ended` ("Fosterhem upphörde"), and `adoption_ended` ("Adoption upphörde"), registered in every place the existing `adoption` type is registered: the event-type lists and default-role map in `slaktbusken/ui/editors/event_editor.py`, the label maps in `slaktbusken/ui/swedish_locale.py`, the filter list in `slaktbusken/ui/dialogs/filter_dialog.py`, the detail-panel label map in `slaktbusken/ui/person_detail_panel.py`, the icon map in `slaktbusken/ui/icons/icon_registry.py`, and the report label maps in `slaktbusken/reports/ansedel.py` and `slaktbusken/reports/kallrapport.py`.
2. THE event editor SHALL offer, for a Fosterhem_Event, the Child_Role `"fosterbarn"` for the fostered child and the Parent_Role `"fosterförälder"` for each foster parent; and for an Adoption_Event, the Child_Role `"adopterad"` for the adoptee and the Parent_Role `"adoptivförälder"` for each adoptive parent.
3. A Placement_Start_Event SHALL accept exactly one participant in its Child_Role and one or two participants in its Parent_Role.
4. WHEN a Placement_Start_Event names zero participants in its Child_Role, THE event validator SHALL return exactly one occurrence of the error message "Ett fosterhem måste ange ett fosterbarn." for a Fosterhem_Event and "En adoption måste ange ett adopterat barn." for an Adoption_Event.
5. WHEN a Placement_Start_Event names more than one participant in its Child_Role, THE event validator SHALL return exactly one occurrence of the error message "Ett fosterhem kan bara ange ett fosterbarn." for a Fosterhem_Event and "En adoption kan bara ange ett adopterat barn." for an Adoption_Event.
6. WHEN a Placement_Start_Event names more than two participants in its Parent_Role, THE event validator SHALL return exactly one occurrence of the error message "Ett fosterhem kan ange högst två fosterföräldrar." for a Fosterhem_Event and "En adoption kan ange högst två adoptivföräldrar." for an Adoption_Event.
7. A Placement_Event SHALL accept an optional `date` and an optional `place` using the existing `Event` fields, and SHALL return zero errors when either or both are absent.
8. THE Fosterhem_Event SHALL be assigned an icon by the icon map, falling back to the existing generic event icon when no dedicated `foster_home.svg` asset is present; THE Adoption_Event SHALL keep its existing icon; THE end-event types SHALL each be assigned an icon, falling back to the generic event icon when no dedicated asset is present.
9. THE extension of the Adoption_Event SHALL be backward compatible: an existing Adoption_Event that names no participant in the Parent_Role SHALL remain valid and SHALL simply derive no adoptive links.
10. A Placement_End_Event SHALL name the same child and the same parents as its paired Placement_Start_Event (symmetric participants), using the same Child_Role and Parent_Role as its type.

### Requirement 1B: Participant picker disambiguation and plausibility filtering

**User Story:** As a genealogist with many same-named people, I want the event editor's participant picker to disambiguate people by their birth and death years and to hide people who cannot plausibly be a parent of the chosen child, so that I can pick the right person from a large list without confusing a father and his same-named son.

#### Acceptance Criteria

1. WHEN the event editor populates a participant combo, THE event editor SHALL display each person as the person's name followed by the person's birth and death years in parentheses, with an en dash (`–`, U+2013) separating the two years, for example "Janne Karlsson (1914–1978)".
2. WHERE a person has a known birth year and no known death year, THE event editor SHALL display that person as the name followed by "(<birth year>–)", for example "Janne Karlsson (1914–)".
3. WHERE a person has a known death year and no known birth year, THE event editor SHALL display that person as the name followed by "(–<death year>)", for example "Janne Karlsson (–1978)".
4. WHERE a person has neither a known birth year nor a known death year, THE event editor SHALL display that person as the name alone with no parentheses.
5. THE event editor SHALL derive a person's birth year and death year from the year portion of the date value of the person's birth event and death event respectively, using the same event-lookup approach the Ansedel_Report uses (`_find_event_by_type(person_id, "birth"/"death", data)`).
6. WHILE the current event type is a Placement_Event type (`foster_home`, `foster_home_ended`, `adoption`, or `adoption_ended`) AND a participant occupies the Child_Role AND the Child_Role participant has a known birth year, THE event editor SHALL exclude from the Parent_Role candidate list every person whose known birth year is not strictly earlier than the Child_Role participant's birth year.
7. WHILE the current event type is a Placement_Event type AND a participant occupies the Child_Role AND the Child_Role participant has a known birth year, THE event editor SHALL exclude from the Parent_Role candidate list every person whose known death year is earlier than the Child_Role participant's birth year.
8. THE event editor SHALL retain in the Parent_Role candidate list every person whose known dates do not prove implausibility, including every person whose birth year, death year, or both are unknown.
9. IF the Child_Role has no participant OR the Child_Role participant has no known birth year, THEN THE event editor SHALL apply no plausibility exclusion and SHALL offer the full person list as Parent_Role candidates.
10. THE plausibility exclusion of criteria 6 and 7 SHALL apply only to the Parent_Role candidate list of Placement_Event types; THE Child_Role candidate list and the participant picker of every non-Placement_Event type SHALL continue to offer the full person list.

### Requirement 2: Placement events are the single source of truth for derived links

**User Story:** As a genealogist, I want the foster and adoptive relationships in the family model to come from my Fosterhem and Adoption events, so that there is one place to edit a placement and the tree stays consistent with it.

#### Acceptance Criteria

1. THE Parentage_Sync_Service SHALL, for every Placement_Event, ensure a Derived_Link of the event's Derived_Parentage_Type exists from each non-biological parent in the event to the child in the event.
2. THE Parentage_Sync_Service SHALL remove every Derived_Link that is not backed by any Placement_Event, and SHALL leave every biological link and every link whose parentage is neither `"foster"` nor `"adoptive"` unchanged.
3. WHEN a Placement_Event is created, edited, or deleted, THE application SHALL run the Parentage_Sync_Service so that the Derived_Links agree with the current set of Placement_Events.
4. THE Parentage_Sync_Service SHALL place the Derived_Links from one Placement_Event so that that event's Parent_Set stays distinguishable from the Parent_Set of any other Placement_Event for the same child.
5. WHEN two or more Placement_Events of the same Derived_Parentage_Type name the same child, THE application SHALL order their Parent_Sets by the events' `date` values, placing events without a date after all dated events while preserving their existing project order.
6. THE person editor SHALL present event-derived foster and adoptive links as read-only entries that cannot be added, retyped, or removed from the parent table, and SHALL direct the user to edit the corresponding Placement_Event instead.
7. WHEN the user attempts to add a parent of type foster or adoptive directly in the person editor, THE person editor SHALL decline the direct edit and SHALL offer to create the corresponding Placement_Event instead.
8. THE Parentage_Sync_Service SHALL be idempotent: running it twice in succession with no intervening change SHALL leave the Project's Derived_Links identical to running it once.
9. THE max-parents validation SHALL permit a child to have more than two foster parents and more than two adoptive parents in total across the Project, SHALL cap each individual Parent_Set at two parents, and SHALL continue to cap biological parents at one father-role and one mother-role.
10. THE Parentage_Sync_Service and the "backed by a Placement_Event" test in criteria 2.1 and 2.2 SHALL consider only Placement_Start_Events; a Placement_End_Event SHALL never, on its own, cause a Derived_Link to be created or removed.

### Requirement 2A: Placement end events

**User Story:** As a genealogist, I want to record when a foster or adoptive placement ended, so that a person's history shows each placement's span while the relationship itself remains a permanent fact.

#### Acceptance Criteria

1. A Placement_End_Event SHALL record the end of exactly one Placement, and SHALL be paired to its Placement_Start_Event through that start event's Parent_Set (the same child and the same parents).
2. WHEN a placement ends, THE application SHALL retain the Derived_Links produced by the paired Placement_Start_Event; ending a placement SHALL NOT remove any Derived_Link.
3. A Placement_Start_Event SHALL have at most one paired Placement_End_Event.
4. WHEN a Placement_End_Event has no Placement_Start_Event with a matching Parent_Set for the same child, THE event validator SHALL return exactly one occurrence of the error message "Fosterhem upphörde saknar en fosterhemsplacering att avsluta." for a Fosterhem_Ended_Event and "Adoption upphörde saknar en adoption att avsluta." for an Adoption_Ended_Event.
5. WHEN the user creates a Placement_End_Event for which no matching Placement_Start_Event exists, THE event editor SHALL offer to create a dateless Placement_Start_Event of the matching type with the same child and parents in the same step, rather than only rejecting the end event.
6. WHEN a Placement_End_Event has a `date` that is earlier than the `date` of its paired Placement_Start_Event, THE event validation SHALL return a warning-level finding (not a hard error) noting the end precedes the start.
7. WHEN more than one Placement_Start_Event of the same type exists for the same child, THE pairing of a Placement_End_Event SHALL resolve to the Parent_Set it names, so that the correct placement among several is the one marked ended.
8. THE person's timeline and event list SHALL show each Placement as its start and, when present, its end, so that successive placements (and any intervening institutional stay recorded as a Boende) read in chronological order.

### Requirement 3: Visual differentiation of foster and adoptive connections

**User Story:** As a genealogist, I want foster and adoptive connections to look different in the diagram, so that I can tell at a glance which parents are foster or adoptive parents.

#### Acceptance Criteria

1. THE Connection_Type enumeration SHALL gain members for a foster parent-child connection and an adoptive parent-child connection in addition to the existing `PARENT_CHILD` and `PARTNER`.
2. THE connection line SHALL render a foster connection as a dashed line in a colour distinct from both the biological parent-child colour and the partner colour.
3. THE connection line SHALL render an adoptive connection as a dashed line in a colour distinct from the biological, partner, and foster colours.
4. WHEN a child-parent connection has `parentage_type` biological, THE Diagram_Views SHALL render it with the existing solid `PARENT_CHILD` style unchanged.
5. THE Diagram_Views `family_view.py`, `ancestry_view.py`, and `descendants_view.py` SHALL each select the connection style from the `parentage_type` of the `ParentChildLink` that justifies the drawn edge.
6. WHEN the text badge setting of Requirement 7 is enabled, THE connection line for a foster connection SHALL display the badge text "foster" and the connection line for an adoptive connection SHALL display the badge text "adoptiv", positioned on or beside the connector.
7. WHEN the text badge setting is disabled, THE connection line SHALL display no badge text for any connection type.
8. WHEN a Parent_Set drawn in the diagram holds exactly one parent, THE Diagram_Views SHALL render that single parent as a complete parent, SHALL NOT draw an "add the other parent" placeholder for that set, and SHALL NOT draw a partner connector to an absent second parent.
9. WHEN a Parent_Set drawn in the diagram holds two parents, THE Diagram_Views SHALL render both parents and the partner connector between them as they do for a two-person biological parent pair.
10. THE single-parent rendering of Requirement 3.8 SHALL apply only to foster and adoptive Parent_Sets; a biological parent pair with one unknown parent SHALL continue to show its existing father/mother placeholder for the unknown parent.

### Requirement 4: Show-level for the diagram views

**User Story:** As a genealogist, I want to choose whether a diagram shows biological parents, foster/adoptive parents, or all of them, so that I can read the tree the way I need for a given task.

#### Acceptance Criteria

1. THE Diagram_Views SHALL support a Show_Level with the three values biological, non-biological, and all.
2. WHEN the Show_Level is biological, THE Diagram_Views SHALL draw parent-child connections whose `parentage_type` is biological and SHALL omit foster and adoptive connections, subject to the Parentage_Fallback of Requirement 6 and the Connection_Override of Requirement 5.
3. WHEN the Show_Level is non-biological, THE Diagram_Views SHALL draw foster and adoptive connections and SHALL omit biological connections, subject to the Connection_Override of Requirement 5.
4. WHEN the Show_Level is all, THE Diagram_Views SHALL draw biological, foster, and adoptive connections, each in its own style per Requirement 3.
5. THE Show_Level SHALL default to biological for a user who has never changed it.
6. THE Show_Level SHALL apply identically to the Familj, Anor, and Ättlingar views so that switching views does not change which parent set is shown.
7. WHEN the Show_Level changes, THE active diagram SHALL redraw to reflect the new level without requiring the user to reselect the active person.

### Requirement 5: Per-connection override

**User Story:** As a genealogist, I want to override, for one particular child, which parent set the diagram shows, so that an individual case can differ from the global setting without changing it for everyone.

#### Acceptance Criteria

1. THE Project SHALL be able to store a Connection_Override for a child that names which parent set — biological, foster, or adoptive — that child's parent connection should display.
2. WHEN a child has a Connection_Override, THE Diagram_Views SHALL honour the override for that child's parent connection regardless of the current Show_Level.
3. WHEN a child has no Connection_Override, THE Diagram_Views SHALL fall back to the current Show_Level for that child's parent connection.
4. THE Diagram_Views SHALL offer a context action on a child's parent connection to set the Connection_Override to biological, to foster, to adoptive, or to cleared.
5. THE Connection_Override SHALL persist with the Project so that reopening the project preserves each override.
6. WHEN a Connection_Override names a parent set that the child does not have, THE Diagram_Views SHALL ignore that override and fall back to the Show_Level, and SHALL not raise an error.

### Requirement 6: Fallback when no biological parents are known

**User Story:** As a genealogist viewing a biological tree, I want to still see a person's foster or adoptive parents when no biological parents are recorded, so that I am not left with an empty branch where the only known parents are non-biological.

#### Acceptance Criteria

1. THE application SHALL provide a Parentage_Fallback setting that is enabled by default.
2. WHEN the Show_Level is biological AND a person has no biological parents AND the person has one or more foster or adoptive parents AND the Parentage_Fallback setting is enabled AND the person has no Connection_Override, THE Diagram_Views SHALL draw that person's non-biological parents, styled per type per Requirement 3.
3. WHEN the Parentage_Fallback setting is disabled under the same conditions, THE Diagram_Views SHALL draw the empty biological parent placeholders instead of the non-biological parents.
4. WHEN a person has at least one biological parent, THE Parentage_Fallback SHALL have no effect for that person.
5. THE Parentage_Fallback SHALL never cause biological connections to be hidden.
6. WHEN a person has both foster and adoptive parents and no biological parents under an active fallback, THE Diagram_Views SHALL draw both the foster and the adoptive parents, each in its own style.

### Requirement 7: Diagram settings in Inställningar

**User Story:** As a genealogist, I want the foster- and adoption-related diagram options in the Diagram tab of Inställningar, so that I can configure them where the other diagram options live.

#### Acceptance Criteria

1. THE Settings_Dialog Diagram tab SHALL provide a control for the Show_Level with the three values biological, non-biological, and all.
2. THE Settings_Dialog Diagram tab SHALL provide a toggle for the text badge of Requirement 3, defaulting to disabled.
3. THE Settings_Dialog Diagram tab SHALL provide a toggle for the Parentage_Fallback of Requirement 6, defaulting to enabled.
4. THE App_Settings SHALL persist the Show_Level, the badge toggle, and the Parentage_Fallback toggle across application restarts.
5. WHEN a setting on the Diagram tab changes, THE active diagram SHALL redraw to reflect it.

### Requirement 8: Blood priority in the relationship calculator

**User Story:** As a genealogist, I want kinship paths that go through blood relatives to take priority over paths that go through foster or adoptive parents, so that the relationship calculator reports the biological relationship whenever one exists.

#### Acceptance Criteria

1. THE Relationship_Calculator SHALL treat a foster or adoptive link edge as a non-blood edge for the purpose of its `blood_priority` policy.
2. WHEN at least one blood path exists between two people, THE Relationship_Calculator SHALL return only blood paths and SHALL not return any path that traverses a foster or adoptive link.
3. WHEN no blood path exists between two people but a foster or adoptive path exists, THE Relationship_Calculator SHALL return the closest non-blood path.
4. WHEN a foster path and an adoptive path of equal distance are the only non-blood paths, THE Relationship_Calculator SHALL apply its existing deterministic closest-path selection so that the result is stable.

### Requirement 9: Distinct Swedish kinship terms for foster and adoptive relationships

**User Story:** As a genealogist, I want foster and adoptive relationships to use their own Swedish terms, so that a foster or adoptive relative is never mistaken for a blood relative in the relationship calculator.

#### Acceptance Criteria

1. THE Relationship_Calculator relationship classification SHALL produce a distinct foster classification when the determining link along the path is a foster link, and SHALL keep its existing distinct adoptive classification when the determining link is an adoptive link, rather than folding either into the generic "legal" classification.
2. THE Kinship_Terms module SHALL render the foster classification with foster-specific Swedish terms, including "fosterfar", "fostermor", and "fosterbarn" for the immediate foster relationships, and SHALL continue to render the adoptive classification with its adoption-specific terms.
3. WHEN a path mixes non-biological and biological links, THE classification SHALL continue to prefer the blood classification per Requirement 8 before any foster or adoptive term is produced.
4. THE existing adoptive classification and its "adoption" terms SHALL remain correct and SHALL not regress under this feature.

### Requirement 10: Ansedel report reflects parent type

**User Story:** As a genealogist, I want the Ansedel report to say which parents are foster or adoptive, so that the printed family sheet is not misleading about the nature of each parent relationship.

#### Acceptance Criteria

1. THE Ansedel_Report SHALL, for each listed parent, indicate the parent's `parentage_type` when it is foster or adoptive, using the Swedish parentage labels from `slaktbusken/ui/swedish_locale.py`.
2. WHEN a parent's `parentage_type` is biological, THE Ansedel_Report SHALL list the parent without any parentage-type annotation, preserving the current output.
3. WHEN a child has a mix of biological, foster, and adoptive parents, THE Ansedel_Report SHALL list all of them and annotate the foster and adoptive parents distinctly from the biological parents and from each other.
4. THE Ansedel_Report SHALL render a Fosterhem_Event in the person's event list using the "Fosterhem" label registered in Requirement 1, and SHALL continue to render an Adoption_Event using its "Adoption" label.

### Requirement 11: GEDCOM round-trip of foster and adoptive parentage

**User Story:** As a genealogist exchanging data with other software, I want foster and adoptive relationships to survive a GEDCOM export and re-import, so that I do not lose this information when I move my data.

#### Acceptance Criteria

1. WHEN the GEDCOM_Exporter writes a child-to-family link for a foster link, THE exporter SHALL emit the GEDCOM pedigree tag `PEDI foster` on that child reference.
2. WHEN the GEDCOM_Exporter writes a child-to-family link for an adoptive link, THE exporter SHALL emit the pedigree tag `PEDI adopted` on that child reference.
2a. WHEN the GEDCOM_Exporter writes an individual who has an Adoption_Event, THE exporter SHALL emit a `1 ADOP` individual event carrying the event's `DATE` and `PLAC` when present, so the adoption's date and place are not lost; `adoption` SHALL be added to the exporter's event-type-to-tag handling, which does not emit it today.
2b. WHEN the GEDCOM_Exporter writes an individual who has a Fosterhem_Event, THE exporter SHALL emit a custom `1 EVEN` / `2 TYPE Fosterhem` structure carrying the event's `DATE` and `PLAC` when present, following the same pattern as the existing Flytt event export, so the fostering's date and place are not lost.
2c. WHEN the GEDCOM_Exporter emits an `ADOP` or Fosterhem `EVEN` structure that is associated with a specific Parent_Set, THE exporter SHALL emit a subordinate `FAMC` pointer to the derived family for that Parent_Set, so a re-import can reconstruct which parents the placement names rather than only that the child was fostered or adopted.
2d. THE GEDCOM_Exporter SHALL emit one `ADOP`/`EVEN` structure per Placement_Start_Event, so that a child with multiple Parent_Sets of the same type exports multiple structures and their ordering and distinctness survive a round-trip.
2e. WHEN a Placement has a Placement_End_Event, THE GEDCOM_Exporter SHALL carry the end date on the same `ADOP`/`EVEN` structure as its paired start, so that the end date is not emitted as a separate orphan structure; the end date SHALL be recorded in a way that re-import can distinguish from the start date (for example a second `DATE` modelled as a span, or a labelled `NOTE`), following the same structure-loss-logging convention the Flytt export uses for data GEDCOM cannot model natively.
3. WHEN the GEDCOM_Importer reads a child reference carrying `PEDI foster`, THE importer SHALL create the corresponding parent-child relationship with `parentage_type="foster"` rather than the default biological type.
4. WHEN the GEDCOM_Importer reads a child reference carrying `PEDI adopted`, THE importer SHALL create the relationship with `parentage_type="adoptive"`.
5. WHEN the GEDCOM_Importer reads a child reference with no `PEDI` tag or an unrecognised pedigree value, THE importer SHALL create the relationship with `parentage_type="biological"` as it does today.
6. WHEN the GEDCOM_Importer creates a foster or adoptive link for which no imported Placement_Event already backs that child-parent pair, THE importer SHALL back-fill a Placement_Event of the matching type (Fosterhem for foster, Adoption for adoptive) naming that child and parent, BEFORE the Parentage_Sync_Service runs, so that the imported relationship is backed by an event and is not deleted as an orphan.
7. WHEN the GEDCOM_Importer back-fills a Placement_Event for an imported foster or adoptive link, THE importer SHALL carry over any date and place available from the GEDCOM context for that relationship, preferring a matching `ADOP` individual event's `DATE`/`PLAC` for an adoptive link and a matching custom `EVEN` / `TYPE Fosterhem` structure's `DATE`/`PLAC` for a foster link, and SHALL otherwise create the event without a date or place.
7a. WHEN a GEDCOM `ADOP` or Fosterhem `EVEN` structure carries a subordinate `FAMC` pointer, THE importer SHALL use it to associate the back-filled Placement_Event with the Parent_Set of that family, rather than guessing the parents from the pedigree alone.
8. WHEN two or more imported foster or adoptive parents for the same child share the same GEDCOM family, THE importer SHALL group them into a single back-filled Placement_Event so they form one Parent_Set rather than separate single-parent sets.
9. THE application SHALL run the Parentage_Sync_Service after a GEDCOM import so that imported foster and adoptive links are consistent with the imported and back-filled Placement_Events, giving precedence to Placement_Events as the source of truth where both are present for the same child-parent pair, and SHALL NOT delete any imported foster or adoptive relationship for which a Placement_Event exists or was back-filled.
10. WHEN a GEDCOM `ADOP`/`EVEN TYPE Fosterhem` structure on import carries an end date (per criterion 2e), THE importer SHALL create the paired Placement_End_Event with that date and the same child and parents as the start, so the placement's span round-trips.

### Requirement 12: Person checks and detail panel account for foster and adoptive parents

**User Story:** As a genealogist, I want the research checks and the person detail panel to treat foster and adoptive parents correctly, so that these relationships neither trigger meaningless warnings nor are omitted from the person's summary.

#### Acceptance Criteria

1. THE Person_Check_Engine SHALL distinguish foster and adoptive links from biological links when building its per-person parent list, so that checks which assume a biological parent do not apply to foster or adoptive parents.
2. WHEN a person has only foster or adoptive parents and no biological parents, THE Person_Check_Engine SHALL not emit a "saknar föräldrar" style finding solely because biological parents are absent, provided foster or adoptive parents are present.
3. THE person detail panel SHALL list foster and adoptive parents and annotate each distinctly from biological parents using the Swedish parentage labels.
4. WHEN a parent-child age-gap or chronology check would be meaningless for a foster relationship, THE Person_Check_Engine SHALL skip that check for the foster link; adoptive links SHALL retain whatever chronology checks already apply to them today unless they are likewise meaningless.

### Requirement 13: Persistence and backward compatibility

**User Story:** As a genealogist with existing projects, I want this feature to load my old projects without data loss, so that upgrading does not break my files.

#### Acceptance Criteria

1. WHEN the application opens a project saved before this feature, THE application SHALL read it successfully, treating the absence of any Connection_Override as no override.
2. THE Project serializer SHALL persist Connection_Overrides and SHALL omit them from the written file when none are set, so that unaffected projects are unchanged on disk.
3. WHEN the application opens a project that contains foster or adoptive links but no backing Placement_Events, THE application SHALL preserve those links and SHALL establish the source-of-truth invariant by a one-time migration that back-fills a Placement_Event for each orphan Parent_Set, so that no foster or adoptive data is silently deleted.
4. THE existing `_VALID_PARENTAGE_TYPES` set in `slaktbusken/model/validators.py` SHALL continue to accept `"foster"` and `"adoptive"` without change.
5. WHEN the application opens a project that contains descriptive Adoption_Events predating this feature, THE application SHALL preserve those events; an Adoption_Event that names no adoptive-parent participant SHALL derive no links and SHALL not be altered.

## Settled Decisions

1. **Each placement event is the single source of truth for its links.** Foster links derive from Fosterhem events; adoptive links derive from Adoption events. Neither is edited directly. (Requirement 2.)
2. **The existing `adoption` event type is reused and extended** to name adoptive parents, rather than adding a new adoptive event type. Pre-feature descriptive adoption events stay valid. (Requirements 1.9, 13.5.)
3. **One or two parents per event; the event groups the Parent_Set.** Multiple events express multiple sets, ordered by event date. (Requirements 1.3, 2.4, 2.5.)
4. **Dashed lines in distinct colours — one for foster, one for adoptive — with an optional text badge toggled in the Diagram tab.** (Requirements 3, 7.)
5. **Parentage_Fallback is a setting, enabled by default.** When biological is shown but only foster/adoptive parents are known, they are shown. (Requirement 6.)
6. **Two-layer selection: a global Show_Level (biological / non-biological / all) plus a stored per-connection override that wins.** (Requirements 4, 5.)
7. **Applies to all three diagram views for consistency.** (Requirement 4.6.)
8. **Blood paths keep priority in the relationship calculator; foster and adoptive are non-blood fallbacks.** (Requirement 8.)
9. **Foster gets distinct Swedish kinship terms; adoptive keeps its existing distinct terms.** (Requirement 9.)
10. **Ansedel annotates foster and adoptive parents distinctly.** (Requirement 10.)
11. **GEDCOM import and export carry both foster (`PEDI foster`) and adoptive (`PEDI adopted`).** (Requirement 11.)
12. **Person editor shows event-derived foster and adoptive links read-only for now; revisit if it proves awkward.** (Requirements 2.6, 2.7.)
13. **Placement end events** (`foster_home_ended` "Fosterhem upphörde", `adoption_ended` "Adoption upphörde") record when a placement ended. The derived link persists (ending is informational, like divorce not erasing a marriage). An end event is paired to a specific start via its Parent_Set, has symmetric participants, is ignored by link-sync, may not be an orphan (the editor offers to create a dateless start instead), and end-before-start is a warning. (Requirement 2A.)
14. **Barnhemsplacering (institutional/children's-home stays) is out of scope for this feature and is modelled with the existing Boende (Residence_Fact) entity**, since an institution is a place, not a parent, and a stay is an interval, not a point. The person's timeline interleaves Placements and Boende stays chronologically. (Requirement 2A.8.)
15. **The participant picker disambiguates same-named people by showing "(birth–death)" after the name** (degrading to "(birth–)", "(–death)", or no parentheses as years are known), and **filters the parent-candidate list for placement events by plausibility**: a candidate is excluded only when known dates prove it cannot be a parent of the chosen child — the candidate's birth year is not strictly earlier than the child's (strictly older, any positive gap, not a fixed minimum), or the candidate died before the child was born. People with unknown or partial dates stay in the list, and no filtering happens when the child or the child's birth year is unknown. This is a list filter (implausible candidates never appear), chosen over a post-hoc warning/error because an unfiltered list over thousands of people is unwieldy. It applies only to the Parent_Role list of placement events; the child picker and non-placement events are unaffected. (Requirement 1B.)
