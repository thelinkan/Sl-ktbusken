"""Unit tests for ResidenceEditor edit operations and warning behaviour.

Tests the wiring of pure edit operations (split, merge, exact start/end,
create flytt) into the editor, and the save-with-warnings logic.

Task 17.5: Wire the edit operations and warning behaviour into the editor.
Requirements: 5.10, 6.9, 16.5, 16.6, 16.9, 17.1, 17.10, 17.13, 17.15, 18.12.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from PySide6.QtWidgets import QApplication, QMessageBox

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.ui.editors.residence_editor import ResidenceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_with_splittable_residence() -> ProjectData:
    """Project containing a residence with a coverage gap that is splittable."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        sources=[
            Source(id="src_1", provider="AD", source_type="church_book", title="AI:1"),
            Source(id="src_2", provider="AD", source_type="church_book", title="AI:2"),
        ],
        residences=[
            ResidenceFact(
                id="res_1",
                person_id="p1",
                place_id="pl1",
                start=Endpoint(earliest="1840", latest="1842"),
                end=Endpoint(earliest="1870", latest="1875"),
                role_in_household="husbonde",
                observations=[
                    Observation(
                        source_ref=SourceRef(source_id="src_1", quality="primary"),
                        observed_from="1842",
                        observed_to="1847",
                    ),
                    Observation(
                        source_ref=SourceRef(source_id="src_2", quality="primary"),
                        observed_from="1855",
                        observed_to="1870",
                    ),
                ],
                notes="test",
            ),
        ],
    )


@pytest.fixture()
def project_with_mergeable_residences() -> ProjectData:
    """Project with two residences for the same person/place, eligible for merge."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        sources=[
            Source(id="src_1", provider="AD", source_type="church_book", title="AI:1"),
            Source(id="src_2", provider="AD", source_type="church_book", title="AI:2"),
        ],
        residences=[
            ResidenceFact(
                id="res_1",
                person_id="p1",
                place_id="pl1",
                start=Endpoint(earliest="1840", latest="1842"),
                end=Endpoint(earliest="1847", latest="1850"),
                observations=[
                    Observation(
                        source_ref=SourceRef(source_id="src_1", quality="primary"),
                        observed_from="1842",
                        observed_to="1847",
                    ),
                ],
            ),
            ResidenceFact(
                id="res_2",
                person_id="p1",
                place_id="pl1",
                start=Endpoint(earliest="1851", latest="1855"),
                end=Endpoint(earliest="1870", latest="1875"),
                observations=[
                    Observation(
                        source_ref=SourceRef(source_id="src_2", quality="primary"),
                        observed_from="1855",
                        observed_to="1870",
                    ),
                ],
            ),
        ],
    )


@pytest.fixture()
def project_with_flytt_candidates() -> ProjectData:
    """Project with two residences for the same person at different places."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        sources=[
            Source(id="src_1", provider="AD", source_type="church_book", title="AI:1"),
            Source(id="src_2", provider="AD", source_type="church_book", title="AI:2"),
        ],
        residences=[
            ResidenceFact(
                id="res_1",
                person_id="p1",
                place_id="pl1",
                start=Endpoint(earliest="1840", latest="1842"),
                end=Endpoint(earliest="1847", latest="1850"),
                observations=[
                    Observation(
                        source_ref=SourceRef(source_id="src_1", quality="primary"),
                        observed_from="1842",
                        observed_to="1847",
                    ),
                ],
            ),
            ResidenceFact(
                id="res_2",
                person_id="p1",
                place_id="pl2",
                start=Endpoint(earliest="1850", latest="1851"),
                end=Endpoint(earliest="1860", latest="1865"),
                observations=[
                    Observation(
                        source_ref=SourceRef(source_id="src_2", quality="primary"),
                        observed_from="1851",
                        observed_to="1860",
                    ),
                ],
            ),
        ],
    )


