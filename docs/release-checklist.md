# Release checklist

Items that must be resolved before a given release. Each item names the release it blocks, its status and its acceptance condition.

## Blockers for Släktbusken 1.0

### TRK-1 Non-destructive GEDCOM update handling

- **Status:** open. Mandatory pre-1.0 release blocker.
- **Scope:** separate spec. It is not part of the `person-comparison-and-merge` feature and is not implemented by it.
- **Problem:** an update import currently overwrites names, notes, title and occupation of existing persons. It can therefore overwrite user-edited or merged data of an active person (for example the surviving person of a merge).
- **Requirement:** an update import must not silently overwrite user-edited or merged data of an active person, and every difference must be presented for review before any change is applied.
- **Direction (design.md section 14):** a baseline snapshot hash per `PersonMapping`, a three-way comparison of baseline, current and incoming values, and a review dialog where the user decides each difference. Without a baseline, every difference is treated as a conflict.
- **Acceptance:** an update import leaves every field of every active person unchanged until the user accepts a difference.
- **Warning removal:** the wizard warning (the GEDCOM update warning shown in the merge preview, controlled by `NON_DESTRUCTIVE_UPDATE_AVAILABLE` in `slaktbusken/gedcom/capabilities.py`) is removed by setting the constant to `True` in the same change that implements the handling. The warning exists only once that constant is added by the merge feature (task 11.18).
- **Source:** `.kiro/specs/person-comparison-and-merge/design.md`, "Tracked items" (TRK-1) and section 14. Requirement 30 criteria 14 and 15, Requirement 33 criterion 10.
