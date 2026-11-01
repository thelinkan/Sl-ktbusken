"""Planning steps for person attributes, names, events and residences.

Qt-free. The steps are registered through :func:`merge_planner.plan_step` and
fill the slots ``attributes``, ``names``, ``events`` and ``residences``
(Requirements 21.1 to 21.17, design sections 10.5 to 10.8).

``merge_planner`` imports this module at its end, so the steps are registered
whenever the planner is imported. Steps only read ``ctx.data`` and edit clones
through ``ctx.work``; user-facing problems become conflicts or unresolved
choices, never exceptions.
"""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.event import Event
from slaktbusken.model.person import Person
from slaktbusken.services import merge_rules as rules
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.merge_planner import (
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
    Disposition,
    PlanContext,
    plan_step,
)

MISSING_NAME = "(namn saknas)"
BOTH_PARTICIPANTS_MESSAGE = "Händelsen hade båda personerna som deltagare"

_EVENT_LABELS = {
    "adoption": "Adoption", "adoption_ended": "Adoption upphörde",
    "foster_home": "Fosterhem", "foster_home_ended": "Fosterhem upphörde",
    "baptism": "Dop", "birth": "Födelse", "blessing": "Välsignelse",
    "burial": "Begravning", "census": "Folkräkning", "confirmation": "Konfirmation",
    "cremation": "Kremering", "death": "Död", "emigration": "Emigration",
    "first_communion": "Första nattvarden", "flytt": "Flytt",
    "gender_correction": "Könskorrigering", "graduation": "Examen",
    "immigration": "Immigration", "name_change": "Namnbyte", "retirement": "Pension",
    "will": "Testamente", "divorce": "Skilsmässa", "divorce_filed": "Skilsmässoansökan",
    "engagement": "Förlovning", "marriage": "Vigsel",
    "custom_individual_event": "Anpassad individuell händelse",
    "custom_family_event": "Anpassad familjehändelse",
}
_FAMILY_EVENT_TYPES = frozenset(
    {"divorce", "divorce_filed", "engagement", "marriage", "custom_family_event"}
)


def _persons(ctx: PlanContext) -> tuple[Person, Person]:
    by_id = {p.id: p for p in ctx.data.persons}
    return by_id[ctx.survivor_id], by_id[ctx.retired_id]


def _display_name(person: Person) -> str:
    if person.names:
        n = person.names[0]
        text = f"{n.given} {n.surname}".strip()
        if text:
            return text
    return MISSING_NAME


def _event_label(event: Event) -> str:
    if event.custom_type_name:
        return event.custom_type_name
    return _EVENT_LABELS.get(event.type, event.type)


def _event_text(event: Event) -> str:
    date = event.date.value if event.date is not None else ""
    return f"{_event_label(event)} {date}".strip()


# ---------------------------------------------------------------------------
# Attributes (21.2 to 21.7)
# ---------------------------------------------------------------------------


def _plan_single(
    ctx: PlanContext,
    *,
    key: str,
    label: str,
    survivor_value: Optional[str],
    other_value: Optional[str],
    chosen: Optional[str],
    chosen_is_value: bool,
) -> tuple[bool, Optional[str]]:
    """Plan one single-valued field. Returns ``(changed, new_value)``.

    *chosen* is a person id (title, occupation) or the value itself
    (``chosen_is_value``, profile media id).
    """
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    res = rules.resolve_single_value(survivor_value, other_value)
    if res.status == rules.SINGLE_VALUE_BOTH_EMPTY:
        ctx.add_item("attributes", key, label, Disposition.PRESERVED, "Båda saknar värde")
        return False, survivor_value
    if res.status == rules.SINGLE_VALUE_EQUAL:
        ctx.add_item("attributes", key, label, Disposition.COMBINED, "Lika värden, ett behålls")
        return False, survivor_value
    if res.status == rules.SINGLE_VALUE_ONE:
        if rules.is_blank(survivor_value):
            ctx.add_item("attributes", key, label, Disposition.REASSIGNED,
                         "Värdet tas från den andra personen")
            return True, other_value
        ctx.add_item("attributes", key, label, Disposition.PRESERVED, "Värdet behålls")
        return False, survivor_value
    # conflict
    if chosen_is_value:
        take_survivor = chosen is not None and chosen.strip() == (survivor_value or "").strip()
        take_other = chosen is not None and chosen.strip() == (other_value or "").strip()
    else:
        take_survivor = chosen == s_id
        take_other = chosen == r_id
    if take_survivor:
        ctx.add_item("attributes", key, label, Disposition.EXCLUDED,
                     "Den andra personens värde utesluts efter val")
        return False, survivor_value
    if take_other:
        ctx.add_item("attributes", key, label, Disposition.REASSIGNED,
                     "Den andra personens värde väljs")
        return True, other_value
    ctx.add_item("attributes", key, label, Disposition.FLAGGED, "Val krävs")
    ctx.add_unresolved(key, "attributes", f"Välj {label.lower()}.", (s_id, r_id))
    return False, survivor_value


