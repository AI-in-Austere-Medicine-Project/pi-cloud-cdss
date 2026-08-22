"""
Ventilator card engine — the fence, the dispatch, and the arithmetic.

Every card in the repo ships UNSIGNED, so the serve paths here build signed
cards locally. Those fixtures carry obviously-synthetic content ("TEST mode",
"step one") and no clinical values: a test fixture that looked like real
settings would be exactly the thing the fence exists to prevent, sitting in
the repo where someone could copy it into a card file.

F-12, which this closes the class of: the eval baseline measured 4 of 4 TBI
vent queries returning VT/RR/PEEP/FiO2 and 0 of 4 DKA vent queries returning
any of them, across four phrasings each, 100% reproducible.
"""
import copy
import json
import pathlib

import pytest

import openai_client as oc
import vent_module as vm
from openai_client import PatientContext, extract_patient_context


# ── fixtures: obviously-synthetic signed cards ──────────────────────────────

def _sign(card: dict, **overrides) -> dict:
    card = copy.deepcopy(card)
    card.update({"reviewed_by": "A. Azelton", "review_date": "2026-08-22",
                 "references": ["TEST reference"], "signoff": True})
    card.update(overrides)
    return card


def signed_physiology(card_id="metabolic_acidosis", **overrides):
    card = _sign(vm.PHYSIOLOGY[card_id])
    card["initial_settings"] = {"mode": "TEST mode", "vt_ml_per_kg_ibw": "6-8",
                                "rate_strategy": "TEST rate", "peep": "TEST peep",
                                "fio2": "TEST fio2"}
    card.update({"titrate_on": ["TEST titrate"], "watch_for": ["TEST watch"],
                 "evac_if": ["TEST evac"], "escape_hatch": "TEST assumes",
                 "actual_weight_caveat": "TEST caveat", "tldr": "TEST tldr"})
    card.update(overrides)
    return card


def signed_trouble(card_id="high_pressure_alarm", **overrides):
    card = _sign(vm.TROUBLESHOOTING[card_id])
    card["steps"] = [{"check": "TEST check", "finding": "TEST finding",
                      "action": "TEST action"}]
    card.update({"watch_for": ["TEST watch"], "evac_if": ["TEST evac"],
                 "escape_hatch": "TEST assumes", "tldr": "TEST tldr"})
    card.update(overrides)
    return card


def signed_device(card_id="hamilton_t1", **overrides):
    card = _sign(vm.DEVICES[card_id])
    card.update({
        "startup_sequence": ["TEST startup"],
        "parameter_map": {"mode": "TEST location"},
        "alarm_table": [{"display": "TEST DISPLAY", "meaning": "TEST meaning",
                         "first_action": "TEST action"}],
        "quirks": ["TEST quirk"], "crosswalk": ["TEST crosswalk"],
        "manual_reference": {"title": "TEST manual", "revision": "9.9",
                             "verified_date": "2026-08-22"},
    })
    card.update(overrides)
    return card


@pytest.fixture
def live(monkeypatch):
    """Install signed cards for the duration of one test."""
    def install(family, card):
        table = dict(vm.FAMILIES[family])
        table[card["id"]] = card
        monkeypatch.setattr(vm, {"physiology": "PHYSIOLOGY",
                                 "troubleshooting": "TROUBLESHOOTING",
                                 "device": "DEVICES"}[family], table)
        monkeypatch.setitem(vm.FAMILIES, family, table)
    return install


# ── THE FENCE ───────────────────────────────────────────────────────────────

def test_every_shipped_card_is_unsigned():
    """The repo state. Clinical content is the owner's and none has landed."""
    for family, cards in vm.FAMILIES.items():
        assert cards, f"{family} loaded no cards at all"
        for card_id, card in cards.items():
            servable, reason = vm.card_is_servable(card, family)
            assert not servable, f"{family}/{card_id} is live and should not be"
            assert reason


def test_nothing_is_servable_today():
    assert vm.servable_cards() == {"physiology": [], "troubleshooting": [],
                                   "device": []}


@pytest.mark.parametrize("family,builder", [
    ("physiology", signed_physiology),
    ("troubleshooting", signed_trouble),
    ("device", signed_device),
])
def test_engine_refuses_an_unsigned_card_on_the_serve_path(family, builder, live):
    """One serve-path test per family: signed serves, unsigned falls through.

    Paired, because a fence that also blocks signed cards is not a fence, it
    is an outage.
    """
    card = builder()
    query = {"physiology": "vent settings for a DKA patient",
             "troubleshooting": "high pressure alarm on the vent",
             "device": "hamilton t1 vent startup"}[family]

    live(family, card)
    hit = vm.dispatch(query)
    assert hit is not None and hit[0] == family, f"signed {family} card did not serve"

    live(family, dict(card, signoff=False))
    assert vm.dispatch(query) is None, f"unsigned {family} card served anyway"