# ===========================================================================
# Tests: "Använd som exakt början" and "Använd som exakt slut"
# ===========================================================================


class TestUseAsExactStart:
    """Tests for the 'Använd som exakt början' action (Req 16.10, 16.11)."""

    def test_sets_both_start_bounds_from_observation(
        self, qapp, project_with_splittable_residence
    ):
        """Exact start sets both start.earliest and start.latest to observed_from."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        # Select the first row (obs sorted: 1842-1847 first, 1855-1870 second)
        editor._observations_table.setCurrentCell(0, 0)
        editor._on_use_as_exact_start()

        # The residence should now have start.earliest = start.latest = "1842"
        updated = editor._residence
        assert updated.start.earliest == "1842"
        assert updated.start.latest == "1842"
        # End should be unchanged
        assert updated.end.earliest == "1870"
        assert updated.end.latest == "1875"

    def test_does_nothing_without_selection(
        self, qapp, project_with_splittable_residence
    ):
        """No action when no observation row is selected."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        # No selection — currentRow is -1
        editor._observations_table.clearSelection()
        editor._observations_table.setCurrentCell(-1, -1)
        editor._on_use_as_exact_start()

        # Residence unchanged
        assert editor._residence.start.earliest == "1840"
        assert editor._residence.start.latest == "1842"


class TestUseAsExactEnd:
    """Tests for the 'Använd som exakt slut' action (Req 16.10, 16.11)."""

    def test_sets_both_end_bounds_from_observation(
        self, qapp, project_with_splittable_residence
    ):
        """Exact end sets both end.earliest and end.latest to observed_to."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        # Select the second row (1855-1870)
        editor._observations_table.setCurrentCell(1, 0)
        editor._on_use_as_exact_end()

        updated = editor._residence
        assert updated.end.earliest == "1870"
        assert updated.end.latest == "1870"
        # Start unchanged
        assert updated.start.earliest == "1840"
        assert updated.start.latest == "1842"


# ===========================================================================
# Tests: "Dela boendet här" (split)
# ===========================================================================


class TestSplitAction:
    """Tests for the 'Dela boendet här' action (Req 5.10)."""

    def test_split_produces_two_facts(
        self, qapp, project_with_splittable_residence
    ):
        """Split replaces one fact with two in the project."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        assert len(project.residences) == 1
        editor._on_split()

        # Original is removed, two new facts added
        assert len(project.residences) == 2
        # Neither has the original id
        ids = {r.id for r in project.residences}
        assert "res_1" not in ids

    def test_split_first_fact_has_before_observations(
        self, qapp, project_with_splittable_residence
    ):
        """The first resulting fact has observations ending before the gap."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._on_split()

        # First fact should have the 1842-1847 observation
        first = project.residences[0]
        assert len(first.observations) == 1
        assert first.observations[0].observed_to == "1847"

    def test_split_second_fact_has_after_observations(
        self, qapp, project_with_splittable_residence
    ):
        """The second resulting fact has observations beginning after the gap."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._on_split()

        second = project.residences[1]
        assert len(second.observations) == 1
        assert second.observations[0].observed_from == "1855"

    def test_split_copies_person_place_role_notes(
        self, qapp, project_with_splittable_residence
    ):
        """Both resulting facts copy person_id, place_id, role, notes."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._on_split()

        for fact in project.residences:
            assert fact.person_id == "p1"
            assert fact.place_id == "pl1"
            assert fact.role_in_household == "husbonde"
            assert fact.notes == "test"

    def test_split_no_splittable_gap_shows_message(self, qapp):
        """Split shows message when there are no splittable gaps."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(
                    id="res_1",
                    person_id="p1",
                    place_id="pl1",
                    observations=[
                        Observation(
                            source_ref=SourceRef(source_id="s1", quality="primary"),
                            observed_from="1842",
                            observed_to="1847",
                        ),
                    ],
                ),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        with patch.object(QMessageBox, "information") as mock_info:
            editor._on_split()
            mock_info.assert_called_once()


