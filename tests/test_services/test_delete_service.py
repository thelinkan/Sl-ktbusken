"""Unit tests for delete_service event classification, family finding, and DeleteService."""

from __future__ import annotations

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.delete_service import (
    DeleteService,
    DeletionConsequences,
    classify_events,
    find_affected_families,
)
from slaktbusken.services.project_service import ProjectService


def _make_project(
    events: list[Event] | None = None,
    families: list[Family] | None = None,
) -> ProjectData:
    """Create a minimal ProjectData with the given events and families."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        events=events or [],
        families=families or [],
    )


def _make_event(event_id: str, participant_ids: list[str]) -> Event:
    """Create an Event with participants from a list of person IDs."""
    return Event(
        id=event_id,
        type="birth",
        participants=[
            Participant(person_id=pid, role="primary") for pid in participant_ids
        ],
    )


def _make_family(
    family_id: str,
    partner_ids: list[str] | None = None,
    children: list[str] | None = None,
    event_ids: list[str] | None = None,
    parent_child_links: list[ParentChildLink] | None = None,
) -> Family:
    """Create a Family with given partners, children, and event_ids."""
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=pid, role="partner") for pid in (partner_ids or [])],
        children=children or [],
        event_ids=event_ids or [],
        parent_child_links=parent_child_links or [],
    )


class TestClassifyEvents:
    """Tests for classify_events."""

    def test_exclusive_event_single_participant(self) -> None:
        """Event where person is the only participant is exclusive."""
        event = _make_event("evt_1", ["person_1"])
        project = _make_project(events=[event])

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == [event]
        assert family == []
        assert shared == []

    def test_exclusive_event_multiple_same_person(self) -> None:
        """Event where all participants reference the same person is exclusive."""
        event = Event(
            id="evt_1",
            type="birth",
            participants=[
                Participant(person_id="person_1", role="primary"),
                Participant(person_id="person_1", role="witness"),
            ],
        )
        project = _make_project(events=[event])

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == [event]
        assert family == []
        assert shared == []

    def test_empty_participants_is_exclusive(self) -> None:
        """Event with empty participants list is treated as exclusive."""
        event = Event(id="evt_1", type="birth", participants=[])
        project = _make_project(events=[event])

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == [event]
        assert family == []
        assert shared == []

    def test_family_event(self) -> None:
        """Event in a family's event_ids with person as participant is a family event."""
        event = _make_event("evt_1", ["person_1", "person_2"])
        fam = _make_family("fam_1", partner_ids=["person_1", "person_2"], event_ids=["evt_1"])
        project = _make_project(events=[event], families=[fam])

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == []
        assert family == [event]
        assert shared == []

    def test_non_family_shared_event(self) -> None:
        """Shared event not in any family event_ids is non-family shared."""
        event = _make_event("evt_1", ["person_1", "person_2"])
        project = _make_project(events=[event])

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == []
        assert family == []
        assert shared == [event]

    def test_unrelated_events_are_excluded(self) -> None:
        """Events where the person is not a participant are not classified."""
        event = _make_event("evt_1", ["person_2", "person_3"])
        project = _make_project(events=[event])

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == []
        assert family == []
        assert shared == []

    def test_mixed_classification(self) -> None:
        """Multiple events are correctly sorted into all three categories."""
        excl_event = _make_event("evt_excl", ["person_1"])
        fam_event = _make_event("evt_fam", ["person_1", "person_2"])
        shared_event = _make_event("evt_shared", ["person_1", "person_3"])
        unrelated = _make_event("evt_other", ["person_4"])

        fam = _make_family("fam_1", event_ids=["evt_fam"])
        project = _make_project(
            events=[excl_event, fam_event, shared_event, unrelated],
            families=[fam],
        )

        exclusive, family, shared = classify_events("person_1", project)

        assert exclusive == [excl_event]
        assert family == [fam_event]
        assert shared == [shared_event]


