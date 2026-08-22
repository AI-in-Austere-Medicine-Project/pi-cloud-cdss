"""
EdgeCDSS — vital signs capture, supersession, rejection and cautions.

Offline, zero keys. The parser and the caution table are pure Python; the two
end-to-end tests stub the provider layer.

    cd server && ./run_unit_tests.sh
"""

import datetime
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import openai_client as oc  # noqa: E402
import vitals as v  # noqa: E402
from openai_client import PatientContext  # noqa: E402

# Anchored to the clock, not to a calendar date. Most uses only need the gaps
# between them, but two end-to-end tests put T0 in conversation_history against
# a CURRENT turn stamped from utcnow — and the gap from the history to now is
# what decides whether a patient boundary fires. A fixed date turns into an
# inactivity_timeout the moment real time walks past it plus
# PATIENT_BOUNDARY_TIMEOUT_MIN, and the suite starts failing on a clock instead
# of on a change. It did, on 2026-08-21 at 10:30Z.
_T_ANCHOR = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)


def _at(minutes):
    return (_T_ANCHOR + datetime.timedelta(minutes=minutes)).isoformat()


T0 = _at(0)
T5 = _at(5)
T9 = _at(9)


def parse(text, ts=T0):
    return v.parse_vitals(text, ts=ts)


def values(readings):
    return {k: r.value for k, r in readings.items()}


# ── parsing: the phrasings a medic actually types ───────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("HR 128", {"hr": 128}),
    ("hr of 128", {"hr": 128}),
    ("heart rate 128", {"hr": 128}),
    ("pulse 44", {"hr": 44}),
    ("BP 82/40", {"sbp": 82, "dbp": 40}),
    ("bp of 82/40", {"sbp": 82, "dbp": 40}),
    ("blood pressure 90/60", {"sbp": 90, "dbp": 60}),
    ("sats 91", {"spo2": 91}),
    ("sat 91", {"spo2": 91}),
    ("spo2 91", {"spo2": 91}),
    ("sats 91%", {"spo2": 91}),
    ("o2 sat 96", {"spo2": 96}),
    ("pulse ox 94", {"spo2": 94}),
    ("RR 8", {"rr": 8}),
    ("resp rate 8", {"rr": 8}),
    ("respiratory rate 8", {"rr": 8}),
    ("GCS 13", {"gcs": 13}),
    ("gcs of 13", {"gcs": 13}),
    ("temp 38.2", {"temp": 38.2}),
    ("T 38.5", {"temp": 38.5}),
    ("temperature of 39", {"temp": 39}),
    ("fever of 104", {"temp": 104}),
    ("fever 104", {"temp": 104}),
    ("fever at 39.4", {"temp": 39.4}),
])
def test_common_phrasings(text, expected):
    readings, rejections = parse(text)
    assert values(readings) == expected
    assert rejections == []


@pytest.mark.parametrize("text,expected", [
    # A zero for the letter O is the most common way this gets typed.
    ("sp02 88", {"spo2": 88}),
    ("sa02 88", {"spo2": 88}),
    ("SpO2 of 88", {"spo2": 88}),
])
def test_typo_adjacent_spo2_spellings(text, expected):
    assert values(parse(text)[0]) == expected


def test_gcs_component_form_is_summed():
    """"GCS 3-4-5" is how a total gets written down in the field."""
    assert values(parse("GCS 3-4-5")[0]) == {"gcs": 12}
    assert values(parse("gcs e3 v4 m5")[0]) == {"gcs": 12}


def test_several_vitals_in_one_sentence():
    readings, _ = parse("34yo male HR 128 BP 82/40 sats 91 RR 28 GCS 14 temp 35.1")
    assert values(readings) == {"hr": 128, "sbp": 82, "dbp": 40, "spo2": 91,
                                "rr": 28, "gcs": 14, "temp": 35.1}


# ── temperature: two units, one canonical value ─────────────────────────────
#
# The medic states a temperature in Celsius or Fahrenheit and rarely says which.
# The two plausible bands do not overlap, so the number itself says which — and
# a number in neither band is not a temperature this parser can read.

def test_a_stated_unit_is_kept_and_both_conversions_are_stored():
    """Showing 40 C to someone who typed 104 F is a translation they did not ask
    for, and a number they cannot check against the thermometer in their hand."""
    r = parse("temp 101.2 F")[0]["temp"]
    assert (r.value, r.unit) == (101.2, "F")
    assert r.value_c == pytest.approx(38.4, abs=0.1)
    assert r.value_f == 101.2
    assert r.canonical == r.value_c

    r = parse("temp 38.5 C")[0]["temp"]
    assert (r.value, r.unit) == (38.5, "C")
    assert r.value_c == 38.5
    assert r.value_f == pytest.approx(101.3, abs=0.1)
    assert r.canonical == 38.5


def test_an_unlabelled_temperature_is_read_by_which_band_it_falls_in():
    """35-43 is a Celsius patient; 93-110 is a Fahrenheit one. No overlap."""
    for text, value, unit in (("temp 39", 39.0, "C"),
                              ("temp 36.8", 36.8, "C"),
                              ("temp 99", 99.0, "F"),
                              ("fever of 104", 104.0, "F")):
        r = parse(text)[0]["temp"]
        assert (r.value, r.unit) == (value, unit), text


def test_a_temperature_in_neither_band_is_rejected_visibly():
    """Guessing a unit for an implausible number is how a system holds 50C."""
    for text in ("temp 44", "temp 50", "fever of 130", "temp 12"):
        readings, rejections = parse(text)
        assert "temp" not in readings, text
        assert [r.name for r in rejections] == ["temp"], text
        assert "either unit" in rejections[0].reason
    assert "Couldn't read that vital" in v.rejection_notice(parse("temp 50")[1])