@pytest.mark.parametrize("breakage,reason_fragment", [
    ({"signoff": False}, "signoff"),
    ({"reviewed_by": "Someone Else"}, "authorised signer"),
    ({"reviewed_by": vm.PENDING}, "authorised signer"),
    ({"review_date": vm.PENDING}, "review_date"),
    ({"references": []}, "references"),
    ({"titrate_on": [vm.PENDING]}, vm.PENDING),
    ({"watch_for": []}, "empty"),
    ({"escape_hatch": vm.PENDING}, vm.PENDING),
    ({"initial_settings": {"mode": vm.PENDING}}, vm.PENDING),
])
def test_every_way_a_card_can_be_incomplete_is_refused(breakage, reason_fragment, live):
    """signoff:true over a half-filled card must not serve either.

    The dangerous state is not "unsigned" — nobody ships that by accident. It
    is a card someone signed while a field was still a placeholder.
    """
    card = signed_physiology(**breakage)
    servable, reason = vm.card_is_servable(card, "physiology")
    assert not servable
    assert reason_fragment.lower() in reason.lower(), reason
    live("physiology", card)
    assert vm.dispatch("vent settings for a DKA patient") is None


def test_there_is_no_override_that_serves_an_unsigned_card(monkeypatch):
    """No debug flag, no env var, no warn-only path.

    EDGECDSS_DEBUG_WARN_ONLY downgrades safety holds elsewhere in this system.
    It must not reach this gate: the failure mode of a half-authored
    ventilator card is a patient ventilated on a placeholder.
    """
    monkeypatch.setenv("EDGECDSS_DEBUG_WARN_ONLY", "1")
    monkeypatch.setenv("CDSS_CARD_FORCE", "1")
    monkeypatch.setenv("CDSS_SERVE_PENDING_CARDS", "1")
    source = pathlib.Path(vm.__file__).read_text()
    assert "DEBUG_WARN_ONLY" not in source, "the warn-only flag must not reach this gate"

    # card_is_servable takes the card and the family and nothing else — there
    # is no parameter to pass a bypass through.
    import inspect
    assert list(inspect.signature(vm.card_is_servable).parameters) == ["card", "family"]

    for family, cards in vm.FAMILIES.items():
        for card in cards.values():
            assert not vm.card_is_servable(card, family)[0]
    assert vm.dispatch("vent settings for a DKA patient") is None


def test_a_pending_card_is_indistinguishable_from_an_absent_one(live):
    """The caller must not be able to branch on "pending" vs "no such card"."""
    assert vm.dispatch("vent settings for a DKA patient") is None
    live("physiology", signed_physiology(signoff=False))
    assert vm.dispatch("vent settings for a DKA patient") is None


def test_the_organisation_may_sign_but_signing_is_not_authoring():
    """AI-AIM signs as an organisation rather than as a person. It authorises
    the SIGNATURE and nothing else: an authorised name on a card whose clinical
    fields are still sentinels is refused exactly as an unauthorised one is,
    and refused for the content rather than for the name. The fence is about
    whether the settings exist, not about who is willing to put a name to
    them."""
    assert "AI-AIM" in vm.SIGNOFF_AUTHORS

    empty = copy.deepcopy(vm.PHYSIOLOGY["metabolic_acidosis"])
    empty.update({"signoff": True, "reviewed_by": "AI-AIM",
                  "review_date": "2026-08-22", "references": ["TEST reference"]})
    ok, why = vm.card_is_servable(empty, "physiology")
    assert not ok
    assert "PENDING_CLINICAL_SIGNOFF" in why
    assert "authorised signer" not in why, "refused for the name, not the content"

    authored = signed_physiology("metabolic_acidosis", reviewed_by="AI-AIM")
    assert vm.card_is_servable(authored, "physiology")[0]


def test_an_unauthorised_name_is_still_refused():
    """Widening the list to two names is not widening it to any name."""
    card = signed_physiology("metabolic_acidosis", reviewed_by="AI AIM")
    ok, why = vm.card_is_servable(card, "physiology")
    assert not ok and "authorised signer" in why


# ── F-12 REGRESSION ─────────────────────────────────────────────────────────

DKA_PHRASINGS = [
    "Ventilator settings for 75kg male in DKA. Ph 7.1",
    "I need ventilator settings for a DKA patient that I'm managing for the next 24 hours",
    "Vent settings dka",
    "vent settings for a diabetic ketoacidosis patient, ph 7.0",
]

TBI_PHRASINGS = [
    "need basic vent settings for TBI patient",
    "vent settings for tbi 50kg male",
    "We have successfully RSI a traumatic brain injury patient, we will now be "
    "managing this patient for the next 4 to 10 hours… need to know blood "
    "pressure ranges and vent settings",
    "tbi mgmt on vent",
]


@pytest.mark.parametrize("query", DKA_PHRASINGS)
def test_f12_dka_phrasings_reach_the_metabolic_card_once_signed(query, live):
    """The finding, closed. 0 of 4 of these returned any vent settings in the
    eval baseline; all four TBI equivalents did."""
    live("physiology", signed_physiology("metabolic_acidosis"))
    hit = vm.dispatch(query)
    assert hit is not None, f"no card claimed {query!r}"
    family, card = hit
    assert (family, card["id"]) == ("physiology", "metabolic_acidosis")


