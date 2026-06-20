# Requirements Document

## Introduction

This feature adds a visual image chooser for assigning a logo to a DNA company in the DNA Editor. Currently, users must manually type a media-ID into a text field. This feature replaces that workflow with a button that opens a file dialog, handles copying the image to the project's `media/logo` folder if needed, creates a corresponding `MediaItem` entry in `ProjectData`, and associates it with the DNA company. The logo will later be displayed next to DNA matchings in list views.

## Glossary

- **DNA_Editor**: The tabbed editor widget for DNA-related records (`DnaEditor`), containing the companies tab where logos are managed.
- **DNA_Company**: A DNA testing company entity (`DnaCompany` dataclass) with fields including `logo_media_id`.
- **Media_Item**: A media record (`MediaItem` dataclass) representing a file with metadata such as type, file path, and title.
- **Project_Data**: The in-memory data store (`ProjectData`) containing all project entities including media items and DNA companies.
- **Logo_Folder**: The `media/logo` subfolder within the project directory, designated for logo image files.
- **Logo_Chooser**: A file dialog that allows the user to select an image file from the filesystem.
- **Project_Folder**: The root directory of the current project on disk.

## Requirements

### Requirement 1: Logo Image Chooser Button

**User Story:** As a genealogist, I want a button to browse and select a logo image for a DNA company, so that I can visually associate companies with their logos without manually entering media IDs.

#### Acceptance Criteria

1. THE DNA_Editor companies tab SHALL display a "Välj logo..." button adjacent to the existing logo media-ID field in the company form.
2. WHILE no company is selected in the DNA_Editor companies tab, THE "Välj logo..." button SHALL be disabled.
3. WHEN the user clicks the "Välj logo..." button, THE DNA_Editor SHALL open the Logo_Chooser file dialog.
4. THE Logo_Chooser SHALL display only files matching the extensions PNG, JPG, JPEG, GIF, SVG, BMP, and WEBP in the file list.
5. WHEN the Logo_Chooser opens, THE Logo_Chooser SHALL default its initial directory to the project's Logo_Folder.
6. IF the Logo_Folder does not exist when the Logo_Chooser opens, THEN THE DNA_Editor SHALL create the Logo_Folder before opening the dialog.

### Requirement 2: Image Already in Logo Folder

**User Story:** As a genealogist, I want to select a logo that already resides in the logo folder without any file copying, so that existing logos can be assigned directly.

#### Acceptance Criteria

1. WHEN the user selects an image file that is located within the Logo_Folder or any of its subdirectories, THE DNA_Editor SHALL use the selected file path relative to the Project_Folder, using forward slashes as path separators, without copying the file.
2. WHEN the user selects an image file from the Logo_Folder, THE DNA_Editor SHALL create a new Media_Item with type "logo", the relative file path, and the filename (without extension) as title.
3. IF a Media_Item with the same relative file path (compared case-insensitively) already exists in Project_Data, THEN THE DNA_Editor SHALL use the existing Media_Item's ID for the company association instead of creating a duplicate.
4. WHEN a Media_Item is created or reused for the selected logo, THE DNA_Editor SHALL set the DNA_Company `logo_media_id` field to that Media_Item's ID.

### Requirement 3: Image from Outside Logo Folder

**User Story:** As a genealogist, I want to select a logo image from anywhere on my computer and have it automatically copied to the logo folder, so that I can use any image without manual file management.

#### Acceptance Criteria

1. WHEN the user selects an image file that is NOT located within the Logo_Folder, THE DNA_Editor SHALL copy the file to the Logo_Folder.
2. IF the Logo_Folder does not exist at the time of copying, THEN THE DNA_Editor SHALL create the Logo_Folder before copying the file.
3. WHEN copying a file to the Logo_Folder, THE DNA_Editor SHALL preserve the original filename.
4. IF a file with the same name already exists in the Logo_Folder, THEN THE DNA_Editor SHALL generate a unique filename by appending a numeric suffix starting at 1 and incrementing until an unused name is found (e.g., "logo_1.png", "logo_2.png") before copying.
5. WHEN the file copy completes, THE DNA_Editor SHALL create a new Media_Item with type "logo", the file path relative to the Project_Folder, and the original filename (without extension) as title.
6. IF a Media_Item with the same relative file path already exists in Project_Data, THEN THE DNA_Editor SHALL reuse the existing Media_Item instead of creating a duplicate.
7. IF the file copy fails due to a filesystem error, THEN THE DNA_Editor SHALL display an error message indicating the failure reason to the user and leave the DNA_Company logo_media_id unchanged.

### Requirement 4: Associate Logo with DNA Company

**User Story:** As a genealogist, I want the selected logo to be linked to the DNA company record, so that the logo appears in DNA matching lists.

#### Acceptance Criteria

1. WHEN a Media_Item is created or identified for the selected logo, THE DNA_Editor SHALL add the newly created Media_Item to Project_Data.media before updating the DNA_Company record, and SHALL set the DNA_Company `logo_media_id` field to the Media_Item's ID.
2. IF a Media_Item with the same file path already exists in Project_Data.media, THEN THE DNA_Editor SHALL reuse the existing Media_Item and SHALL NOT add a duplicate entry to Project_Data.media.
3. WHEN the logo is successfully associated, THE DNA_Editor SHALL update the logo media-ID text field to display the new Media_Item ID.
4. WHEN the DNA_Company already has a `logo_media_id` set and the user selects a new logo, THE DNA_Editor SHALL overwrite the existing `logo_media_id` with the new Media_Item's ID.
5. WHEN the user cancels the Logo_Chooser without selecting a file, THE DNA_Editor SHALL leave the DNA_Company `logo_media_id` field and the logo media-ID text field unchanged.

### Requirement 5: Logo Preview

**User Story:** As a genealogist, I want to see a preview of the selected logo in the company form, so that I can confirm the correct image was chosen.

#### Acceptance Criteria

1. WHEN a logo is associated with the DNA_Company, THE DNA_Editor SHALL display a thumbnail preview of the logo image in the company form area, scaled to fit within a 64x64 pixel bounding box while preserving the original aspect ratio.
2. WHEN the DNA_Company logo_media_id changes, THE DNA_Editor SHALL immediately update the preview area to reflect the newly associated logo image.
3. WHILE no logo is associated with the DNA_Company, THE DNA_Editor SHALL display an empty placeholder area of 64x64 pixels in the preview location.
4. IF the logo image file cannot be found on disk, THEN THE DNA_Editor SHALL display a visually distinct "missing image" indicator in the preview area that differs from the empty placeholder shown when no logo is associated.

### Requirement 6: Logo Display in DNA Match Lists

**User Story:** As a genealogist, I want to see the DNA company logo displayed next to DNA matchings in list views, so that I can quickly identify which company each match belongs to.

#### Acceptance Criteria

1. WHEN a DNA match list displays match entries, THE list SHALL show the associated DNA_Company logo (resolved via the other profile's company → logo_media_id → Media_Item → file) as a 24x24 pixel icon next to each match entry.
2. IF a DNA_Company has no logo assigned, THEN THE list SHALL display a default 24x24 pixel placeholder icon for matches from that company.
3. IF the logo image file is missing from disk, THEN THE list SHALL display a 24x24 pixel "missing image" placeholder icon.