def test_a_stated_unit_is_never_reinterpreted():
    """"temp 104 C" is a mistyped reading, not a Fahrenheit one.

    Reading it as F would invent a plausible vital out of an implausible one,
    which is the failure the rejection path exists to prevent.
    """
    readings, rejections = parse("temp 104 C")
    assert "temp" not in readings
    assert "35-43C" in rejections[0].reason

    readings, rejections = parse("temp 39 F")
    assert "temp" not in readings
    assert "93-110F" in rejections[0].reason


def test_hypothermia_in_celsius_is_rejected_by_the_shipped_band():
    """Pinned because it is a consequence, not an accident.

    temp.min is 35, so a Celsius hypothermia reading falls outside the band and
    is not stored. Stated in Fahrenheit the same patient reads fine (93F is
    33.9C), which is the only way hypothermia_txa arms. Lowering temp.min in
    vitals_rules.json restores it with no code change; this test says out loud
    which way the shipped config is set.
    """
    readings, rejections = parse("temp 33")
    assert "temp" not in readings
    assert rejections and rejections[0].name == "temp"
    assert parse("temp 93 F")[0]["temp"].canonical == pytest.approx(33.9, abs=0.1)


def test_febrile_without_a_number_captures_nothing():
    """This table stores measurements. The word alone is the router's business
    (has_fever), and a described fever is not a measured one."""
    for text in ("he is febrile", "febrile and tachycardic", "patient has a fever",
                 "fever for two days", "denies fever"):
        readings, rejections = parse(text)
        assert readings == {}, text
        assert rejections == [], text


def test_a_temperature_is_shown_in_the_unit_it_was_stated_in():
    readings = parse("fever of 104")[0]
    assert v.format_pair(readings, "temp") == "Temp 104 F"
    assert v.summary_line(readings) == "Temp 104 F"
    # The prompt carries the conversion too: a model reasoning about a fever
    # should not have to do the arithmetic or guess the unit.
    assert "(40C)" in v.prompt_block(readings, now_ts=T5)
    assert "(40C)" not in v.prompt_block(parse("temp 39")[0], now_ts=T5)


def test_the_caution_table_compares_the_canonical_value():
    """The thresholds are written in one unit. A reading kept in the other one
    would compare 93 against a rule that means 33.9."""
    cautions = v.conflicts("Give TXA 1 g IV.", armed("temp 93 F"))
    assert len(cautions) == 1
    assert "93 F" in cautions[0], "quoted back in the unit the medic used"
    assert not v.conflicts("Give TXA 1 g IV.", armed("temp 39"))


def test_bare_blood_pressure_is_read():
    assert values(parse("pt is 82/40 and tachy")[0]) == {"sbp": 82, "dbp": 40}


@pytest.mark.parametrize("text,expected", [
    ("HR 90/50", {"hr": 90}),
    ("map 70/40", {"map": 70}),
    ("gcs 14/15", {"gcs": 14}),
])
def test_digits_another_label_claimed_do_not_leave_half_a_pressure(text, expected):
    """The bare-BP form used to store the diastolic whether or not the systolic
    survived the overlap check, so "HR 90/50" left a diastolic of 50 with no
    systolic behind it. Half a pressure is not a pressure — and it is not
    something to derive a MAP from either."""
    readings, _ = parse(text)
    assert values(readings) == expected
    assert "dbp" not in readings


# ── MAP: derived, not measured ──────────────────────────────────────────────
#
# The only value in this module the system produces rather than hears. Which
# means it has to be visibly computed, has to stay in agreement with the
# pressure behind it, and must never look fresher than that pressure does.


def merged(text, prior=None, ts=T0):
    """Parse and fold, which is where derivation happens — parse_vitals sees one
    turn, and a MAP is a property of the accumulated state."""
    found, _ = parse(text, ts=ts)
    out, _ = v.merge(prior or {}, found)
    return out


@pytest.mark.parametrize("text,expected", [
    ("BP 90/30", 50),        # (90 + 60) / 3
    ("BP 82/40", 54),        # (82 + 80) / 3
    ("BP 120/80", 93),       # (120 + 160) / 3 = 93.33, rounded
    ("BP 100/48", 65),       # (100 + 96) / 3 = 65.33 — the threshold, from above
    ("BP 100/46", 64),       # (100 + 92) / 3 = 64 — and from below
])
def test_map_is_derived_from_the_pressure(text, expected):
    m = merged(text)
    assert m["map"].value == expected
    assert m["map"].unit == "mmHg"
    assert m["map"].derived is True


def test_a_derived_map_says_where_it_came_from():
    """A computed number that reads as a measured one is its own small S-1."""
    m = merged("BP 90/30")
    assert m["map"].raw == "derived from 90/30"
    assert "derived" in v.prompt_block(m, now_ts=T5)
    assert m["sbp"].derived is False, "a stated reading is flagged stated"


def test_no_map_without_both_pressures():
    """Derivation needs two numbers. One of them is not a mean of anything."""
    assert "map" not in merged("HR 128")
    assert v.derive_map({"sbp": parse("BP 90/30")[0]["sbp"]}) is None
    assert v.derive_map({}) is None


def test_an_impossible_pressure_yields_no_map():
    """The rejection path is unchanged, and derivation inherits it for free.

    A pressure that failed its plausibility band was never stored, so there is
    nothing to derive from — the system does not hold a MAP it told the medic it
    could not read.
    """
    found, rejections = parse("BP 400/300")
    m, _ = v.merge({}, found)
    assert m == {}
    assert "map" not in m
    assert len(rejections) == 1


def test_a_rejected_pressure_does_not_disturb_an_existing_map():
    """The prior MAP is still the prior pressure's MAP, and still says so."""
    first = merged("BP 90/30", ts=T0)
    second = merged("now BP 400/300", first, ts=T5)
    assert second["map"].value == 50
    assert second["sbp"].value == 90