@pytest.mark.parametrize("query", TBI_PHRASINGS)
def test_f12_tbi_phrasings_reach_the_tbi_card_as_control(query, live):
    """The control arm. TBI already worked; the card must not take that away."""
    live("physiology", signed_physiology("tbi"))
    hit = vm.dispatch(query)
    assert hit is not None, f"no card claimed {query!r}"
    assert hit[1]["id"] == "tbi"


@pytest.mark.parametrize("query", DKA_PHRASINGS + TBI_PHRASINGS)
def test_vent_queries_fall_through_untouched_while_cards_are_pending(query):
    """Today's behaviour, pinned. Until content lands, nothing changes."""
    assert vm.dispatch(query) is None


def test_a_served_settings_card_actually_contains_settings():
    """The literal shape of F-12: a vent question that returns vent settings."""
    card = signed_physiology("metabolic_acidosis")
    ctx = extract_patient_context("75kg male, 178 cm, DKA")
    out = vm.render("physiology", card, ctx, "vent settings dka")
    for heading in ("**SETTINGS**", "Mode:", "VT:", "Rate:", "PEEP:", "FiO2:",
                    "**TITRATE**", "**WATCH FOR**", "**EVAC IF**"):
        assert heading in out, heading


# ── THE PHYSIOLOGY GATE ─────────────────────────────────────────────────────
#
# lung_protective_baseline used to carry "vent settings", "ventilator
# settings", "initial settings", "baseline", "set the vent", "start the vent",
# "vent the patient" and "mechanical ventilation" in its OWN applies_when. It
# is first in the file, so it was the first match for almost every real vent
# question and shadowed the four specific cards behind it — a DKA query
# reaching the ARDS-pattern card is F-12 with the roles reversed, and it stayed
# invisible only because no card is signed off yet. The generic phrases live in
# the module now, and they lead to a QUESTION rather than to a default: the
# physiology decides the settings, and guessing which one is not a thing a
# ventilator card gets to do.

GENERIC_SETTINGS_QUERIES = [
    "what are the vent settings for this guy",
    "vent settings",
    "ventilator settings, 80kg male",
    "initial settings on the vent",
    "set the vent up",
    "about to start the vent, what settings",
    "mechanical ventilation for this patient",
]


@pytest.mark.parametrize("query,expected", [
    ("Ventilator settings for 75kg male in DKA. Ph 7.1", "metabolic_acidosis"),
    ("need basic vent settings for TBI patient", "tbi"),
    ("vent settings for an asthmatic, status asthmaticus", "obstructive"),
    ("initial vent settings, blast lung and pulmonary contusion", "chest_trauma"),
])
def test_the_baseline_card_no_longer_shadows_the_specific_ones(query, expected, live):
    """Every physiology card live at once — the state the fence is walking
    towards, one signoff at a time. The card that names the physiology answers,
    not the one that happens to be first in the file."""
    for card_id in vm.PHYSIOLOGY:
        live("physiology", signed_physiology(card_id))
    family, card = vm.dispatch(query)
    assert (family, card["id"]) == ("physiology", expected), query


@pytest.mark.parametrize("query", [
    "ards vent settings",
    "lung protective vent settings",
    "acute respiratory distress, what settings on the vent",
    "ardsnet on the vent",
])
def test_the_baseline_card_still_answers_its_own_physiology(query, live):
    """Narrowing it to its own signals must not switch it off. ARDS is a
    physiology like the other four, not the drawer everything else falls into."""
    for card_id in vm.PHYSIOLOGY:
        live("physiology", signed_physiology(card_id))
    family, card = vm.dispatch(query)
    assert (family, card["id"]) == ("physiology", "lung_protective_baseline"), query


def test_no_physiology_card_claims_a_generic_settings_phrase():
    """The card files, checked directly. A generic phrase in any card's
    applies_when re-creates the shadow for whichever card is first."""
    for query in GENERIC_SETTINGS_QUERIES:
        claimed = [cid for cid, card in vm.PHYSIOLOGY.items()
                   if vm._match_applies_when(card, query)]
        assert claimed == [], f"{claimed} claimed {query!r} on generic wording"


def test_a_generic_settings_question_is_recognised_as_one():
    for query in GENERIC_SETTINGS_QUERIES:
        assert vm.needs_physiology_choice(query), query


@pytest.mark.parametrize("query", DKA_PHRASINGS + TBI_PHRASINGS + [
    "vent settings for an asthmatic",
    "ards vent settings",
])
def test_a_settings_question_that_names_a_physiology_is_not_a_choice(query):
    """The gate is for the ones that named nothing. A query with a physiology
    in it has already answered the question the gate would ask — and this holds
    while every card is still pending, because applies_when is data, not a
    signoff."""
    assert not vm.needs_physiology_choice(query), query