class TestFindAffectedFamilies:
    """Tests for find_affected_families."""

    def test_person_as_partner(self) -> None:
        """Family where person is a partner is affected."""
        fam = _make_family("fam_1", partner_ids=["person_1", "person_2"])
        project = _make_project(families=[fam])

        result = find_affected_families("person_1", project)

        assert result == [fam]

    def test_person_as_child(self) -> None:
        """Family where person is in the children list is affected."""
        fam = _make_family("fam_1", partner_ids=["person_2"], children=["person_1"])
        project = _make_project(families=[fam])

        result = find_affected_families("person_1", project)

        assert result == [fam]

    def test_person_in_parent_child_link_as_child(self) -> None:
        """Family where person appears in a ParentChildLink as child is affected."""
        link = ParentChildLink(child_id="person_1", parent_id="person_2", parentage_type="biological")
        fam = _make_family("fam_1", partner_ids=["person_2"], parent_child_links=[link])
        project = _make_project(families=[fam])

        result = find_affected_families("person_1", project)

        assert result == [fam]

    def test_person_in_parent_child_link_as_parent(self) -> None:
        """Family where person appears in a ParentChildLink as parent is affected."""
        link = ParentChildLink(child_id="person_3", parent_id="person_1", parentage_type="biological")
        fam = _make_family("fam_1", partner_ids=["person_2"], children=["person_3"], parent_child_links=[link])
        project = _make_project(families=[fam])

        result = find_affected_families("person_1", project)

        assert result == [fam]

    def test_unrelated_family_not_returned(self) -> None:
        """Family that doesn't reference the person is not affected."""
        fam = _make_family("fam_1", partner_ids=["person_2", "person_3"], children=["person_4"])
        project = _make_project(families=[fam])

        result = find_affected_families("person_1", project)

        assert result == []

    def test_person_in_multiple_families(self) -> None:
        """Person appearing in multiple families returns all of them."""
        fam1 = _make_family("fam_1", partner_ids=["person_1", "person_2"])
        fam2 = _make_family("fam_2", partner_ids=["person_3"], children=["person_1"])
        fam3 = _make_family("fam_3", partner_ids=["person_4", "person_5"])
        project = _make_project(families=[fam1, fam2, fam3])

        result = find_affected_families("person_1", project)

        assert fam1 in result
        assert fam2 in result
        assert fam3 not in result
        assert len(result) == 2

    def test_no_duplicate_when_person_is_partner_and_in_link(self) -> None:
        """Family is only returned once even if person appears in multiple roles."""
        link = ParentChildLink(child_id="person_3", parent_id="person_1", parentage_type="biological")
        fam = _make_family(
            "fam_1",
            partner_ids=["person_1", "person_2"],
            children=["person_3"],
            parent_child_links=[link],
        )
        project = _make_project(families=[fam])

        result = find_affected_families("person_1", project)

        assert result == [fam]


# ============================================================================
# DeleteService unit tests
# ============================================================================


def _make_project_service(project_data: ProjectData) -> ProjectService:
    """Create a ProjectService with pre-set project data for testing."""
    ps = ProjectService()
    ps._project_data = project_data
    ps._dirty = False
    return ps


class TestDeleteServiceCancel:
    """Validates: Requirements 1.3, 6.6 - cancel preserves state."""

    def test_cancel_preserves_state(self) -> None:
        """Computing consequences without executing deletion leaves data unchanged."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])
        other = Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Johansson")])
        project_data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="p2"),
            persons=[person, other],
        )
        ps = _make_project_service(project_data)
        service = DeleteService(ps)

        # Simulate user opening delete dialog: compute consequences
        consequences = service.compute_consequences("p1")

        # User cancels - no execute_deletion called
        # Verify data is unchanged
        assert len(ps.data.persons) == 2
        assert ps.data.persons[0].id == "p1"
        assert ps.data.persons[1].id == "p2"
        assert ps._dirty is False


class TestDeleteServiceMainPerson:
    """Validates: Requirement 1.4 - main person error message."""

    def test_main_person_error_message(self) -> None:
        """can_delete returns (False, Swedish error) for main person."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])
        project_data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="p1"),
            persons=[person],
        )
        ps = _make_project_service(project_data)
        service = DeleteService(ps)

        allowed, message = service.can_delete("p1")

        assert allowed is False
        assert message == "Huvudpersonen kan inte tas bort."


class TestDeleteServiceDirtyFlag:
    """Validates: Requirement 8.5 - dirty flag set after deletion."""

    def test_dirty_flag_set_after_deletion(self) -> None:
        """execute_deletion sets the project dirty flag to True."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])
        other = Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Johansson")])
        project_data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="p2"),
            persons=[person, other],
        )
        ps = _make_project_service(project_data)
        assert ps._dirty is False

        service = DeleteService(ps)
        service.execute_deletion("p1")

        assert ps._dirty is True


class TestDeleteServiceConnectivitySkip:
    """Validates: Requirements 7.5, 7.6 - connectivity check skip conditions."""

    def test_connectivity_check_skipped_no_main_person(self) -> None:
        """When no main_person_id is set, would_disconnect is False and count is 0."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])
        other = Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Johansson")])
        project_data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id=None),
            persons=[person, other],
        )
        ps = _make_project_service(project_data)
        service = DeleteService(ps)

        consequences = service.compute_consequences("p1")

        assert consequences.would_disconnect is False
        assert consequences.disconnected_person_count == 0

    def test_connectivity_check_skipped_for_main_person_target(self) -> None:
        """When target equals main_person_id, would_disconnect is False and count is 0.

        Note: In practice can_delete blocks this, but compute_consequences
        still handles it gracefully via compute_disconnection's skip condition.
        """
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])
        other = Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Johansson")])
        project_data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="p1"),
            persons=[person, other],
        )
        ps = _make_project_service(project_data)
        service = DeleteService(ps)

        consequences = service.compute_consequences("p1")

        assert consequences.would_disconnect is False
        assert consequences.disconnected_person_count == 0


# ============================================================================
# build_warning_lines unit tests
# ============================================================================

from slaktbusken.model.event import DateValue
from slaktbusken.ui.dialogs.delete_person_dialog import build_warning_lines