def test_map_recomputes_when_the_pressure_changes():
    first = merged("BP 120/80", ts=T0)
    assert first["map"].value == 93
    second = merged("now BP 82/40", first, ts=T5)
    assert second["map"].value == 54
    assert second["map"].ts == T5, "the new pressure's age, not the old one's"


def test_map_recomputes_from_a_lone_systolic_or_diastolic_update():
    """Either input moving is enough. A MAP still keyed to a superseded half of
    the pressure is a stale vital wearing a fresh one's face."""
    base = merged("BP 120/80", ts=T0)
    only_sbp = dict(base)
    only_sbp["sbp"] = v.VitalReading(90.0, "mmHg", T5, "90")
    out, _ = v.merge(only_sbp, {"sbp": only_sbp["sbp"]})
    assert out["map"].value == 83                       # (90 + 160) / 3

    only_dbp = dict(base)
    only_dbp["dbp"] = v.VitalReading(40.0, "mmHg", T5, "40")
    out, _ = v.merge(only_dbp, {"dbp": only_dbp["dbp"]})
    assert out["map"].value == 67                       # (120 + 80) / 3


def test_map_carries_the_age_of_its_older_input():
    """A derived value is only as fresh as the stalest thing behind it."""
    old_sbp = v.VitalReading(90.0, "mmHg", T0, "90")
    new_dbp = v.VitalReading(30.0, "mmHg", T5, "30")
    assert v.derive_map({"sbp": old_sbp, "dbp": new_dbp}).ts == T0
    assert v.derive_map({"sbp": new_dbp, "dbp": old_sbp}).ts == T0


def test_an_input_with_no_timestamp_makes_the_map_age_unknown():
    """Never fabricate freshness, and never launder it either.

    An unknown age is potentially any age. Taking the other input's timestamp
    would present the derived number as fresher than the data it came from.
    """
    m = merged("BP 90/30", ts=None)
    assert m["map"].ts is None
    assert v.age_minutes(m["map"], T9) is None


# ── MAP: stated beats derived ───────────────────────────────────────────────

def test_a_stated_map_is_captured_like_any_other_vital():
    """The medic may be reading an arterial line."""
    for text in ("MAP 70", "map of 70", "mean arterial pressure 70",
                 "mean arterial 70"):
        m = merged(text)
        assert m["map"].value == 70, text
        assert m["map"].derived is False, text


def test_the_word_map_alone_is_not_a_vital():
    """"map" is an ordinary English word, which is why the label is anchored and
    why a number has to follow it."""
    assert parse("check the roadmap 70 later")[0] == {}
    assert parse("show me the map")[0] == {}
    assert parse("mapping the route")[0] == {}


def test_an_impossible_stated_map_is_rejected_visibly():
    readings, rejections = parse("MAP 400")
    assert "map" not in readings
    assert len(rejections) == 1 and rejections[0].name == "map"


def test_a_stated_map_supersedes_the_derived_one():
    first = merged("BP 90/30", ts=T0)
    assert first["map"].derived is True
    second = merged("art line reads MAP 70", first, ts=T5)
    assert second["map"].value == 70
    assert second["map"].derived is False, "arithmetic does not overrule a measurement"


def test_a_stated_map_stands_until_a_pressure_outdates_it():
    stated = merged("MAP 70", merged("BP 90/30", ts=T0), ts=T5)
    carried, _ = v.merge(stated, parse("HR 128", ts=T9)[0])
    assert carried["map"].value == 70, "an unrelated turn does not recompute it away"
    assert carried["map"].derived is False


def test_a_newer_pressure_takes_the_map_back():
    """"Newer" is turn order, not a timestamp comparison — the same rule merge()
    already follows, so a turn carrying no `ts` still supersedes the one before."""
    stated = merged("MAP 70", merged("BP 90/30", ts=T0), ts=T5)
    after = merged("now BP 70/50", stated, ts=T9)
    assert after["map"].value == 57                     # (70 + 100) / 3
    assert after["map"].derived is True


def test_a_stated_map_is_recorded_as_superseding_the_derived_one():
    """A restatement is a change of belief the medic made, and the log has to
    answer "what did the system think the MAP was before this turn"."""
    first = merged("BP 90/30", ts=T0)
    _, superseded = v.merge(first, parse("MAP 70", ts=T5)[0])
    names = {s["name"]: s for s in superseded}
    assert names["map"]["from"]["value"] == 50
    assert names["map"]["to"]["value"] == 70


def test_a_recompute_is_not_a_supersession():
    """Nothing was displaced — the same formula met newer inputs, and those
    inputs are already in `superseded`. Reporting the MAP too would treble the
    list on every pressure update and say nothing the pressures do not."""
    first = merged("BP 120/80", ts=T0)
    _, superseded = v.merge(first, parse("BP 82/40", ts=T5)[0])
    assert [s["name"] for s in superseded] == ["sbp", "dbp"]


def test_map_reaches_the_strip_and_the_prompt():
    m = merged("BP 90/30")
    assert v.format_pair(m, "map") == "MAP 50 mmHg"
    assert "MAP 50 mmHg" in v.summary_line(m)
    assert v.to_dict(m)["map"] == {
        "value": 50.0, "unit": "mmHg", "ts": T0,
        "raw": "derived from 90/30", "derived": True,
    }


def test_map_is_cleared_by_a_patient_boundary():
    """Derived from this patient's pressure, so it is this patient's number."""
    ctx = oc.rebuild_patient_context_from_history(
        "new patient, HR 100",
        conversation_history=[{"query": "BP 90/30", "ts": T0}], now_ts=T9)
    assert ctx.boundary_reset_reason
    assert "map" not in ctx.vitals
    assert "sbp" not in ctx.vitals


# ── parsing: what must NOT be read as a vital ───────────────────────────────