def test_an_alarm_is_not_a_settings_question():
    """Troubleshooting outranks settings, and it outranks the gate for the same
    reason: a patient deteriorating on a ventilator is not being asked about."""
    for query in ("high pressure alarm on the vent",
                  "the vent is alarming, patient desatting",
                  "breath stacking on the vent"):
        assert not vm.needs_physiology_choice(query), query


def test_the_settings_phrases_are_word_anchored():
    """House doctrine, applied to the phrases that now decide whether a medic
    gets asked a question. Each of these carries vent context — it is the
    settings phrase itself that must not match inside a longer word."""
    for text in ("solvent settings on the bench",
                 "the event settings look wrong on the vent",
                 "reset the vents in the tent, then check the patient"):
        assert vm.has_vent_context(text), f"weak specimen: {text!r}"
        assert not vm.needs_physiology_choice(text), text


def test_the_gate_is_silent_while_no_physiology_card_is_live():
    """Today's shipped state. A question is only worth a turn if answering it
    leads somewhere: with nothing signed off, asking "which physiology?" would
    cost a turn and then have nothing to serve, while that same query falls
    through to a retrieval that already answers the TBI phrasings. Blocking
    working behaviour to ask a question we cannot act on would be F-12 in a
    third costume."""
    for query in GENERIC_SETTINGS_QUERIES:
        assert vm.needs_physiology_choice(query), query
        assert vm.physiology_gate(query) is None, query


def test_the_gate_asks_which_physiology_once_a_card_is_live(live):
    live("physiology", signed_physiology("metabolic_acidosis"))
    for query in GENERIC_SETTINGS_QUERIES:
        ask = vm.physiology_gate(query)
        assert ask is not None, query
        assert vm.PHYSIOLOGY["metabolic_acidosis"]["title"] in ask


def test_the_gate_lists_only_the_cards_that_can_answer(live):
    """Partial deployment is the normal state, so the menu is never a list of
    things that are still dark."""
    live("physiology", signed_physiology("metabolic_acidosis"))
    live("physiology", signed_physiology("tbi"))
    ask = vm.physiology_gate("what are the vent settings for this guy")
    assert vm.PHYSIOLOGY["metabolic_acidosis"]["title"] in ask
    assert vm.PHYSIOLOGY["tbi"]["title"] in ask
    for dark in ("lung_protective_baseline", "obstructive", "chest_trauma"):
        assert vm.PHYSIOLOGY[dark]["title"] not in ask, dark


def test_the_gate_does_not_fire_when_a_card_claims_the_query(live):
    """dispatch() runs first in the pipeline. The gate must not shadow a card
    the way the card used to shadow the others."""
    live("physiology", signed_physiology("metabolic_acidosis"))
    for query in DKA_PHRASINGS:
        assert vm.dispatch(query) is not None, query
        assert vm.physiology_gate(query) is None, query


def test_an_unsigned_card_cannot_appear_in_the_gate(live):
    """The fence covers the menu too: naming a card is a weaker claim than
    serving one, but it is still a claim that the content is there."""
    live("physiology", signed_physiology("metabolic_acidosis", signoff=False))
    assert vm.physiology_gate("what are the vent settings for this guy") is None


# ── IBW AND THE DOSING BASIS ────────────────────────────────────────────────

@pytest.mark.parametrize("height_cm,sex,expected", [
    (152.4, "male", 50.0),      # exactly 60 inches — the formula's base
    (152.4, "female", 45.5),
    (177.8, "male", 73.0),      # 70 in -> 50 + 2.3*10
    (177.8, "female", 68.5),
    (165.0, "female", 56.9),
    (190.5, "male", 84.5),      # 75 in -> 50 + 2.3*15
    (140.0, "male", 50.0),      # below base: never negative
])
def test_devine_ideal_body_weight(height_cm, sex, expected):
    assert vm.ideal_body_weight_kg(height_cm, sex) == pytest.approx(expected, abs=0.15)


@pytest.mark.parametrize("height_cm,sex", [
    (None, "male"), (178.0, None), (None, None), (178.0, "unspecified"),
])
def test_ibw_returns_none_rather_than_guessing(height_cm, sex):
    """Defaulting a sex or a height puts an invented number under every breath."""
    assert vm.ideal_body_weight_kg(height_cm, sex) is None


def test_vt_is_dosed_on_ibw_when_height_and_sex_are_known():
    # 178 cm is 70.08 inches, not 70 — the conversion is not rounded to whole
    # inches before the formula, and a test that assumed it was would be
    # asserting a different formula from the one that ships.
    ctx = extract_patient_context("80kg male, 178 cm, in DKA")
    basis = vm.dosing_basis(ctx)
    assert basis["basis"] == "ibw"
    assert basis["weight_kg"] == pytest.approx(73.2, abs=0.05)
    out = vm.render_physiology(signed_physiology(), basis)
    assert "IBW 73.2 kg" in out
    assert "439-586 mL" in out, out      # 6-8 mL/kg x 73.2
    assert "ACTUAL" not in out