def _make_consequences(
    person_name: str = "Erik Svensson",
    exclusive_events: list[Event] | None = None,
    family_events: list[Event] | None = None,
    non_family_shared_events: list[Event] | None = None,
    affected_families: list[Family] | None = None,
    would_disconnect: bool = False,
    disconnected_person_count: int = 0,
) -> DeletionConsequences:
    """Create a DeletionConsequences for testing build_warning_lines."""
    return DeletionConsequences(
        person_name=person_name,
        exclusive_events=exclusive_events or [],
        family_events=family_events or [],
        non_family_shared_events=non_family_shared_events or [],
        affected_families=affected_families or [],
        would_disconnect=would_disconnect,
        disconnected_person_count=disconnected_person_count,
    )


class TestBuildWarningLines:
    """Tests for build_warning_lines pure function.

    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
    """

    def test_generic_confirmation_no_shared_events(self) -> None:
        """With no family or shared events, shows generic confirmation."""
        consequences = _make_consequences()

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Erik Svensson" in text
        assert "inga delade händelser" in text

    def test_family_events_listed_with_date(self) -> None:
        """Family events show type and date value."""
        event = Event(
            id="e1",
            type="marriage",
            participants=[],
            date=DateValue(value="1920-06-15", precision="exact"),
        )
        consequences = _make_consequences(family_events=[event])

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Vigsel" in text
        assert "1920-06-15" in text

    def test_family_events_listed_without_date(self) -> None:
        """Family events without date show 'inget datum'."""
        event = Event(id="e1", type="marriage", participants=[], date=None)
        consequences = _make_consequences(family_events=[event])

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Vigsel" in text
        assert "inget datum" in text

    def test_shared_events_listed(self) -> None:
        """Shared events show type and date."""
        event = Event(
            id="e1",
            type="census",
            participants=[],
            date=DateValue(value="1890", precision="year"),
        )
        consequences = _make_consequences(non_family_shared_events=[event])

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Folkräkning" in text
        assert "1890" in text

    def test_shared_event_without_date_shows_inget_datum(self) -> None:
        """Shared events without date show 'inget datum'."""
        event = Event(id="e1", type="birth", participants=[], date=None)
        consequences = _make_consequences(non_family_shared_events=[event])

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Födelse" in text
        assert "inget datum" in text

    def test_cap_at_max_events(self) -> None:
        """When more than max_events, shows overflow indicator."""
        events = [
            Event(id=f"e{i}", type="census", participants=[], date=None)
            for i in range(15)
        ]
        consequences = _make_consequences(family_events=events)

        lines = build_warning_lines(consequences, max_events=10)

        text = "\n".join(lines)
        # Should show overflow message with count of remaining
        assert "...och 5 till" in text
        # At most 10 event bullet lines
        bullet_lines = [line for line in lines if line.startswith("  • ")]
        assert len(bullet_lines) <= 10

    def test_cap_across_both_categories(self) -> None:
        """max_events applies across family + shared events combined."""
        family_events = [
            Event(id=f"fe{i}", type="marriage", participants=[], date=None)
            for i in range(7)
        ]
        shared_events = [
            Event(id=f"se{i}", type="census", participants=[], date=None)
            for i in range(6)
        ]
        consequences = _make_consequences(
            family_events=family_events,
            non_family_shared_events=shared_events,
        )

        lines = build_warning_lines(consequences, max_events=10)

        text = "\n".join(lines)
        # 13 total events, cap at 10, overflow = 3
        assert "...och 3 till" in text

    def test_person_name_displayed(self) -> None:
        """Person name appears in the warning text."""
        consequences = _make_consequences(person_name="Anna Johansson")

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Anna Johansson" in text

    def test_disconnection_warning(self) -> None:
        """When would_disconnect is True, shows disconnection warning."""
        consequences = _make_consequences(
            would_disconnect=True,
            disconnected_person_count=5,
        )

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "5 personer" in text
        assert "koppla bort" in text

    def test_no_disconnection_warning_when_false(self) -> None:
        """When would_disconnect is False, no disconnection warning."""
        consequences = _make_consequences(would_disconnect=False)

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "koppla bort" not in text

    def test_exclusive_events_summary(self) -> None:
        """Exclusive events count is shown as summary."""
        events = [_make_event(f"e{i}", ["p1"]) for i in range(3)]
        consequences = _make_consequences(exclusive_events=events)

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "3 händelser" in text

    def test_affected_families_summary(self) -> None:
        """Affected families count is shown."""
        families = [_make_family(f"f{i}", partner_ids=["p1", "p2"]) for i in range(2)]
        consequences = _make_consequences(affected_families=families)

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "2 familjeassociationer" in text

    def test_custom_type_name_used(self) -> None:
        """Events with custom_type_name use that instead of type translation."""
        event = Event(
            id="e1",
            type="custom",
            participants=[],
            date=None,
            custom_type_name="Husförhör",
        )
        consequences = _make_consequences(family_events=[event])

        lines = build_warning_lines(consequences)

        text = "\n".join(lines)
        assert "Husförhör" in text