@pytest.mark.parametrize("text", [
    "give 1/2 mg",                                  # a ratio, not a pressure
    "draw 0.24 mL of 100mg/mL ketamine IV (24mg)",  # a canonical GIVE line
    "1:10,000 epinephrine",
    "thrombosis 5 days ago",                        # 'hr' inside 'thrombosis'
    "patient has diarrhea 3 days",
    "80kg male with a blast injury",
])
def test_prose_and_doses_are_not_vitals(text):
    """Short vital labels are substrings of ordinary clinical words.

    Bare 't' matched the t in "pt is 82/40" and read a temperature of 82F before
    the labels were anchored — the same substring failure as F-2 in the alias
    table and "norepinephrine drip" in FIXED_PREP_TERMS.
    """
    readings, rejections = parse(text)
    assert readings == {}, f"{text!r} produced {values(readings)}"
    assert rejections == []


def test_a_dose_line_never_becomes_a_vital():
    """The one collision that would be actively dangerous.

    A GIVE line carries several numbers with units. If any of them were read as
    a vital, the caution table would then reason about a blood pressure the
    patient never had.
    """
    readings, _ = parse("Draw 0.75 mL of 100mg/mL ketamine IV (75mg).")
    assert readings == {}


# ── rejection: impossible values are visible, not silent ────────────────────

@pytest.mark.parametrize("text,name", [
    ("bp 400/300", "bp"),
    ("HR 900", "hr"),
    ("sats 4", "spo2"),
    ("GCS 22", "gcs"),
    ("RR 200", "rr"),
])
def test_impossible_values_are_rejected_not_stored(text, name):
    readings, rejections = parse(text)
    assert readings == {}, "an impossible value must never be stored"
    assert [r.name for r in rejections] == [name]
    assert rejections[0].reason


def test_a_reversed_pressure_is_rejected():
    """sbp > dbp is plausibility, not formatting. Reversed means mistyped."""
    readings, rejections = parse("BP 60/90")
    assert readings == {}
    assert "not above" in rejections[0].reason


def test_a_bad_pressure_rejects_both_halves():
    """A pressure is one measurement, so it passes or fails as one.

    300 sits inside the diastolic range. Storing it while rejecting the systolic
    would leave the system holding half a vital it just said it could not read.
    """
    readings, rejections = parse("bp 400/300")
    assert "dbp" not in readings and "sbp" not in readings
    assert len(rejections) == 1


def test_rejection_notice_names_the_value_and_says_it_was_dropped():
    _, rejections = parse("bp 400/300")
    notice = v.rejection_notice(rejections)
    assert "400/300" in notice
    assert "not stored" in notice.lower()
    assert v.rejection_notice([]) == ""


def test_good_vitals_survive_alongside_a_rejected_one():
    readings, rejections = parse("HR 128 bp 400/300 sats 91")
    assert values(readings) == {"hr": 128, "spo2": 91}
    assert len(rejections) == 1


# ── supersession ────────────────────────────────────────────────────────────

def test_newer_supersedes_and_the_prior_value_is_kept():
    first, _ = parse("BP 120/80", ts=T0)
    second, _ = parse("BP 82/40", ts=T5)
    merged, superseded = v.merge(first, second)
    assert merged["sbp"].value == 82
    assert merged["sbp"].ts == T5
    names = {s["name"]: s for s in superseded}
    assert names["sbp"]["from"] == {"value": 120.0, "ts": T0}
    assert names["sbp"]["to"] == {"value": 82.0, "ts": T5}


def test_an_unchanged_value_is_not_recorded_as_superseded():
    first, _ = parse("HR 128", ts=T0)
    second, _ = parse("HR 128", ts=T5)
    merged, superseded = v.merge(first, second)
    assert superseded == []
    assert merged["hr"].ts == T5, "the timestamp still refreshes"


def test_vitals_not_restated_are_carried_forward():
    first, _ = parse("HR 128 BP 120/80", ts=T0)
    second, _ = parse("BP 82/40", ts=T5)
    merged, _ = v.merge(first, second)
    assert merged["hr"].value == 128
    assert merged["hr"].ts == T0, "carried forward, not restamped"


def test_supersession_across_conversation_turns():
    history = [{"query": "80kg male BP 120/80 HR 90", "ts": T0},
               {"query": "now BP 82/40", "ts": T5}]
    ctx = oc.rebuild_patient_context_from_history(
        "sats 88", conversation_history=history, now_ts=T9)
    assert ctx.vitals["sbp"].value == 82
    assert ctx.vitals["hr"].value == 90
    assert ctx.vitals["spo2"].value == 88
    assert ctx.vitals["spo2"].ts == T9


def test_superseded_reports_this_turn_only():
    """Same "this turn" semantics as boundary_reset_reason.

    The log entry for a turn must describe what THAT turn changed. The server is
    stateless and replays the whole conversation on every request, so an
    accumulating list would re-report an old supersession on every subsequent
    query.
    """
    history = [{"query": "BP 120/80", "ts": T0}, {"query": "now BP 82/40", "ts": T5}]
    ctx = oc.rebuild_patient_context_from_history(
        "sats 88", conversation_history=history, now_ts=T9)
    assert ctx.vitals_superseded == [], "a replayed change is not this turn's change"

    ctx = oc.rebuild_patient_context_from_history(
        "BP 70/30", conversation_history=history, now_ts=T9)
    assert [s["name"] for s in ctx.vitals_superseded] == ["sbp", "dbp"]


# ── timestamps ──────────────────────────────────────────────────────────────

def test_a_turn_without_a_timestamp_yields_an_unknown_age():
    """Never fabricate freshness.

    Pre-v4.1 clients send no `ts` at all. Stamping those readings with the
    current time would present a stale vital as fresh — S-1 with a faster clock.
    """
    readings, _ = parse("HR 128", ts=None)
    assert readings["hr"].ts is None
    assert v.age_minutes(readings["hr"], T9) is None
    assert "age unknown" in v.prompt_block(readings, now_ts=T9)