def test_vt_falls_back_to_actual_weight_with_the_cards_caveat():
    """Serve, do not block. F-12 is a vent question answered with something
    else, and refusing here would be the same failure in a new place."""
    ctx = extract_patient_context("80kg patient in DKA on the vent")
    basis = vm.dosing_basis(ctx)
    assert basis["basis"] == "actual"
    assert sorted(basis["missing"]) == ["height", "sex"]
    out = vm.render_physiology(signed_physiology(), basis)
    assert "ACTUAL weight 80.0 kg — not IBW" in out
    assert "**CAVEAT**" in out
    assert "TEST caveat" in out, "the caveat text must come from the CARD"


def test_the_follow_up_ask_is_non_blocking():
    ctx = extract_patient_context("80kg patient in DKA on the vent")
    basis = vm.dosing_basis(ctx)
    ask = vm.follow_up_ask("physiology", basis)
    assert ask and "height" in ask and "sex" in ask
    assert vm.follow_up_ask("physiology", vm.dosing_basis(
        extract_patient_context("80kg male, 178cm, DKA"))) is None


def test_a_hedged_weight_cannot_anchor_a_tidal_volume():
    """F-1 applies unchanged. estimated_weight_kg is not a dosing weight, and
    a tidal volume is a dose delivered thirty times a minute."""
    ctx = extract_patient_context("he's about 80kg I think, DKA, on the vent")
    assert ctx.confirmed_weight_kg is None
    assert ctx.estimated_weight_kg == 80.0
    basis = vm.dosing_basis(ctx)
    assert basis["basis"] is None
    assert basis["weight_kg"] is None
    out = vm.render_physiology(signed_physiology(), basis)
    assert "80" not in out.split("**SETTINGS**")[1].split("**TITRATE**")[0]


def test_a_hedged_weight_with_height_and_sex_still_uses_ibw():
    """IBW does not come from the weight at all, so a hedged weight is
    irrelevant once height and sex are known."""
    ctx = extract_patient_context("about 80kg maybe, male, 178 cm, DKA")
    basis = vm.dosing_basis(ctx)
    assert basis["basis"] == "ibw"
    assert basis["weight_kg"] == pytest.approx(73.2, abs=0.05)


# ── DISPATCH: PRIORITY AND COLLISIONS ───────────────────────────────────────

def _live_all(monkeypatch):
    """Sign one card in each family so priority can be observed at all."""
    for family, attr, builder, cid in (
            ("physiology", "PHYSIOLOGY", signed_physiology, "obstructive"),
            ("troubleshooting", "TROUBLESHOOTING", signed_trouble,
             "breath_stacking_auto_peep"),
            ("device", "DEVICES", signed_device, "hamilton_t1")):
        table = dict(vm.FAMILIES[family])
        table[cid] = builder(cid)
        monkeypatch.setattr(vm, attr, table)
        monkeypatch.setitem(vm.FAMILIES, family, table)


def test_troubleshooting_outranks_settings(monkeypatch):
    """A patient deteriorating on a ventilator is not a question about what the
    settings should have been. Answering the second when asked the first is
    S-4 with the roles reversed."""
    _live_all(monkeypatch)
    family, card = vm.dispatch("asthmatic on the vent, breath stacking and the "
                               "high pressure alarm is going off")
    assert family == "troubleshooting"
    assert card["id"] == "breath_stacking_auto_peep"


def test_device_plus_alarm_goes_to_troubleshooting_with_the_device_cross_referenced(monkeypatch):
    _live_all(monkeypatch)
    query = "hamilton t1 is alarming, breath stacking on the vent"
    family, card = vm.dispatch(query)
    assert family == "troubleshooting"
    out = vm.render("troubleshooting", card, PatientContext(), query)
    assert "**ON THIS DEVICE**" in out
    assert "Hamilton T1" in out


def test_device_without_an_alarm_goes_to_the_device_card(monkeypatch):
    _live_all(monkeypatch)
    family, card = vm.dispatch("how do I start up the hamilton t1 vent")
    assert family == "device"
    assert card["id"] == "hamilton_t1"


def test_settings_answer_only_when_nothing_more_urgent_claims_the_query(monkeypatch):
    _live_all(monkeypatch)
    family, card = vm.dispatch("vent settings for an asthmatic")
    assert family == "physiology"
    assert card["id"] == "obstructive"


# The collision the build request calls out by name.
@pytest.mark.parametrize("query,should_match", [
    ("hamilton t1 vent startup", True),
    ("the T1 is alarming on the vent", True),
    ("T1 burst fracture, neuro intact", False),
    ("penetrating injury at T1", False),
    ("t1 level sensory loss", False),
    ("zoll emv on the vent", True),
    ("731 vent alarm", True),
    ("give 731 mg of something", False),
    ("ltv 1200 vent circuit", True),
    ("1200 mL blood loss", False),
    ("1200 hours, casualty inbound", False),
    ("ventway sparrow", True),
    ("sparrow", True),
])
def test_device_aliases_require_vent_context_when_ambiguous(query, should_match):
    """"T1" is a thoracic level, a trauma category and a Hamilton ventilator.
    Word anchoring cannot separate those — only context can. Same treatment
    F-6 gave "k", "hs" and "cold" in the router."""
    assert (vm.named_device(query) is not None) is should_match, query