@plan_step("attributes")
def plan_attributes(ctx: PlanContext) -> None:
    survivor, retired = _persons(ctx)
    d = ctx.decisions
    clone: Person = ctx.work.edit("persons", ctx.survivor_id)

    # sex
    res = rules.resolve_sex(survivor.sex, retired.sex)
    if res.status == rules.SINGLE_VALUE_CONFLICT:
        known = {survivor.sex.strip(), retired.sex.strip()}
        if d.sex is not None and d.sex.strip() in known:
            clone.sex = d.sex.strip()
            disp = (
                Disposition.EXCLUDED
                if clone.sex == survivor.sex.strip() else Disposition.REASSIGNED
            )
            ctx.add_item("attributes", "sex", "Kön", disp, "Valt av användaren")
        else:
            ctx.add_item("attributes", "sex", "Kön", Disposition.FLAGGED, "Val krävs")
            ctx.add_conflict(
                SEVERITY_BLOCKING, "sex_conflict", "attributes",
                f"Personerna har olika kön ({survivor.sex} och {retired.sex}). Välj ett.",
                (survivor.id, retired.id),
            )
            ctx.add_unresolved("sex", "attributes", "Välj kön.", sorted(known))
    elif res.status == rules.SINGLE_VALUE_EQUAL:
        ctx.add_item("attributes", "sex", "Kön", Disposition.COMBINED, "Lika värden, ett behålls")
    elif res.status == rules.SINGLE_VALUE_ONE:
        if res.value != survivor.sex:
            clone.sex = res.value  # type: ignore[assignment]
            ctx.add_item("attributes", "sex", "Kön", Disposition.REASSIGNED,
                         "Det kända könet tas från den andra personen")
        else:
            ctx.add_item("attributes", "sex", "Kön", Disposition.PRESERVED, "Värdet behålls")
    else:
        ctx.add_item("attributes", "sex", "Kön", Disposition.PRESERVED, "Inget känt kön")

    changed, value = _plan_single(
        ctx, key="title", label="Titel", survivor_value=survivor.title,
        other_value=retired.title, chosen=d.title_from, chosen_is_value=False,
    )
    if changed:
        clone.title = value
    changed, value = _plan_single(
        ctx, key="occupation", label="Yrke", survivor_value=survivor.occupation,
        other_value=retired.occupation, chosen=d.occupation_from, chosen_is_value=False,
    )
    if changed:
        clone.occupation = value
    changed, value = _plan_single(
        ctx, key="profile_media_id", label="Profilbild",
        survivor_value=survivor.profile_media_id, other_value=retired.profile_media_id,
        chosen=d.profile_media_id, chosen_is_value=True,
    )
    if changed:
        clone.profile_media_id = value

    # notes
    s_empty, o_empty = rules.is_blank(survivor.notes), rules.is_blank(retired.notes)
    mode = d.notes_mode if d.notes_mode in (
        rules.NOTES_KEEP_SURVIVOR, rules.NOTES_KEEP_OTHER, rules.NOTES_CONCATENATE
    ) else rules.NOTES_CONCATENATE
    new_notes = rules.resolve_notes(
        survivor.notes, retired.notes, _display_name(retired), retired.id, mode
    )
    clone.notes = new_notes
    if s_empty and o_empty:
        ctx.add_item("attributes", "notes", "Anteckningar", Disposition.PRESERVED, "Inga anteckningar")
    elif o_empty:
        ctx.add_item("attributes", "notes", "Anteckningar", Disposition.PRESERVED, "Anteckningarna behålls")
    elif s_empty:
        ctx.add_item("attributes", "notes", "Anteckningar", Disposition.REASSIGNED,
                     "Anteckningarna tas från den andra personen")
    elif survivor.notes.strip() == retired.notes.strip():
        ctx.add_item("attributes", "notes", "Anteckningar", Disposition.COMBINED,
                     "Lika anteckningar, en behålls")
    elif mode == rules.NOTES_CONCATENATE:
        ctx.add_item("attributes", "notes", "Anteckningar", Disposition.COMBINED,
                     "Anteckningarna slås ihop med en synlig avskiljare")
    else:
        ctx.add_item("attributes", "notes", "Anteckningar", Disposition.EXCLUDED,
                     "Den ena personens anteckningar utesluts efter val")


# ---------------------------------------------------------------------------
# Names (21.8 to 21.10)
# ---------------------------------------------------------------------------


def _name_label(name) -> str:
    return f"{name.given} {name.surname}".strip() + f" ({name.type})"


