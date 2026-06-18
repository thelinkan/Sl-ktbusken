# Requirements Document

## Introduction

This feature extends the "DNA & Kluster" tab in the Person Editor (Redigera personer) to allow users to create new DNA profiles (tests) and DNA matches directly from within the tab. Currently, the DNA profiles and matches lists are read-only. This feature adds creation capabilities following the same UI patterns already established for cluster management (buttons + dialogs).

## Glossary

- **Person_Editor**: The tabbed editor widget for Person records (Redigera personer), implemented as `PersonEditor` in PySide6.
- **DNA_Tab**: The "DNA & Kluster" tab within the Person_Editor that displays DNA profiles, matches, and cluster memberships.
- **DNA_Profile**: A DNA test result (kit) belonging to a person, containing company, test type, kit name, kit ID, administrator, and notes.
- **DNA_Match**: A recorded DNA match between two DNA profiles, containing shared centiMorgans, shared percentage, segment count, largest segment, match source, and notes.
- **DNA_Company**: A DNA testing company (e.g., AncestryDNA, MyHeritage, FamilyTreeDNA).
- **Profile_Dialog**: A modal dialog for creating a new DNA profile for the current person.
- **Match_Dialog**: A modal dialog for creating a new DNA match associated with one of the current person's profiles.
- **Project_Data**: The in-memory data store containing all project entities including persons, DNA profiles, matches, and companies.

## Requirements

### Requirement 1: Add DNA Profile Button

**User Story:** As a genealogist, I want to have a button to create a new DNA profile from the DNA tab, so that I can register DNA tests without leaving the person editor.

#### Acceptance Criteria

1. THE DNA_Tab SHALL display a "Lägg till profil" button positioned vertically below the DNA profiles list.
2. WHEN the user clicks the "Lägg till profil" button, THE Person_Editor SHALL open the Profile_Dialog as a modal dialog.
3. WHILE no person is loaded in the Person_Editor, THE "Lägg till profil" button SHALL be hidden.
4. WHILE a person is loaded in the Person_Editor, THE "Lägg till profil" button SHALL be visible and enabled.

### Requirement 2: DNA Profile Creation Dialog

**User Story:** As a genealogist, I want a dialog to enter DNA profile details, so that I can register a new DNA test for the current person.

#### Acceptance Criteria

1. WHEN the Profile_Dialog opens, THE Profile_Dialog SHALL display input fields for: company (dropdown from existing DNA_Company entries), test type (dropdown: autosomal, Y-DNA, mtDNA), kit name (text, maximum 100 characters), kit ID (text, maximum 50 characters), and notes (multiline text, maximum 2000 characters).
2. IF the user confirms the Profile_Dialog without selecting a company or test type, THEN THE Profile_Dialog SHALL display a validation error indicating the missing required field and prevent confirmation.
3. WHEN the user confirms the Profile_Dialog with a company and test type selected, THE Person_Editor SHALL create a new DNA_Profile with a generated unique ID and the current person's ID as person_id.
4. WHEN the user confirms the Profile_Dialog, THE Person_Editor SHALL add the new DNA_Profile to Project_Data.dna_profiles.
5. WHEN the user confirms the Profile_Dialog, THE Person_Editor SHALL refresh the DNA profiles list to display the new entry.
6. IF no DNA_Company entries exist in the project, THEN THE Profile_Dialog SHALL display an informational message indicating that companies must be created first and SHALL disable the confirm button.
7. WHEN the user cancels the Profile_Dialog, THE Person_Editor SHALL not modify Project_Data.

### Requirement 3: Add DNA Match Button

**User Story:** As a genealogist, I want to have a button to create a new DNA match from the DNA tab, so that I can register matches without leaving the person editor.

#### Acceptance Criteria

1. THE DNA_Tab SHALL display a "Lägg till matchning" button positioned vertically below the DNA matches list.
2. WHEN the user clicks the "Lägg till matchning" button, THE Person_Editor SHALL open the Match_Dialog as a modal dialog.
3. WHILE no person is loaded in the Person_Editor, THE "Lägg till matchning" button SHALL be hidden.
4. WHILE the current person has no DNA profiles, THE "Lägg till matchning" button SHALL be disabled with a tooltip "En DNA-profil krävs för att skapa matchningar" explaining that a profile is required first.

### Requirement 4: DNA Match Creation Dialog

**User Story:** As a genealogist, I want a dialog to enter DNA match details, so that I can register a match between the current person's profile and another profile.

#### Acceptance Criteria

1. WHEN the Match_Dialog opens, THE Match_Dialog SHALL display input fields for: profile 1 (dropdown of the current person's DNA profiles, pre-selected if only one exists), profile 2 (dropdown of all other DNA profiles in Project_Data), shared cM (numeric, range 0.01 to 10000.00), shared percentage (numeric, range 0.01 to 100.00), segment count (integer, range 1 to 100000), largest segment cM (numeric, range 0.01 to 10000.00), match source (text, maximum 200 characters, default "internal"), and notes (multiline text, maximum 2000 characters).
2. WHEN the current person has exactly one DNA profile, THE Match_Dialog SHALL pre-select that profile as profile 1 and disable the profile 1 dropdown.
3. WHEN the user selects both profiles, enters a shared cM value, and confirms the dialog, THE Person_Editor SHALL create a new DNA_Match with a generated unique ID, the two selected profile IDs, and all entered field values.
4. WHEN the user confirms the Match_Dialog, THE Person_Editor SHALL add the new DNA_Match to Project_Data.dna_matches.
5. WHEN the user confirms the Match_Dialog, THE Person_Editor SHALL refresh the DNA matches list to display the new entry.
6. IF the user attempts to confirm the Match_Dialog without selecting both profiles or without entering a shared cM value, THEN THE Match_Dialog SHALL display a validation error indicating the missing required fields and prevent confirmation.
7. IF the user selects the same profile for both profile 1 and profile 2, THEN THE Match_Dialog SHALL display a validation error and prevent confirmation.
8. IF no other DNA profiles exist in Project_Data when the Match_Dialog opens, THEN THE Match_Dialog SHALL display an informational message indicating that another person's DNA profile must exist to create a match.
9. WHEN the user cancels the Match_Dialog, THE Person_Editor SHALL not modify Project_Data.

### Requirement 5: List Refresh After Creation

**User Story:** As a genealogist, I want the DNA lists to update immediately after I create a new profile or match, so that I can see my changes reflected without re-opening the editor.

#### Acceptance Criteria

1. WHEN a new DNA_Profile is created via the Profile_Dialog, THE DNA_Tab SHALL refresh the profiles list so the new entry appears, and refresh the matches list.
2. WHEN a new DNA_Match is created via the Match_Dialog, THE DNA_Tab SHALL refresh the matches list so the new entry appears.
3. WHEN a new DNA_Profile is created and the person previously had no profiles, THE "Lägg till matchning" button SHALL become enabled and its disabled tooltip SHALL be removed.