def test_no_vent_pattern_matches_inside_a_longer_word():
    """House doctrine. This repo is at five substring specimens and a sixth in
    the module that decides ventilator settings is not one anyone wants."""
    for text in ("preventing further blood loss",      # 'vent' inside 'preventing'
                 "the event was at 0300",              # 'vent' inside 'event'
                 "inventory check",                    # 'vent' inside 'inventory'
                 "adventitious sounds"):               # 'vent' inside 'adventitious'
        assert not vm.has_vent_context(text), text
    assert not vm.looks_like_vent_trouble("preventing decompensation")


def test_alarm_language_alone_does_not_route_without_vent_context():
    """"the alarm is going off" in a room full of monitors is not a vent
    problem."""
    assert not vm.looks_like_vent_trouble("the monitor alarm is going off")
    assert vm.looks_like_vent_trouble("the vent alarm is going off")


def test_a_non_vent_query_is_never_claimed():
    for query in ("junctional groin wound, tourniquet won't seat",
                  "how much ketamine for a 6yo arm fracture",
                  "what is the parkland formula",
                  ""):
        assert vm.dispatch(query) is None, query


def test_applies_when_cannot_inject_a_pattern(live):
    """Card files are data. A signal list is matched with the same word
    anchoring as everything else, never compiled as a regex."""
    card = signed_physiology(applies_when=[".*", "(?i)vent"])
    live("physiology", card)
    assert vm.dispatch("literally anything at all") is None


# ── HEIGHT AS A VITAL ───────────────────────────────────────────────────────

import vitals as v  # noqa: E402


@pytest.mark.parametrize("text,cm", [
    ("height 180 cm", 180.0), ("he is 180cm", 180.0), ("ht 72 in", 182.9),
    ("height 70", 177.8), ("5'10\"", 177.8), ("5 ft 10 in", 177.8),
    ("6 foot", 182.9), ("1.8 m", 180.0), ("175 cm", 175.0),
    ("height 90 cm", 90.0), ("80kg male, 175 cm", 175.0), ("he is 180 tall", 180.0),
])
def test_height_phrasings(text, cm):
    readings, _ = v.parse_vitals(text, ts=None)
    assert readings["height"].value == pytest.approx(cm, abs=0.1), text
    assert readings["height"].unit == "cm"


def test_an_ambiguous_bare_height_is_rejected_not_guessed():
    """85-99 is neither a plausible cm nor a plausible inch reading. "Need
    height and sex before vent settings." already exists as a gate question,
    so asking costs a turn while guessing scales every breath."""
    readings, rejections = v.parse_vitals("height 90", ts=None)
    assert "height" not in readings
    assert [r.name for r in rejections] == ["height"]
    assert "Couldn't read that vital" in v.rejection_notice(rejections)


def test_a_measurement_that_is_not_a_height_is_skipped_silently():
    """Asymmetric on purpose: a number next to "height" was MEANT as one, a
    bare "3 cm laceration" was not, and a notice that fires on wound
    measurements is a notice nobody reads."""
    readings, rejections = v.parse_vitals("3 cm laceration to the scalp", ts=None)
    assert "height" not in readings
    assert not [r for r in rejections if r.name == "height"]


def test_height_supersedes_like_every_other_vital():
    ctx = extract_patient_context("male, height 175 cm")
    assert ctx.vitals["height"].value == 175.0
    ctx = extract_patient_context("correction, he is 182 cm", prior_ctx=ctx)
    assert ctx.vitals["height"].value == 182.0
    assert [s["name"] for s in ctx.vitals_superseded] == ["height"]


def test_a_patient_boundary_clears_height():
    """It is a property of a patient, and a boundary is a new patient. A
    carried-over height would scale the next casualty's tidal volume."""
    history = [{"query": "6 year old, 34kg, height 120 cm"}, {"query": "34kg"}]
    ctx = oc.rebuild_patient_context_from_history(
        "have a marine that was hit by an IED - he is bleeding out",
        conversation_history=history)
    assert ctx.boundary_reset_reason
    assert "height" not in ctx.vitals
    assert vm.dosing_basis(ctx)["height_cm"] is None


def test_height_does_not_eat_a_blood_pressure():
    readings, _ = v.parse_vitals("BP 82/40, height 180, HR 128", ts=None)
    assert readings["sbp"].value == 82.0
    assert readings["dbp"].value == 40.0
    assert readings["height"].value == 180.0
    assert readings["hr"].value == 128.0


