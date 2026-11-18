"""Tests for the "has source" list icon and the residence-aware usage dialog."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QHelpEvent, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyleOptionViewItem,
)

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.ui.dialogs.usage_detail_dialog import (
    UsageDetailDialog,
    build_residence_groups,
    build_usage_groups,
)
from slaktbusken.ui.editors.person_editor import EventListMapIconDelegate, PersonEditor
from slaktbusken.ui.icons.icon_registry import icon_registry
from slaktbusken.ui.widgets.boenden_tab import BoendenTab
from slaktbusken.ui.widgets.list_icon_delegate import (
    HAS_COORDS_ROLE,
    HAS_SOURCE_ROLE,
    SOURCE_TITLES_ROLE,
    ListIconDelegate,
    sources_tooltip,
)
from slaktbusken.ui.widgets.research_marker import MARKER_COLOR_ROLE

DOT = "#E67E22"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _data() -> ProjectData:
    return ProjectData(
        project=ProjectMetadata(title="T"),
        persons=[
            Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="A")]),
            Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="B")]),
        ],
        sources=[
            Source(id="s1", provider="x", source_type="church_book", title="Husförhör"),
            Source(id="s2", provider="x", source_type="church_book", title="Dödbok"),
        ],
        places=[Place(id="pl1", type="parish", name="Ljusdal", latitude=61.8, longitude=16.1)],
        events=[
            Event(
                id="e1",
                type="birth",
                participants=[Participant(person_id="p1", role="child")],
                date=DateValue(
                    value="1889-12-17",
                    precision="exact",
                    source_refs=[SourceRef(source_id="s1", quality="high")],
                ),
                place=PlaceRef(place_id="pl1", source_refs=[SourceRef(source_id="s2", quality="high")]),
            ),
            Event(
                id="e2",
                type="death",
                participants=[Participant(person_id="p1", role="deceased")],
                date=DateValue(value="1950", precision="year"),
            ),
        ],
        residences=[
            ResidenceFact(
                id="r1",
                person_id="p1",
                place_id="pl1",
                start=Endpoint(earliest="1880"),
                end=Endpoint(earliest="1890"),
                observations=[Observation(source_ref=SourceRef(source_id="s1", quality="high"))],
            ),
            ResidenceFact(id="r2", person_id="p1", place_id="pl1"),
            ResidenceFact(
                id="r3",
                person_id="p2",
                place_id="pl1",
                observations=[Observation(source_ref=SourceRef(source_id="s1", quality="high"))],
            ),
        ],
    )


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------


def test_events_list_source_data(qapp):
    data = _data()
    editor = PersonEditor(data, data.persons[0])
    lst = editor._ui.events_list
    by_id = {
        lst.item(i).data(Qt.ItemDataRole.UserRole): lst.item(i) for i in range(lst.count())
    }
    assert by_id["e1"].data(HAS_SOURCE_ROLE) is True
    assert by_id["e1"].data(SOURCE_TITLES_ROLE) == ["Husförhör", "Dödbok"]
    assert by_id["e2"].data(HAS_SOURCE_ROLE) is None
    assert by_id["e2"].data(SOURCE_TITLES_ROLE) is None
    assert isinstance(lst.itemDelegate(), EventListMapIconDelegate)


def test_boenden_list_source_data(qapp):
    data = _data()
    tab = BoendenTab(data, data.persons[0])
    lst = tab.residence_list
    by_id = {
        lst.item(i).data(Qt.ItemDataRole.UserRole): lst.item(i) for i in range(lst.count())
    }
    assert by_id["r1"].data(HAS_SOURCE_ROLE) is True
    assert by_id["r1"].data(SOURCE_TITLES_ROLE) == ["Husförhör"]
    assert by_id["r2"].data(HAS_SOURCE_ROLE) is None
    assert isinstance(lst.itemDelegate(), ListIconDelegate)


def _option(view: QListWidget, item: QListWidgetItem) -> QStyleOptionViewItem:
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 500, 24)
    opt.widget = view
    opt.font = view.font()
    opt.fontMetrics = view.fontMetrics()
    opt.decorationSize = view.iconSize()
    return opt


def _render(view: QListWidget, item: QListWidgetItem):
    delegate = view.itemDelegate()
    index = view.indexFromItem(item)
    opt = _option(view, item)
    image = QImage(500, 24, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    delegate.paint(painter, opt, index)
    painter.end()
    return image, delegate, index, opt


def _has_ink(image: QImage, rect: QRect, colour: QColor | None = None) -> bool:
    for x in range(rect.left(), rect.right() + 1):
        for y in range(rect.top(), rect.bottom() + 1):
            px = QColor(image.pixel(x, y))
            if colour is None:
                if px != QColor("white"):
                    return True
            elif abs(px.red() - colour.red()) < 40 and abs(px.green() - colour.green()) < 40:
                return True
    return False


@pytest.mark.parametrize("pin", [False, True])
@pytest.mark.parametrize("source", [False, True])
@pytest.mark.parametrize("decorated", [False, True])
def test_delegate_paints_icons_in_order(qapp, pin, source, decorated):
    view = QListWidget()
    view.setItemDelegate(ListIconDelegate(view))
    item = QListWidgetItem("Födelse — 1889 — Ljusdal")
    if decorated:
        item.setIcon(icon_registry.get_event_icon("birth"))
    if pin:
        item.setData(HAS_COORDS_ROLE, True)
    if source:
        item.setData(HAS_SOURCE_ROLE, True)
        item.setData(SOURCE_TITLES_ROLE, ["A"])
    item.setData(MARKER_COLOR_ROLE, DOT)
    view.addItem(item)

    image, delegate, index, opt = _render(view, item)
    pin_rect, source_rect, used = delegate.icon_rects(opt, index)

    assert (pin_rect is not None) == pin
    assert (source_rect is not None) == source
    if pin:
        assert _has_ink(image, pin_rect)
    if source:
        assert _has_ink(image, source_rect)
    if pin and source:
        assert source_rect.left() > pin_rect.right()
    assert used == (22 if pin else 0) + (22 if source else 0)

    # The research dot (orange) is drawn after the last icon.
    last = source_rect or pin_rect
    dot_area = QRect((last.right() + 1) if last else 0, 0, 500, 24)
    if last is None:
        text_end = opt.fontMetrics.horizontalAdvance(item.text()) + (20 if decorated else 0)
        dot_area = QRect(text_end + 4, 0, 40, 24)
    assert _has_ink(image, dot_area, QColor(DOT))
    if last is not None:
        assert not _has_ink(image, QRect(last.left(), 0, last.width(), 24), QColor(DOT))


def test_no_source_means_no_source_rect(qapp):
    view = QListWidget()
    view.setItemDelegate(ListIconDelegate(view))
    item = QListWidgetItem("Boende")
    view.addItem(item)
    _image, delegate, index, opt = _render(view, item)
    assert delegate.icon_rects(opt, index) == (None, None, 0)


def test_sources_tooltip_text_and_cap():
    assert sources_tooltip(["A", "B"]) == "Källor:\n• A\n• B"
    text = sources_tooltip([f"S{i}" for i in range(13)])
    assert text.splitlines()[-1] == "… och 3 till"
    assert len(text.splitlines()) == 12


def test_help_event_shows_tooltip_only_over_source_icon(qapp, monkeypatch):
    shown: list[str] = []
    monkeypatch.setattr(
        "slaktbusken.ui.widgets.list_icon_delegate.QToolTip.showText",
        lambda pos, text, *a: shown.append(text),
    )
    view = QListWidget()
    view.setItemDelegate(ListIconDelegate(view))
    item = QListWidgetItem("Födelse")
    item.setToolTip("Radtips")
    item.setData(HAS_SOURCE_ROLE, True)
    item.setData(SOURCE_TITLES_ROLE, ["Husförhör", "Dödbok"])
    view.addItem(item)
    delegate = view.itemDelegate()
    index = view.indexFromItem(item)
    opt = _option(view, item)
    _pin, rect, _ = delegate.icon_rects(opt, index)

    over = QHelpEvent(QEvent.Type.ToolTip, rect.center(), QPoint(10, 10))
    assert delegate.helpEvent(over, view, opt, index) is True
    assert shown and "Husförhör" in shown[0] and "Dödbok" in shown[0]

    shown.clear()
    elsewhere = QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), QPoint(10, 10))
    delegate.helpEvent(elsewhere, view, opt, index)
    assert not any("Husförhör" in s for s in shown)


def test_source_icon_is_cached_and_14px(qapp):
    pix = icon_registry.get_source_icon()
    assert (pix.width(), pix.height()) == (14, 14)
    assert icon_registry.get_source_icon() is pix


def test_source_icon_not_clickable(qapp):
    # The delegate defines no editor/click handling of its own.
    assert not hasattr(ListIconDelegate, "editorEvent") or (
        ListIconDelegate.editorEvent is ListIconDelegate.__mro__[1].editorEvent
    )
    assert not hasattr(ListIconDelegate, "clicked")


# --------------------------------------------------------------------------
# Usage dialog
# --------------------------------------------------------------------------


def _labels(dialog: UsageDetailDialog, name: str) -> list[str]:
    return [w.text() for w in dialog.findChildren(QLabel, name)]


def test_dialog_lists_events_and_residences(qapp):
    data = _data()
    dialog = UsageDetailDialog(
        None, data.sources[0], data.events, data.persons, data.residences, data.places
    )
    assert any("Födelse (1889-12-17)" in t for t in _labels(dialog, "event_item"))
    assert sorted(_labels(dialog, "residence_item")) == [
        "  • Boende: Ljusdal",
        "  • Boende: Ljusdal (från 1880 till 1890)",
    ]
    headers = _labels(dialog, "person_header")
    assert len(headers) == 2  # Anna only via residence
    assert any("Anna" in h for h in headers)
    assert "Totalt: 2 personer, 1 händelse, 2 boenden" in _labels(dialog, "usage_summary")[0]


def test_dialog_residence_only_summary(qapp):
    data = _data()
    dialog = UsageDetailDialog(None, data.sources[0], [], data.persons, data.residences, data.places)
    assert "Totalt: 2 personer, 2 boenden" in _labels(dialog, "usage_summary")[0]
    single = UsageDetailDialog(None, data.sources[0], [], data.persons, data.residences[2:], data.places)
    assert "Totalt: 1 person, 1 boende" in _labels(single, "usage_summary")[0]
    assert "händelse" not in _labels(single, "usage_summary")[0]


def test_dialog_empty_message(qapp):
    data = _data()
    dialog = UsageDetailDialog(None, data.sources[1], [], data.persons)
    assert _labels(dialog, "no_usage") == [
        "Inga händelser eller boenden refererar till denna källa."
    ]


def test_dialog_backward_compatible_events_only(qapp):
    data = _data()
    dialog = UsageDetailDialog(None, data.sources[0], data.events, data.persons)
    assert "Totalt: 1 person, 1 händelse" in _labels(dialog, "usage_summary")[0]
    assert _labels(dialog, "residence_item") == []


def test_build_groups(qapp):
    data = _data()
    assert list(build_usage_groups("s1", data.events, data.persons)) == ["p1"]
    groups = build_residence_groups("s1", data.residences)
    assert {k: [f.id for f in v] for k, v in groups.items()} == {"p1": ["r1"], "p2": ["r3"]}