def test_age_is_measured_from_the_turn_the_vital_was_stated_in():
    readings, _ = parse("HR 128", ts=T0)
    assert v.age_minutes(readings["hr"], T9) == pytest.approx(9.0)
    assert "9m ago" in v.prompt_block(readings, now_ts=T9)


# ── patient boundary clears vitals ──────────────────────────────────────────

def test_patient_boundary_clears_every_vital():
    """The S-1 fix must cover vitals or it covers nothing.

    A previous patient's blood pressure surviving a boundary is the original
    finding with a shorter half-life.
    """
    history = [{"query": "6yo 20kg BP 90/60 HR 140 sats 97", "ts": T0}]
    ctx = oc.rebuild_patient_context_from_history(
        "new patient, adult male", conversation_history=history, now_ts=T5)
    assert ctx.vitals == {}
    assert ctx.confirmed_weight_kg is None
    assert ctx.boundary_reset_reason


def test_the_reset_notice_names_vitals():
    """The medic is told what was cleared. If vitals go, the banner says so."""
    assert "vitals" in oc.BOUNDARY_RESET_NOTICE.lower()
    for word in ("weight", "age", "access"):
        assert word in oc.BOUNDARY_RESET_NOTICE.lower()


def test_a_fresh_context_has_no_vitals():
    assert PatientContext().vitals == {}
    assert PatientContext().vitals_superseded == []
    assert PatientContext().vitals_rejected == []


def test_two_contexts_do_not_share_a_vitals_dict():
    """A mutable default would leak one patient's vitals into every other."""
    a, b = PatientContext(), PatientContext()
    a.vitals["hr"] = v.VitalReading(128, "bpm", T0, "hr 128")
    assert b.vitals == {}


# ── conflict cautions ───────────────────────────────────────────────────────

def armed(text, ts=T0):
    return parse(text, ts=ts)[0]


def armed_map(text, ts=T0):
    """Same, folded through merge() — which is where MAP is derived."""
    return merged(text, ts=ts)


def test_hypotension_cautions_a_hypotension_risk_drug():
    cautions = v.conflicts("Give fentanyl 50 mcg IV for pain.", armed("BP 82/40"))
    assert len(cautions) == 1
    assert "fentanyl" in cautions[0]
    assert "82" in cautions[0]


def test_respiratory_depressant_cautioned_at_low_rr():
    cautions = v.conflicts("Give midazolam 2mg IV.", armed("RR 6"))
    assert cautions and "midazolam" in cautions[0]


def test_respiratory_depressant_cautioned_at_low_spo2():
    cautions = v.conflicts("Give morphine 4mg IV.", armed("sats 86"))
    assert cautions and "SpO2" in cautions[0]


def test_av_nodal_blocker_cautioned_at_low_hr():
    cautions = v.conflicts("Give diltiazem.", armed("HR 42"))
    assert cautions and "diltiazem" in cautions[0]


def test_a_low_map_arms_the_hypotension_caution():
    """MAP < 65 is the same warning as SBP < 90, armed by the perfusion number.

    Not a new mechanism: the same table, the same _rule_armed, the same appended
    line and the same SAFE -> NEEDS_HUMAN_REVIEW downgrade.
    """
    cautions = v.conflicts("Give fentanyl 50 mcg IV for pain.", armed_map("BP 90/30"))
    assert len(cautions) == 1
    assert "fentanyl" in cautions[0]
    assert "MAP is 50" in cautions[0]


def test_a_low_map_catches_the_pressure_a_systolic_threshold_misses():
    """90/30 is the query that prompted this. SBP 90 is not below 90, so the
    systolic rule stays silent — and the patient has a MAP of 50."""
    readings = armed_map("BP 90/30")
    assert readings["sbp"].value == 90
    assert v._rule_armed({"when": {"sbp": {"lt": 90}}}, readings) is None
    assert v.conflicts("Give midazolam 2mg IV.", readings)


def test_a_narrow_map_and_a_low_systolic_say_it_once():
    """82/40 arms both rules. They are one caution with two ways to arm, and a
    warning repeated in two sentences that differ only in which number they
    quote is how a caution stops being read."""
    cautions = v.conflicts("Give fentanyl 50 mcg IV.", armed_map("BP 82/40"))
    assert len(cautions) == 1
    assert "SBP is 82" in cautions[0], "first armed rule in table order speaks"


def test_a_stated_map_arms_the_caution_too():
    """The rule reads the vital, not where it came from."""
    stated, _ = v.merge({}, parse("MAP 50", ts=T0)[0])
    assert v.conflicts("Give propofol.", stated)


def test_no_caution_when_the_map_is_adequate():
    assert v.conflicts("Give fentanyl 50 mcg IV.", armed_map("BP 100/48")) == []


def test_the_two_hypotension_rules_cover_the_same_agents():
    """They are one caution. A drug added to one list and not the other would
    make the warning depend on which threshold happened to arm."""
    lists = [frozenset(r.get("drugs", [])) for r in v.CAUTIONS
             if r.get("group") == "hypotension"]
    assert len(lists) == 2, "expected a systolic rule and a MAP rule"
    assert len(set(lists)) == 1, "the two hypotension rules list different drugs"


def test_no_caution_when_the_vital_is_normal():
    assert v.conflicts("Give fentanyl 50 mcg IV.", armed("BP 130/80")) == []
    assert v.conflicts("Give midazolam 2mg IV.", armed("RR 16")) == []


def test_no_caution_when_the_vital_was_never_recorded():
    """Absence of a vital is not a normal vital.

    The system does not know the blood pressure and must not reason as though it
    were fine — but an unrecorded vital is not evidence of a conflict either, so
    it says nothing.
    """
    assert v.conflicts("Give fentanyl 50 mcg IV.", armed("HR 88")) == []
    assert v.conflicts("Give fentanyl 50 mcg IV.", {}) == []