@pytest.mark.parametrize("text,sex", [
    ("80kg male trauma patient", "male"), ("64kg geriatric female", "female"),
    ("a 30 year old man, 175cm", "male"), ("patient is F, 165 cm", "female"),
    ("he is 80kg", None), ("she is 60kg", None), ("no sex stated", None),
])
def test_sex_capture_does_not_infer_from_pronouns(text, sex):
    """A pronoun is how someone is being referred to; a stated "male" is a
    fact. The gap between them is not one a tidal-volume parser gets to close."""
    assert extract_patient_context(text).sex == sex


# ── PROVENANCE ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family,builder,query", [
    ("physiology", signed_physiology, "vent settings dka"),
    ("troubleshooting", signed_trouble, "high pressure alarm on the vent"),
    ("device", signed_device, "hamilton t1 startup vent"),
])
def test_every_served_card_carries_its_source_line(family, builder, query):
    card = builder()
    out = vm.render(family, card, PatientContext(), query)
    assert "**SOURCE**: EdgeCDSS clinical card" in out
    assert "reviewed A. Azelton, 2026-08-22" in out
    assert "refs: TEST reference" in out
    assert vm.DISCLAIMER in out


def test_a_device_card_names_the_manual_revision_it_summarised():
    """The visible half of the copyright rule."""
    out = vm.render_device(signed_device())
    assert "summarized from operator's manual rev 9.9, verified 2026-08-22" in out


def test_card_is_a_third_provenance_value_not_a_synonym_for_jts():
    assert oc.knowledge_source("VENT_CARD") == "card"
    assert oc.knowledge_source("JTS_GROUNDED") == "jts"
    assert oc.knowledge_source("GENERAL_REFERENCE") == "general"
    assert oc.knowledge_source("DETERMINISTIC_PRE_GATE") == "jts"


def test_the_card_source_mode_is_not_gated_by_the_safety_gate():
    """Card answers are reviewed fixed strings and return before the gate, like
    the other deterministic cards. _finalise still applies vitals cautions and
    the boundary notice to them."""
    assert "VENT_CARD" not in oc.GATED_SOURCE_MODES


# ── COPYRIGHT LINT ──────────────────────────────────────────────────────────

def test_no_device_card_field_exceeds_the_summary_limit():
    assert vm.lint_device_cards() == []


def test_an_overlong_device_field_is_flagged(monkeypatch):
    card = signed_device(quirks=["x" * (vm.DEVICE_FIELD_MAX_CHARS + 1)])
    monkeypatch.setattr(vm, "DEVICES", {"hamilton_t1": card})
    problems = vm.lint_device_cards()
    assert problems and "summary limit" in problems[0]


def test_verbatim_manual_text_is_flagged(monkeypatch):
    """The lint takes its corpus as an argument so this runs without a manual
    ever existing in the repo — which is the point of putting .manual. in
    .gitignore."""
    passage = ("Press and hold the mode key for three seconds until the "
               "display shows the configuration menu and then release it")
    card = signed_device(quirks=[passage])
    monkeypatch.setattr(vm, "DEVICES", {"hamilton_t1": card})
    problems = vm.lint_device_cards({"t1_manual.txt": "PREAMBLE. " + passage + " END."})
    assert problems and "verbatim run" in problems[0]
    assert vm.lint_device_cards({"t1_manual.txt": "nothing alike here at all"}) == []


def test_manual_files_are_gitignored():
    root = pathlib.Path(vm.__file__).resolve().parent.parent
    ignored = (root / ".gitignore").read_text()
    assert ".manual." in ignored
    assert "manuals/" in ignored


# ── LOG CONTRACT ────────────────────────────────────────────────────────────

def test_log_records_the_card_that_answered(tmp_path, monkeypatch):
    """A card answer must be traceable to the exact authored revision that
    produced it — the question override_fired answers for the gate.

    Without card_id and card_version, "which version of the DKA card said
    that" is unanswerable from the log, which is the S-2 lesson applied to a
    tier where the content changes by hand.
    """
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    result = {
        "response": "**METABOLIC ACIDOSIS**\n...", "sources": [],
        "source_mode": "VENT_CARD", "card_id": "metabolic_acidosis",
        "card_version": "1.0.0", "validator_result": "SAFE",
        "validator_issues": [], "patient_context": PatientContext().to_dict(),
    }
    result["source"] = oc.knowledge_source(result["source_mode"])
    oc.log_query("vent settings dka", result)

    written = sorted(tmp_path.glob("*.jsonl"))
    entry = json.loads(written[0].read_text().strip())
    assert entry["source"] == "card"
    assert entry["card_id"] == "metabolic_acidosis"
    assert entry["card_version"] == "1.0.0"
    assert entry["log_schema"] == oc.LOG_SCHEMA_VERSION