@plan_step("names")
def plan_names(ctx: PlanContext) -> None:
    survivor, retired = _persons(ctx)
    clone: Person = ctx.work.edit("persons", ctx.survivor_id)

    seen: set[tuple] = set()
    for owner, own in ((survivor, True), (retired, False)):
        for index, name in enumerate(owner.names):
            identity = rules.name_identity(name)
            if identity in seen:
                disp, detail = Disposition.COMBINED, "Identiskt namn, ett behålls"
            elif own:
                disp, detail = Disposition.PRESERVED, "Namnet behålls"
            else:
                disp, detail = Disposition.REASSIGNED, "Namnet läggs till som alternativt namn"
            seen.add(identity)
            ctx.add_item("names", f"{owner.id}:{index}", _name_label(name), disp, detail)

    # The primary-name choice is applied only when it names a listed entry.
    wanted = ctx.decisions.primary_name
    unordered = rules.union_names(survivor.names, retired.names)
    valid = wanted is not None and any(rules.name_identity(n) == tuple(wanted) for n in unordered)
    merged = rules.union_names(survivor.names, retired.names, tuple(wanted) if valid else None)
    clone.names = merged

    duplicates = len(survivor.names) + len(retired.names) - len(merged)
    if duplicates:
        ctx.note_dedup("names", duplicates)
    if len(merged) > 1 and not valid:
        ctx.add_unresolved(
            "primary_name", "names", "Välj ett förstahandsnamn.",
            tuple(_name_label(n) for n in merged),
        )


# ---------------------------------------------------------------------------
# Events (21.11 to 21.15)
# ---------------------------------------------------------------------------


@plan_step("events")
def plan_events(ctx: PlanContext) -> None:
    s_id, r_id = ctx.survivor_id, ctx.retired_id
    first, second = ctx.decisions.first_person_id, ctx.decisions.second_person_id
    by_id = {e.id: e for e in ctx.data.events}

    def has(event: Event, pid: str) -> bool:
        return any(p.person_id == pid for p in event.participants)

    for event in ctx.data.events:
        if not (has(event, s_id) or has(event, r_id)):
            continue
        label = _event_text(event)
        if not has(event, r_id):
            ctx.add_item("events", event.id, label, Disposition.PRESERVED, "Händelsen bevaras")
            continue
        chosen = ctx.decisions.participant_roles.get(event.id)
        rw = rules.rewrite_participants(event.participants, r_id, s_id, chosen)
        clone: Event = ctx.work.edit("events", event.id)
        clone.participants = rw.participants
        if rw.has_conflict:
            ctx.add_item("events", event.id, label, Disposition.FLAGGED, "Val av roll krävs")
            ctx.add_conflict(
                SEVERITY_BLOCKING, "participant_role", "events",
                f"Personerna har olika roller i händelsen {label}: "
                f"{', '.join(rw.conflicting_roles)}. Välj en roll.",
                (event.id, s_id, r_id),
            )
            ctx.add_unresolved(
                f"participant_role:{event.id}", "events",
                f"Välj roll i händelsen {label}.", rw.conflicting_roles,
            )
        elif rw.removed:
            ctx.add_item("events", event.id, label, Disposition.COMBINED,
                         "Deltagarposten slås ihop till en")
        else:
            ctx.add_item("events", event.id, label, Disposition.REASSIGNED,
                         "Deltagaren flyttas till behållen person")
        if rw.removed:
            ctx.note_dedup("participants", rw.removed)
        if has(event, s_id) and event.type in _FAMILY_EVENT_TYPES:
            ctx.add_conflict(
                SEVERITY_WARNING, "both_participants", "events",
                f"{BOTH_PARTICIPANTS_MESSAGE}: {label}", (event.id,),
            )

    # Similar_Event_Rule: only pairs from different records, nothing is merged.
    events_1 = [e for e in ctx.data.events if has(e, first)]
    events_2 = [e for e in ctx.data.events if has(e, second)]
    for id_1, id_2 in rules.find_similar_event_pairs(events_1, events_2):
        ctx.add_conflict(
            SEVERITY_WARNING, "similar_event", "events",
            f"Händelserna kan vara dubbletter: {_event_text(by_id[id_1])} "
            f"och {_event_text(by_id[id_2])}",
            (id_1, id_2),
        )


# ---------------------------------------------------------------------------
# Residences (21.16)
# ---------------------------------------------------------------------------


@plan_step("residences")
def plan_residences(ctx: PlanContext) -> None:
    for fact in ctx.data.residences:
        label = f"Boende {fact.id}"
        if fact.person_id == ctx.retired_id:
            ctx.work.edit("residences", fact.id).person_id = ctx.survivor_id
            ctx.add_item("residences", fact.id, label, Disposition.REASSIGNED,
                         "Flyttas till behållen person")
        elif fact.person_id == ctx.survivor_id:
            ctx.add_item("residences", fact.id, label, Disposition.PRESERVED, "Bevaras")


# ---------------------------------------------------------------------------
# Handler registration (inventory rows this module applies)
# ---------------------------------------------------------------------------

_HANDLERS = {
    "person.sex": plan_attributes,
    "person.title_occupation": plan_attributes,
    "person.notes": plan_attributes,
    "person.names": plan_names,
    "event.participants": plan_events,
    "residence.person": plan_residences,
}

for _key, _func in _HANDLERS.items():
    pri.register_handler(_key, _func)