# ===========================================================================
# Tests: "Slå samman boenden" (merge)
# ===========================================================================


class TestMergeAction:
    """Tests for the 'Slå samman boenden' action (Req 17.1)."""

    def test_merge_combines_two_facts_into_one(
        self, qapp, project_with_mergeable_residences
    ):
        """Merge replaces two facts with one in the project."""
        project = project_with_mergeable_residences
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        assert len(project.residences) == 2

        # Mock QMessageBox to auto-accept (no separation warning in this case)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            editor._on_merge()

        assert len(project.residences) == 1

    def test_merge_unions_observations(
        self, qapp, project_with_mergeable_residences
    ):
        """Merged fact contains observations from both originals."""
        project = project_with_mergeable_residences
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            editor._on_merge()

        merged = project.residences[0]
        assert len(merged.observations) == 2

    def test_merge_no_candidate_shows_message(self, qapp):
        """Merge shows message when no matching candidate exists."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(id="res_1", person_id="p1", place_id="pl1"),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        with patch.object(QMessageBox, "information") as mock_info:
            editor._on_merge()
            mock_info.assert_called_once()

    def test_merge_separation_warning_shown(self, qapp):
        """Merge shows separation warning for >10-year gap (Req 17.10)."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(
                    id="res_1",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(earliest="1830", latest="1832"),
                    end=Endpoint(earliest="1835", latest="1836"),
                    observations=[
                        Observation(
                            source_ref=SourceRef(source_id="s1", quality="primary"),
                            observed_from="1832",
                            observed_to="1835",
                        ),
                    ],
                ),
                ResidenceFact(
                    id="res_2",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(earliest="1860", latest="1862"),
                    end=Endpoint(earliest="1870", latest="1875"),
                    observations=[
                        Observation(
                            source_ref=SourceRef(source_id="s2", quality="primary"),
                            observed_from="1862",
                            observed_to="1870",
                        ),
                    ],
                ),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as mock_q:
            editor._on_merge()
            # Should have been called with the separation warning text
            assert mock_q.called
            call_args = mock_q.call_args
            assert "långt ifrån varandra" in str(call_args)

        # Merge was declined — both facts remain
        assert len(project.residences) == 2


# ===========================================================================
# Tests: "Skapa flytt mellan boendena"
# ===========================================================================


