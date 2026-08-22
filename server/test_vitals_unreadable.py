"""
F-4 — a newer vital that cannot be parsed must not pass for agreement.

Baseline evidence (runs/baseline-gpt4omini, scenario G-MTN-07):

    turn 1  "chest trauma from a fall, breathing hard, sat 96"
    turn 2  "he's satting 84 on room air now"
    vitals the answer was produced against:  spo2 = 96.0, raw "sat 96"
    vitals_superseded:                       []

The medic said 84. The system believed 96, recorded no supersession, and
answered against a saturation twelve points too high. Nothing in the response,
the context or the log showed that the newer number had been dropped.

Two fixes, and the second is the one that generalises: the label table gains
the verb form, AND a number beside a vital label that nothing can read now
lands in vitals_rejected and fires the existing visible notice.
"""
import pytest

import vitals as v
from openai_client import extract_patient_context


# ── the specific phrasing ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,value", [
    ("he's satting 84 on room air now", 84.0),
    ("satting 88", 88.0),
    ("he is sating 90", 90.0),
    ("sats are 91", 91.0),
    ("sat 96", 96.0),
    ("sats 91", 91.0),
    ("spo2 of 84%", 84.0),
])
def test_spo2_verb_and_connective_forms(text, value):
    readings, rejections = v.parse_vitals(text, ts=None)
    assert readings["spo2"].value == value, text
    assert rejections == [], text


def test_verb_form_supersedes_prior_reading():
    """G-MTN-07 end to end through the context builder."""
    ctx = extract_patient_context("chest trauma from a fall, breathing hard, sat 96")
    assert ctx.vitals["spo2"].value == 96.0

    ctx = extract_patient_context("he's satting 84 on room air now", prior_ctx=ctx)
    assert ctx.vitals["spo2"].value == 84.0, (
        "the newer saturation must displace the older one")
    assert [s["name"] for s in ctx.vitals_superseded] == ["spo2"]
    assert ctx.vitals_superseded[0]["from"]["value"] == 96.0
    assert ctx.vitals_superseded[0]["to"]["value"] == 84.0


# ── the general fix: an unreadable vital is visible, not silent ─────────────

def test_unparsed_vital_adjacent_number_is_rejected_visibly():
    """The backstop. The label table is where a phrasing SHOULD be read; this
    is what guarantees that failing to read one cannot pass for agreement."""
    readings, rejections = v.parse_vitals("his sats dropped to 88", ts=None)
    assert "spo2" not in readings
    assert [r.name for r in rejections] == ["unreadable"]
    assert "88" in rejections[0].raw
    assert "Couldn't read that vital" in v.rejection_notice(rejections)


def test_an_unreadable_newer_vital_does_not_leave_the_old_one_looking_agreed():
    """The S-1 shape, in a new field.

    The stale value legitimately persists — one unreadable turn does not mean
    the patient no longer has a saturation. What must NOT happen is that it
    persists silently.
    """
    ctx = extract_patient_context("sat 96")
    ctx = extract_patient_context("his sats dropped to 88", prior_ctx=ctx)
    assert ctx.vitals["spo2"].value == 96.0, "stale value legitimately persists"
    assert ctx.vitals_rejected, "but the medic must be told it was not read"
    notice = v.rejection_notice(ctx.vitals_rejected)
    assert "Couldn't read that vital" in notice
    assert "88" in notice


def test_the_sweep_is_quiet_on_ordinary_prose():
    """A notice that fires on ordinary text is a notice nobody reads — the same
    failure mode the caution table's narrowness exists to avoid.

    Measured over all 186 queries in the eval bank: zero notices. These are the
    phrasings that produced false positives before the sweep's label set was
    tightened, every one of them from the bare "t" in the temperature label.
    """
    for text in ("managing this patient for the next 4 to 10 hours",
                 "the first 2 casualties",
                 "severe tbi 5 minutes out",
                 "what does a rising end tidal co2 tell me",
                 "fever for 2 days",
                 "tourniquet on for 4 hours",
                 "give 500 mg of cefazolin",
                 "he is 6 years old and weighs 20 kg"):
        readings, rejections = v.parse_vitals(text, ts=None)
        assert not [r for r in rejections if r.name == "unreadable"], (
            f"{text!r} produced a spurious unreadable-vital notice: "
            f"{[r.raw for r in rejections]}")


def test_a_readable_vital_never_also_reports_unreadable():
    """The sweep only claims spans nothing else consumed."""
    readings, rejections = v.parse_vitals(
        "34yo male HR 128 BP 82/40 sats 91 RR 28 GCS 14 temp 35.1", ts=None)
    assert len(readings) == 7
    assert rejections == []


def test_an_out_of_range_vital_still_reports_its_own_reason():
    """The sweep must not swallow the more specific rejection.

    "temp 50" is a temperature the parser READ and refused; that is a different
    message from one it could not read at all, and the medic needs the
    difference.
    """
    rejections = v.parse_vitals("temp 50", ts=None)[1]
    assert [r.name for r in rejections] == ["temp"]
    assert "either unit" in rejections[0].reason


def test_the_sweep_covers_every_label_the_parser_knows():
    """A label added to the parser is swept for automatically.

    Pinned because the alternative — a hand-maintained second list — is the
    two-copies failure that S-6 and F-3 were both instances of.
    """
    import vitals
    assert vitals._SPO2_LABEL in vitals._ALL_VITAL_LABELS
    assert vitals._GLUCOSE_LABEL in vitals._ALL_VITAL_LABELS
    assert vitals._HR_LABEL in vitals._ALL_VITAL_LABELS
    # Temperature is the one deliberate exception, and it is a narrowing.
    assert vitals._TEMP_LABEL not in vitals._ALL_VITAL_LABELS
    assert vitals._TEMP_LABEL_SWEEP in vitals._ALL_VITAL_LABELS
    assert "|t)" not in vitals._TEMP_LABEL_SWEEP