def test_ketamine_is_not_cautioned_on_haemodynamic_or_respiratory_grounds():
    """Deliberate. Ketamine is the favourable agent on both axes.

    Cautioning it would push a medic toward the drug the caution exists to warn
    about. Pinned so a future edit to vitals_rules.json cannot add it quietly.
    """
    assert v.conflicts("Draw 0.24 mL of 100mg/mL ketamine IV (24mg).",
                       armed("BP 82/40")) == []
    assert v.conflicts("Give ketamine for analgesia.", armed("sats 86 RR 8")) == []


def test_a_drug_name_inside_a_longer_word_does_not_fire():
    assert v.conflicts("No nitroglycerinated compounds here.", armed("BP 82/40")) == []


def test_one_caution_per_rule():
    """Two flagged drugs in one response produce one line, not a wall of them."""
    cautions = v.conflicts("Give fentanyl and midazolam.", armed("BP 82/40"))
    assert len(cautions) == 1


def test_cautions_never_mention_a_dose():
    """Vitals inform cautions and context only; they never authorise a number."""
    import re
    for text, vit in (("Give fentanyl 50 mcg IV.", "BP 82/40"),
                      ("Give midazolam 2mg IV.", "RR 6"),
                      ("Give diltiazem.", "HR 42")):
        for caution in v.conflicts(text, armed(vit)):
            assert not re.search(r'\d+\s*(mg|mcg|ml)\b', caution.lower()), caution


# ── config degradation ──────────────────────────────────────────────────────