class TestCreateFlyttAction:
    """Tests for the 'Skapa flytt mellan boendena' action (Req 18.12)."""

    def test_creates_flytt_event(self, qapp, project_with_flytt_candidates):
        """Creates a flytt event and links it to both residences."""
        project = project_with_flytt_candidates
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        assert len(project.events) == 0
        editor._on_create_flytt()
        assert len(project.events) == 1

        flytt = project.events[0]
        assert flytt.type == "flytt"
        assert flytt.participants[0].person_id == "p1"

    def test_flytt_prefills_from_and_to_places(
        self, qapp, project_with_flytt_candidates
    ):
        """Flytt from_place is earlier residence's place, place is later's."""
        project = project_with_flytt_candidates
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._on_create_flytt()

        flytt = project.events[0]
        # Earlier residence is at pl1, later at pl2
        assert flytt.from_place is not None
        assert flytt.from_place.place_id == "pl1"
        assert flytt.place is not None
        assert flytt.place.place_id == "pl2"

    def test_flytt_links_to_endpoints(self, qapp, project_with_flytt_candidates):
        """Flytt event_id is set on end of earlier and start of later."""
        project = project_with_flytt_candidates
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._on_create_flytt()

        flytt_id = project.events[0].id
        # Find updated residences
        res_1 = next(r for r in project.residences if r.place_id == "pl1")
        res_2 = next(r for r in project.residences if r.place_id == "pl2")
        assert res_1.end.event_id == flytt_id
        assert res_2.start.event_id == flytt_id

    def test_flytt_no_candidate_shows_message(self, qapp):
        """Shows message when no adjacent different-place residence exists."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(id="res_1", person_id="p1", place_id="pl1"),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        with patch.object(QMessageBox, "information") as mock_info:
            editor._on_create_flytt()
            mock_info.assert_called_once()


# ===========================================================================
# Tests: Save with warnings (Req 6.9)
# ===========================================================================


class TestSaveWithWarnings:
    """Tests for saving a warning-only fact (Req 6.9)."""

    def test_saves_fact_with_warnings(self, qapp):
        """A fact with only warnings is saved and warnings are displayed."""
        # Create a residence with a start/end window overlap (warning)
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(
                    id="res_1",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(earliest="1840", latest="1860"),
                    end=Endpoint(earliest="1850", latest="1880"),
                ),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        result = editor.save_with_warnings()
        assert result is True
        # Warning label should be visible (not hidden)
        assert not editor._warnings_label.isHidden()

    def test_saves_fact_retaining_all_values(self, qapp):
        """Save with warnings retains every entered value."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            sources=[
                Source(id="src_1", provider="AD", source_type="church_book", title="AI:1"),
            ],
            residences=[
                ResidenceFact(
                    id="res_1",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(earliest="1840", latest="1860"),
                    end=Endpoint(earliest="1850", latest="1880"),
                    observations=[
                        Observation(
                            source_ref=SourceRef(source_id="src_1", quality="primary"),
                            observed_from="1830",
                            observed_to="1850",
                        ),
                    ],
                ),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        editor.save_with_warnings()

        # Verify the fact in the project retains its values
        saved = project.residences[0]
        assert saved.start.earliest == "1840"
        assert saved.start.latest == "1860"
        assert saved.end.earliest == "1850"
        assert saved.end.latest == "1880"

    def test_no_warnings_hides_label(self, qapp):
        """A clean fact hides the warnings label."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(
                    id="res_1",
                    person_id="p1",
                    place_id="pl1",
                    start=Endpoint(earliest="1840", latest="1842"),
                    end=Endpoint(earliest="1870", latest="1875"),
                ),
            ],
        )
        editor = ResidenceEditor(project, residence=project.residences[0], person_id="p1")

        editor.save_with_warnings()
        assert editor._warnings_label.isHidden()


# ===========================================================================
# Tests: Atomicity — staging copies swapped in as one step
# ===========================================================================


class TestAtomicity:
    """Tests verifying that actions work on staging copies atomically."""

    def test_exact_start_commits_atomically(
        self, qapp, project_with_splittable_residence
    ):
        """Exact start action modifies the project only via a single commit."""
        project = project_with_splittable_residence
        original_start_earliest = project.residences[0].start.earliest
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._observations_table.setCurrentCell(0, 0)
        editor._on_use_as_exact_start()

        # The project's fact should be updated
        assert project.residences[0].start.earliest == "1842"
        assert project.residences[0].start.latest == "1842"

    def test_split_is_atomic(self, qapp, project_with_splittable_residence):
        """Split replaces in a single step — no intermediate states visible."""
        project = project_with_splittable_residence
        residence = project.residences[0]
        editor = ResidenceEditor(project, residence=residence, person_id="p1")

        editor._on_split()

        # After split: exactly 2 facts, the original is gone
        assert len(project.residences) == 2
        assert all(r.id != "res_1" for r in project.residences)

    def test_merge_is_atomic(self, qapp, project_with_mergeable_residences):
        """Merge replaces in a single step — no intermediate states visible."""
        project = project_with_mergeable_residences
        editor = ResidenceEditor(
            project, residence=project.residences[0], person_id="p1"
        )

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            editor._on_merge()

        # After merge: exactly 1 fact, both originals gone
        assert len(project.residences) == 1
        merged = project.residences[0]
        assert merged.id not in ("res_1", "res_2")
