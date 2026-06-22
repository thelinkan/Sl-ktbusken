# Bugfix Requirements Document

## Introduction

Five bugs exist in the photo section ("Foton") of the "Redigera Person" (Edit Person) dialog:

1. **Person list not persisted on save** — When the user edits which persons are associated with a photo (via "Personer i bilden" in FotoTab), those changes are only saved if the user explicitly clicks "Spara personlista" before clicking the main "Spara" button. If the user edits the person list and then saves the person directly, the person list changes are silently lost because `PersonEditor._on_save()` does not flush pending FotoTab changes.

2. **No way to delete/unlink a photo** — The FotoTab provides an "Lägg till foto" button for adding photos, and metadata editing for existing photos, but there is no UI affordance to remove or unlink a photo from a person. Users who add a photo by mistake or need to remove an outdated photo have no way to do so.

3. **Person not auto-added to photo's person list** — When a user adds a photo to a person (via "Lägg till foto"), the person is linked via `LinkedEntity` but is NOT automatically added to the photo's `mentioned_person_ids` list. This means the person doesn't appear in "Personer i bilden" for the photo they just added, which is counter-intuitive.

4. **Cannot distinguish persons with same name in person search** — In the "Personer i bilden" section of FotoTab, the PersonListWidget combo box shows persons using only their name (via `_person_display_name()`). When multiple persons share the same name (e.g., two "Erik Andersson"), the user cannot tell them apart. The display should include birth year and death year (if available) for disambiguation, e.g., "Erik Andersson (1845–1901)".

5. **Tilltalsnamn marker (*) breaks person search** — In person names, a `*` character is used as a tilltalsnamn (calling name) marker placed after the given name that is the person's calling name. When `_person_display_name()` includes this `*` in the combo box display text, it breaks the QCompleter search because searching for "Erik Andersson" won't match "Erik* Andersson". The `*` should be stripped from the display/search text since it is metadata, not part of the name.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the user modifies the person list ("Personer i bilden") for a photo in FotoTab and then clicks the main "Spara" button without first clicking "Spara personlista" THEN the system silently discards the person list changes — the MediaItem's `mentioned_person_ids`, `mentioned_names`, and `linked_entities` remain unchanged after save

1.2 WHEN the user has a photo linked to a person and wants to remove/unlink it THEN the system provides no button or action to delete or unlink the photo from the person

1.3 WHEN the user adds a photo to a person via "Lägg till foto" THEN the system does not add the current person to the photo's `mentioned_person_ids` list, so the person does not appear in "Personer i bilden" for the newly added photo

1.4 WHEN multiple persons share the same name (e.g., two "Erik Andersson") and the user opens the person search combo box in "Personer i bilden" THEN the system displays only the name without birth/death years, making it impossible to distinguish between the persons

1.5 WHEN a person's given name contains a tilltalsnamn marker `*` (e.g., "Erik*") and the user searches for that person by typing the name without `*` (e.g., "Erik Andersson") THEN the system fails to match the person in the QCompleter because the display text contains "Erik* Andersson" which does not match the search query "Erik Andersson"

### Expected Behavior (Correct)

2.1 WHEN the user modifies the person list ("Personer i bilden") for a photo in FotoTab and then clicks the main "Spara" button THEN the system SHALL automatically persist the pending person list changes to the MediaItem (updating `mentioned_person_ids`, `mentioned_names`, and syncing `linked_entities`) before completing the save

2.2 WHEN the user has a photo linked to a person THEN the system SHALL provide a "Ta bort foto" (delete photo) button that removes the link between the selected photo and the current person (removing the corresponding `LinkedEntity` from the MediaItem), and if no other entities remain linked to the photo, removes the MediaItem from project data entirely

2.3 WHEN the user adds a photo to a person via "Lägg till foto" THEN the system SHALL automatically add the current person's ID to the new MediaItem's `mentioned_person_ids` list so that the person appears in "Personer i bilden" immediately

2.4 WHEN multiple persons share the same name THEN the system SHALL display birth year and death year (if available) after the name in the combo box, formatted as "Name (birth_year–death_year)", e.g., "Erik Andersson (1845–1901)", to allow the user to distinguish between them

2.5 WHEN a person's given name contains a tilltalsnamn marker `*` THEN the system SHALL strip the `*` character from the display text and search text in the combo box so that searching for the name without `*` matches the person correctly

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the user adds a new photo via "Lägg till foto" THEN the system SHALL CONTINUE TO copy the file to Foto_Mapp, create a MediaItem with a LinkedEntity linking it to the current person, and display it in the photo table

3.2 WHEN the user edits photo metadata (title, Foto_Typ) and clicks "Spara ändringar" THEN the system SHALL CONTINUE TO update the MediaItem title in the format `[Foto_Typ] title`

3.3 WHEN the user clicks "Spara personlista" explicitly THEN the system SHALL CONTINUE TO persist person list changes to the MediaItem immediately as before

3.4 WHEN the user selects a photo in the table THEN the system SHALL CONTINUE TO display the metadata editing panel, person list section, and image preview

3.5 WHEN the user sets a profile photo via "Välj som profilbild" THEN the system SHALL CONTINUE TO store the media ID as `profile_media_id` on the Person

3.6 WHEN the user adds a photo and the person is auto-added to `mentioned_person_ids` THEN the system SHALL CONTINUE TO allow the user to add or remove other persons from the photo's person list as before

3.7 WHEN the user searches for a person whose name does not contain a `*` marker THEN the system SHALL CONTINUE TO match and display that person in the combo box as before

3.8 WHEN the user selects a person from the combo box and clicks "Lägg till" THEN the system SHALL CONTINUE TO add the person to the photo's person list and emit `persons_changed` as before

3.9 WHEN a person has only one name variant and no birth/death year data THEN the system SHALL CONTINUE TO display the person's name without parenthetical year information (no empty parentheses)