def test_missing_rules_file_falls_back_to_builtin_ranges(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(v, "_RULES_PATH", tmp_path / "absent.json")
    assert v._load_rules() is v._BUILTIN_RULES
    assert "not found" in capsys.readouterr().out


def test_builtin_fallback_has_no_cautions_and_all_ranges():
    """The safe direction on both counts.

    Without a range a vital cannot be validated, so the parser must not fall
    back to accepting anything. Cautions only add warnings, so an empty list
    degrades to "no warnings" and never to a released response.
    """
    assert v._BUILTIN_RULES["cautions"] == []
    assert set(v._BUILTIN_RULES["ranges"]) == set(v.VITAL_ORDER)


def test_an_old_rules_file_still_arms_its_temperature_caution():
    """vitals_rules.json is meant to be edited by a clinician, and an edited
    copy outlives a deploy. A `temp_c` key from before the rename is renamed on
    load rather than ignored: a caution that silently stops arming is the one
    failure mode this table must not have."""
    raw = {"ranges": {"temp_c": {"label": "Temp", "unit": "C", "min": 35, "max": 43,
                                 "alt_unit": "F", "alt_min": 93, "alt_max": 110}},
           "cautions": [{"id": "legacy", "when": {"temp_c": {"lt": 35}},
                         "drugs": ["txa"],
                         "caution": "The recorded temperature is {temp_c}C."}]}
    v._rename_legacy_temp(raw)
    assert "temp" in raw["ranges"] and "temp_c" not in raw["ranges"]
    assert raw["cautions"][0]["when"] == {"temp": {"lt": 35}}
    assert "{temp}" in raw["cautions"][0]["caution"]


def test_every_caution_rule_names_a_known_vital_or_flag():
    """A `when` key must name a measurement in RANGES or a declared patient flag.

    Both halves matter. An unknown vital name never arms, so the rule is dead
    config that reads as live protection; and a flag that is not in
    PATIENT_FLAGS is the same defect wearing different clothes.
    """
    for rule in v.CAUTIONS:
        for name in (rule.get("when") or {}):
            assert name in v.RANGES or name in v.PATIENT_FLAGS, (
                f"{rule.get('id')} tests unknown vital/flag {name}")
        assert rule.get("drugs"), f"{rule.get('id')} has no drugs"
        assert rule.get("caution"), f"{rule.get('id')} has no caution text"


def test_every_caution_template_formats():
    """A template naming a field the rule does not arm would raise at runtime."""
    for rule in v.CAUTIONS:
        fields = {name: "0" for name in (rule.get("when") or {})}
        rule["caution"].format(drug="testdrug", **fields)


def test_a_flag_rule_arms_without_any_reading():
    """The point of PATIENT_FLAGS: no measurement, still armed."""
    assert v._rule_armed({"when": {"ams_stated": {"is": True}}}, {},
                         {"ams_stated": True}) == {}
    assert v._rule_armed({"when": {"ams_stated": {"is": True}}}, {},
                         {"ams_stated": False}) is None
    assert v._rule_armed({"when": {"ams_stated": {"is": True}}}, {}, {}) is None


# ── end to end through the real pipeline ────────────────────────────────────

class FakeChroma:
    def __init__(self, distance=0.2):
        self.distance = distance

    def query(self, text, n_results=5):
        return {"documents": [["JTS analgesia protocol text"]],
                "metadatas": [[{"source": "JTS Analgesia", "page": 4}]],
                "distances": [[self.distance]]}


@pytest.fixture
def stub_llm(monkeypatch):
    calls = {}

    def fake_chat(system, messages, *, model, temperature=0.2, max_tokens=700):
        calls.setdefault("systems", []).append(system)
        if "Clinical Safety Validator" in system:
            return '{"result": "SAFE", "issues": [], "rationale": ""}'
        return calls.get("reply", "Reassess the patient and monitor closely.")

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    return calls


def run(query, history=None, now=T9, **kw):
    return oc._query_with_rag_internal(query, FakeChroma(),
                                       conversation_history=history or [], **kw)


def test_vitals_reach_the_generator_prompt(stub_llm):
    run("80kg male HR 128 BP 82/40 sats 91, analgesia options?")
    generator_prompt = stub_llm["systems"][0]
    assert "RECORDED VITALS" in generator_prompt
    assert "BP 82/40" in generator_prompt
    assert "never authorise a dose" in generator_prompt


def test_vitals_reach_the_validator(stub_llm):
    run("80kg male HR 128 BP 82/40 sats 91, analgesia options?")
    validator_prompt = next(s for s in stub_llm["systems"]
                            if "Clinical Safety Validator" in s)
    assert "VITALS CONFLICT" in validator_prompt


def test_a_conflicting_recommendation_gets_a_visible_caution(stub_llm):
    stub_llm["reply"] = "**GIVE**\n- Fentanyl 50 mcg IV for pain.\n"
    result = run("80kg male BP 82/40, analgesia options?")
    assert result["validator_result"] == "NEEDS_HUMAN_REVIEW"
    assert "VITALS CAUTION" in result["response"]
    assert result["vitals_cautions"], "the caution must be recoverable for the log"
    assert "82" in result["vitals_cautions"][0]


def test_no_caution_when_vitals_and_recommendation_agree(stub_llm):
    stub_llm["reply"] = "**GIVE**\n- Fentanyl 50 mcg IV for pain.\n"
    result = run("80kg male BP 130/80, analgesia options?")
    assert result["validator_result"] == "SAFE"
    assert "VITALS CAUTION" not in result["response"]
    assert result["vitals_cautions"] == []


def test_a_rejected_vital_is_surfaced_in_the_response(stub_llm):
    result = run("80kg male bp 400/300, analgesia options?")
    assert "Couldn't read that vital" in result["response"]
    assert "400/300" in result["response"]
    assert result["patient_context"]["vitals"] == {}


def test_the_response_carries_the_context_the_client_strip_renders(stub_llm):
    result = run("80kg male HR 128 BP 82/40 sats 91, analgesia options?")
    ctx = result["patient_context"]
    assert ctx["confirmed_weight_kg"] == 80.0
    assert ctx["vitals"]["sbp"]["value"] == 82
    assert ctx["vitals"]["sbp"]["ts"], "the strip needs a timestamp to show age"
    assert ctx["vitals"]["hr"]["value"] == 128


def test_pre_gate_responses_still_carry_context(stub_llm):
    """The strip must not go blank on a turn that returns before retrieval."""
    result = run("6yo BP 90/60, how much ketamine")
    assert result["source_mode"] in ("PRE_GATE", "DETERMINISTIC_PRE_GATE")
    assert result["patient_context"]["vitals"]["sbp"]["value"] == 90


def test_vitals_do_not_change_the_dose_contract(stub_llm):
    """Vitals inform cautions and context only.

    The ALLOWED_DOSES contract is built from weight and route. If a recorded
    blood pressure could move it, vitals would be computing doses.
    """
    ctx_with = oc.rebuild_patient_context_from_history(
        "80kg male BP 82/40 IV ketamine for pain", now_ts=T9)
    ctx_without = oc.rebuild_patient_context_from_history(
        "80kg male IV ketamine for pain", now_ts=T9)
    with_vitals = oc.build_allowed_doses("80kg male BP 82/40 IV ketamine for pain",
                                         ctx_with)
    without = oc.build_allowed_doses("80kg male IV ketamine for pain", ctx_without)
    assert [(d.drug, d.dose_mg, d.route) for d in with_vitals] == \
           [(d.drug, d.dose_mg, d.route) for d in without]
    assert with_vitals, "the contract should be non-empty for this query"


def test_the_log_records_vitals_state_and_cautions(stub_llm, tmp_path, monkeypatch):
    import json
    import pathlib as _pathlib
    stub_llm["reply"] = "**GIVE**\n- Fentanyl 50 mcg IV for pain.\n"
    monkeypatch.setattr(oc, "_LOG_DIR", _pathlib.Path(tmp_path))
    oc.query_with_rag("80kg male BP 82/40, analgesia options?", FakeChroma(),
                      conversation_history=[])
    entry = json.loads(sorted(tmp_path.glob("*.jsonl"))[0].read_text().strip())
    assert entry["log_schema"] == oc.LOG_SCHEMA_VERSION
    assert entry["vitals"]["sbp"]["value"] == 82
    assert entry["vitals_cautions"], "a fired caution must be in the log"
    assert entry["vitals_rejected"] == []


def test_the_log_records_what_was_superseded(stub_llm, tmp_path, monkeypatch):
    import json
    import pathlib as _pathlib
    monkeypatch.setattr(oc, "_LOG_DIR", _pathlib.Path(tmp_path))
    oc.query_with_rag("now BP 70/30", FakeChroma(),
                      conversation_history=[{"query": "BP 120/80", "ts": T0}])
    entry = json.loads(sorted(tmp_path.glob("*.jsonl"))[0].read_text().strip())
    changed = {s["name"]: s for s in entry["vitals_superseded"]}
    assert changed["sbp"]["from"]["value"] == 120
    assert changed["sbp"]["to"]["value"] == 70


def test_the_response_carries_the_derived_map_for_the_strip(stub_llm):
    """The strip renders it, so the response has to carry it — as a number, with
    the same shape as every other reading."""
    ctx = run("80kg male BP 90/30, treatment?")["patient_context"]
    assert ctx["vitals"]["map"]["value"] == 50.0
    assert ctx["vitals"]["map"]["derived"] is True
    assert set(ctx["vitals"]["map"]) >= {"value", "unit", "ts", "derived"}
    assert ctx["vitals"]["map"]["ts"], "the strip needs a timestamp to show age"


def test_the_log_records_the_map_and_says_it_was_derived(stub_llm, tmp_path, monkeypatch):
    """Per query, in the vitals block, flagged. "What did the system believe the
    MAP was when it said that" has to be answerable from the log alone — and so
    does "did anyone actually measure it"."""
    import json
    import pathlib as _pathlib
    monkeypatch.setattr(oc, "_LOG_DIR", _pathlib.Path(tmp_path))
    oc.query_with_rag("80kg male BP 90/30, analgesia options?", FakeChroma(),
                      conversation_history=[])
    entry = json.loads(sorted(tmp_path.glob("*.jsonl"))[0].read_text().strip())
    assert entry["vitals"]["map"]["value"] == 50.0
    assert entry["vitals"]["map"]["derived"] is True
    assert entry["vitals"]["sbp"]["derived"] is False


def test_a_stated_map_is_logged_as_stated(stub_llm, tmp_path, monkeypatch):
    import json
    import pathlib as _pathlib
    monkeypatch.setattr(oc, "_LOG_DIR", _pathlib.Path(tmp_path))
    oc.query_with_rag("art line reads MAP 70", FakeChroma(),
                      conversation_history=[{"query": "BP 90/30", "ts": T0}])
    entry = json.loads(sorted(tmp_path.glob("*.jsonl"))[0].read_text().strip())
    assert entry["vitals"]["map"]["value"] == 70.0
    assert entry["vitals"]["map"]["derived"] is False


def test_a_low_map_downgrades_a_safe_verdict(stub_llm):
    """The caution pathway, end to end and unchanged: it appends a visible line
    and softens SAFE. It does not block, and it cannot release."""
    stub_llm["reply"] = "**GIVE**\n- Fentanyl 50 mcg IV for pain.\n"
    result = run("80kg male BP 90/30, analgesia options?")
    assert "MAP is 50" in result["response"]
    assert result["validator_result"] == "NEEDS_HUMAN_REVIEW"
    assert result["vitals_cautions"]


# ── the live case, 2026-08-21 ───────────────────────────────────────────────

_LIVE_BP_TS = "2026-08-21T14:51:31.895Z"


def test_the_2026_08_21_soft_pressure_derives_a_red_map_and_arms_the_caution():
    """"Ok now his pressure is getting soft 90/50", logged 14:51:31Z.

    The pressure the medic actually typed, in the session that prompted this
    work. It is the case the systolic threshold cannot see: SBP 90 is not below
    90, so before MAP existed nothing armed and nothing on the strip was red —
    for a patient whose mean arterial pressure was 63 and who was 31 minutes
    later asked about vasopressors.
    """
    readings, rejections = v.parse_vitals("Ok now his pressure is getting soft 90/50",
                                          ts=_LIVE_BP_TS)
    assert rejections == []
    merged_state, _ = v.merge({}, readings)

    assert merged_state["sbp"].value == 90 and merged_state["dbp"].value == 50
    assert merged_state["map"].value == 63          # (90 + 100) / 3 = 63.33
    assert merged_state["map"].derived is True
    assert merged_state["map"].ts == _LIVE_BP_TS, "the MAP is as old as the pressure"

    # Red on the strip: the client's threshold is strictly below 65.
    assert merged_state["map"].value < 65

    # The systolic rule stays silent; the MAP rule is what fires.
    assert v._rule_armed({"when": {"sbp": {"lt": 90}}}, merged_state) is None
    cautions = v.conflicts("Give fentanyl 50 mcg IV for pain.", merged_state)
    assert len(cautions) == 1
    assert "MAP is 63" in cautions[0]


def test_the_live_pressure_does_not_caution_the_drug_that_treats_it():
    """The same session asked "Help with the calculation to start norepi".

    Norepinephrine is deliberately absent from the hypotension drug list, for
    the reason ketamine is: it is the answer to a low MAP, not a risk at one,
    and cautioning it would push a medic away from the agent they need. Pinned
    so a future edit to vitals_rules.json cannot add it quietly.
    """
    readings, _ = v.parse_vitals("90/50", ts=_LIVE_BP_TS)
    merged_state, _ = v.merge({}, readings)
    assert merged_state["map"].value == 63
    assert v.conflicts("Start norepinephrine 0.05 mcg/kg/min IV.", merged_state) == []
    assert v.conflicts("Start a norepi drip.", merged_state) == []


def test_a_deterministic_card_gets_a_vitals_caution(stub_llm):
    """The cards bypass the gate by design. They still name cautioned drugs.

    build_seizure_response recommends lorazepam, build_cholera_response
    recommends oral fluids, and both DCR cards name TXA — so a feature that only
    covered the RAG path would silently not cover the four fixed strings most
    likely to conflict with a recorded vital.
    """
    result = run("status epilepticus, seizing 10 minutes, RR 6 sats 84")
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "lorazepam" in result["response"].lower()
    assert "VITALS CAUTION" in result["response"]
    assert result["validator_result"] == "NEEDS_HUMAN_REVIEW"


def test_a_deterministic_card_without_a_conflict_is_untouched(stub_llm):
    result = run("status epilepticus, seizing 10 minutes, RR 16 sats 98")
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "VITALS CAUTION" not in result["response"]
    assert result["validator_result"] == "SAFE"


def test_a_boundary_reset_on_a_pre_gate_turn_is_still_announced(stub_llm):
    """A gap in SC-1's coverage, closed on the way past.

    The notice was applied only on the RAG path, so a boundary turn that hit a
    pre-gate cleared the patient's context and said nothing about it. Option (c)
    was chosen precisely so that every reset is visible.
    """
    history = [{"query": "6yo 20kg BP 90/60", "ts": T0}]
    result = run("new patient — failed intubation failed igel desaturating",
                 history=history)
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "Starting a new patient" in result["response"]
    assert result["patient_context"]["vitals"] == {}


def test_a_rejected_vital_on_a_pre_gate_turn_is_still_surfaced(stub_llm):
    result = run("failed intubation failed igel desaturating, bp 400/300")
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "Couldn't read that vital" in result["response"]