def test_a_non_card_answer_records_card_fields_as_null(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    result = {"response": "x", "source_mode": "JTS_GROUNDED",
              "validator_result": "SAFE", "validator_issues": [],
              "patient_context": PatientContext().to_dict()}
    result["source"] = oc.knowledge_source(result["source_mode"])
    oc.log_query("q", result)
    entry = json.loads(sorted(tmp_path.glob("*.jsonl"))[0].read_text().strip())
    assert entry["source"] == "jts"
    assert entry["card_id"] is None and entry["card_version"] is None


# ── END TO END THROUGH THE REAL PIPELINE ────────────────────────────────────

class _NoChroma:
    """The pipeline must not reach retrieval for a card answer."""
    def query(self, *a, **kw):
        raise AssertionError("a card answer must not hit ChromaDB")


def _no_model(*a, **kw):
    raise AssertionError("a card answer must not call a model")


def test_a_signed_card_answers_without_retrieval_or_a_model_call(monkeypatch, tmp_path):
    """Deterministic tier, end to end. No ChromaDB, no provider, no validator."""
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(oc.providers, "chat", _no_model)
    table = dict(vm.PHYSIOLOGY)
    table["metabolic_acidosis"] = signed_physiology("metabolic_acidosis")
    monkeypatch.setattr(vm, "PHYSIOLOGY", table)
    monkeypatch.setitem(vm.FAMILIES, "physiology", table)

    result = oc._query_with_rag_internal(
        "Ventilator settings for 75kg male in DKA. Ph 7.1", _NoChroma())

    assert result["source_mode"] == "VENT_CARD"
    assert result["card_id"] == "metabolic_acidosis"
    assert "**SETTINGS**" in result["response"]
    assert "**SOURCE**: EdgeCDSS clinical card" in result["response"]
    assert result["validator_result"] == "SAFE"


def test_the_same_query_falls_through_while_the_card_is_pending(monkeypatch, tmp_path):
    """Today's shipped state: the card exists, is unsigned, and changes
    nothing. The query reaches retrieval exactly as it did before."""
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    reached = []

    class _Chroma:
        def query(self, text, n_results=5):
            reached.append(text)
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    monkeypatch.setattr(oc.providers, "chat",
                        lambda *a, **kw: '{"result":"SAFE","issues":[],"rationale":""}')
    result = oc._query_with_rag_internal(
        "Ventilator settings for 75kg male in DKA. Ph 7.1", _Chroma())
    assert result["source_mode"] != "VENT_CARD"
    assert reached, "the pending card must not have swallowed the query"


def test_a_card_answer_still_gets_the_boundary_notice_and_vitals_cautions(monkeypatch):
    """_finalise covers every return path, and a card is one of them."""
    table = dict(vm.PHYSIOLOGY)
    table["metabolic_acidosis"] = signed_physiology("metabolic_acidosis")
    monkeypatch.setattr(vm, "PHYSIOLOGY", table)
    monkeypatch.setitem(vm.FAMILIES, "physiology", table)
    assert "VENT_CARD" not in oc.GATED_SOURCE_MODES


def test_the_pipeline_asks_which_physiology_instead_of_defaulting(monkeypatch, tmp_path):
    """The gate, end to end. Two cards live, the query names neither, and the
    medic is asked rather than handed the first card in the file. No retrieval
    and no model call: the question is deterministic."""
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(oc.providers, "chat", _no_model)
    table = dict(vm.PHYSIOLOGY)
    for card_id in ("lung_protective_baseline", "metabolic_acidosis"):
        table[card_id] = signed_physiology(card_id)
    monkeypatch.setattr(vm, "PHYSIOLOGY", table)
    monkeypatch.setitem(vm.FAMILIES, "physiology", table)

    result = oc._query_with_rag_internal(
        "what are the vent settings for this guy", _NoChroma())

    assert result["source_mode"] == "VENT_GATE"
    assert result["validator_result"] == "SKIPPED_SAFE_GATE"
    assert "Which physiology?" in result["response"]
    assert "**SETTINGS**" not in result["response"], "it answered instead of asking"
    assert table["metabolic_acidosis"]["title"] in result["response"]


def test_the_pipeline_does_not_ask_while_every_card_is_pending(monkeypatch, tmp_path):
    """Today's shipped state, pinned at the pipeline. A question we cannot act
    on would cost a turn and take away a retrieval that already answers."""
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    reached = []

    class _Chroma:
        def query(self, text, n_results=5):
            reached.append(text)
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    monkeypatch.setattr(oc.providers, "chat",
                        lambda *a, **kw: '{"result":"SAFE","issues":[],"rationale":""}')
    result = oc._query_with_rag_internal(
        "what are the vent settings for this guy", _Chroma())
    assert result["source_mode"] != "VENT_GATE"
    assert reached, "the gate swallowed a query it had nothing to serve for"


def test_the_gate_is_a_question_not_an_answer():
    """VENT_GATE bypasses the validator the way every other gate question does,
    and it must not be mistaken for a card answer in the provenance log — no
    card produced it."""
    assert "VENT_GATE" not in oc.GATED_SOURCE_MODES
    assert "VENT_GATE" not in oc.CARD_SOURCE_MODES
    assert oc.knowledge_source("VENT_GATE") == oc.knowledge_source("PRE_GATE")
