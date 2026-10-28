"""K3: a kit-vial volume under 0.5 mL is drawn from the signed dilution.

Owner, 2026-10-28: "If a 0.1 mL / 0.08 mL volume is shown with no dilution
instruction, the paediatric-dilution item comes off v1.1 and is fixed now,
failing test first: for a kit-vial volume under 0.5 mL, the answer gives the
signed dilution (ketamine 5 mg/mL: 1 mL of 50 mg/mL in 9 mL NS) and the volume
from the diluted strength."

Live, after the K1 declaration (run_tests.sh, 2026-10-28): a 6-year-old 20 kg
got "Draw 0.08 mL of 50mg/mL ketamine IV (4 mg) (kit vial)", the 25 kg child
"Draw 0.1 mL ...": the recipe was only a caution.

The dilution is the dose entry's own push_dilution (drug_contracts), signed
(AI-AIM, 2026-09-18). Only paediatric ketamine IV analgesia declares one, so
a dose with none (adult ketamine 18.75 mg = 0.375 mL) is unchanged.

    cd server && ./run_unit_tests.sh
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_concentrations as dcn  # noqa: E402
import drug_contracts  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402
import spoken  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
PED20 = "6 year old, 20kg, arm fracture, ketamine IV for pain"
PED25_HISTORY = [{"query": "need ketamine for a 6yo arm fx", "response": "Need weight in kg before dosing."},
                 {"query": "25kg", "response": "IV or IM? Do you have access?"}]
RECIPE = "Dilute first: 1 mL of 50mg/mL ketamine (kit vial) in 9 mL normal saline."
DRAW20 = "Draw 0.8 mL of 5mg/mL ketamine dilution IV (4 mg)."
DRAW25 = "Draw 1 mL of 5mg/mL ketamine dilution IV (5 mg)."
ADULT_DRAW = "Draw 0.375 mL of 50mg/mL ketamine IV (18.75 mg) (kit vial)."


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def single_vial(monkeypatch):
    """The live kit after K1: ketamine 500 mg / 10 mL is the one vial."""
    entries = copy.deepcopy(dcn.ENTRIES)
    k = entries["ketamine"]
    k["presentations"] = [p for p in k["presentations"] if p["label_text"] == "500 mg / 10 mL vial"]
    assert len(k["presentations"]) == 1 and dcn.presentation_is_signed(k["presentations"][0])
    k["confirm_required"] = False
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    return entries


@pytest.fixture
def gen(monkeypatch):
    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        return "STUB"
    monkeypatch.setattr(providers, "chat", chat)


def run(q, history=()):
    return oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(history))


def give_lines(r):
    return [l for l in r.split("\n") if l.strip().startswith("- Draw") or "NO VOLUME" in l]


# ── the two live failures ───────────────────────────────────────────────────

def test_the_20kg_child_gets_the_dilution_and_its_volume(single_vial, gen):
    r = run(PED20)["response"]
    assert DRAW20 + " " + RECIPE in r, r
    assert "0.08 mL" not in r and "0.08mL" not in r, r
    assert "safety hold" not in r.lower(), r


def test_the_25kg_child_gets_the_dilution_and_its_volume(single_vial, gen):
    r = run("ketamine IV for pain", PED25_HISTORY)["response"]
    assert DRAW25 + " " + RECIPE in r, r
    assert "0.1 mL of 50" not in r and "0.1mL of 50" not in r, r


def test_the_tldr_states_the_diluted_volume(single_vial, gen):
    r = run(PED20)["response"]
    assert "ketamine IV = 4mg = 0.8mL of 5mg/mL dilution (kit vial)." in r, r


def test_the_spoken_brief_says_dilute_then_draw(single_vial, gen):
    said = run(PED20)["spoken_brief"]
    assert said.startswith(
        "Give ketamine, four milligrams, intravenously. "
        "Dilute one millilitre of ketamine, fifty milligrams per millilitre, from your kit, "
        "in nine millilitres of normal saline. "
        "Draw zero point eight millilitres of the dilution."), said


# ── scope ───────────────────────────────────────────────────────────────────

# ── #195 ruling 1 (owner, 2026-10-28): the adult IV analgesia dilution ─────
# "Adult: same rule, any kit-vial volume under 0.5 mL gets the signed
# dilution. Sign the adult IV ketamine dilution as an owner declaration
# (Andrew Azelton, today): 1 mL of 50 mg/mL in 9 mL NS = 5 mg/mL, for IV
# analgesia only; so 75 kg gives 3.75 mL of 5 mg/mL. Failing test first;
# record in KIT_DECLARATIONS."

ADULT_DILUTED = "Draw 3.75 mL of 5mg/mL ketamine dilution IV (18.75 mg). " + RECIPE


def test_the_75kg_adult_gets_3_75_ml_of_the_dilution(single_vial, gen):
    r = run("ketamine for pain, 75 kg IV")["response"]
    assert ADULT_DILUTED in r, r
    assert ADULT_DRAW not in r and "0.375" not in r, r
    assert "ketamine IV = 18.75mg = 3.75mL of 5mg/mL dilution (kit vial)." in r, r


def test_an_adult_volume_of_half_a_millilitre_is_drawn_from_the_vial(single_vial, gen):
    r = run("ketamine for pain, 100 kg IV")["response"]
    assert "Draw 0.5 mL of 50mg/mL ketamine IV (25 mg) (kit vial)." in r, r
    assert "Dilute first" not in r, r


def _ketamine_entries():
    return [e for e in drug_contracts.servable_entries()["ketamine"]]


def test_the_adult_iv_analgesia_entries_carry_the_owner_declared_dilution():
    adult = [e for e in _ketamine_entries()
             if e["route"] == "IV" and "analgesia" in e["indication"] and e["population"] != "peds"]
    assert len(adult) == 2, [(e["population"], e["dose_range"]) for e in adult]
    for e in adult:
        dil = drug_contracts.push_dilution(e)
        assert dil is not None, e["population"]
        assert (dil["concentration_mg_ml"], dil["from_concentration_mg_ml"], dil["drug_ml"],
                dil["diluent_ml"], dil["diluent"]) == (5.0, 50.0, 1.0, 9.0, "normal saline")
        assert (dil["declared_by"], dil["declared_name"], dil["declared_on"]) == (
            "clinician", "Andrew Azelton", "2026-10-28")


def test_the_dilution_is_for_iv_analgesia_only():
    for e in _ketamine_entries():
        if e["route"] != "IV" or "analgesia" not in e["indication"]:
            assert drug_contracts.push_dilution(e) is None, (e["indication"], e["route"])


def test_kit_declarations_records_the_adult_dilution():
    import pathlib
    text = (pathlib.Path(__file__).resolve().parents[2] / "docs/authoring/KIT_DECLARATIONS.md").read_text()
    row = [l for l in text.splitlines() if l.startswith("| 2026-10-28 | ketamine | 5 mg/mL |")]
    assert len(row) == 1, row
    assert "1 mL of 50 mg/mL in 9 mL normal saline" in row[0]
    assert "adult IV analgesia" in row[0] and "Andrew Azelton (clinician)" in row[0], row[0]


# ── #195 ruling 2 (owner, 2026-10-28): a vial the medic states ─────────────
# "the dilution applies whenever the volume is under 0.5 mL and the vial (kit
# or stated) is the one the signed dilution is made from; a stated 500 mg/10
# mL for the 20 kg child gets 0.8 mL of 5 mg/mL. Failing test first."

STATED_RECIPE = "Dilute first: 1 mL of 50mg/mL ketamine in 9 mL normal saline."


@pytest.mark.parametrize("stated", ["I have 500 mg / 10 mL", "I have 50 mg/mL"])
def test_a_stated_vial_gets_the_dilution_too(single_vial, gen, stated):
    r = run(f"{PED20}, {stated}")["response"]
    assert DRAW20 + " " + STATED_RECIPE in r, r
    assert "0.08" not in r and "(kit vial)" not in r, r


def test_a_stated_vial_on_a_kit_that_asks_gets_the_dilution(gen):
    # The conftest kit asks which ketamine vial; the medic answers in the question.
    r = run(f"{PED20}, I have 500 mg / 10 mL")["response"]
    assert DRAW20 + " " + STATED_RECIPE in r, r


@pytest.fixture
def both_signed(monkeypatch):
    """The conftest kit with its 200 mg / 20 mL (10 mg/mL) vial signed too."""
    entries = copy.deepcopy(dcn.ENTRIES)
    for p in entries["ketamine"]["presentations"]:
        p.update(signoff=True, reviewed_by="clinician", review_date="2026-10-28")
    monkeypatch.setattr(dcn, "ENTRIES", entries)


def test_a_stated_vial_the_dilution_is_not_made_from_keeps_its_volume(both_signed, gen):
    # 4 mg of a signed 10 mg/mL vial is 0.4 mL; the recipe starts from 50 mg/mL.
    r = run(f"{PED20}, I have 200 mg / 20 mL")["response"]
    assert "Draw 0.4 mL of 10mg/mL ketamine IV (4 mg)." in r, r
    assert "Dilute first" not in r, r


def test_a_stated_vial_is_spoken_without_the_kit():
    _, said = spoken.dose_sentences(DRAW20 + " " + STATED_RECIPE, spoken._drug_index())
    assert said[1] == ("Dilute one millilitre of ketamine, fifty milligrams per millilitre, "
                       "in nine millilitres of normal saline.")


def _ped_candidate(dose_mg):
    entry = next(e for e in drug_contracts.servable_entries()["ketamine"]
                 if e.get("population") == "peds" and e.get("route") == "IV"
                 and drug_contracts.push_dilution(e))
    return oc.DoseCandidate(drug="ketamine", indication=entry["indication"], route="IV",
                            dose_mg=dose_mg, source="test",
                            dilution=drug_contracts.push_dilution(entry))


@pytest.mark.parametrize("dose_mg, diluted", [(24.5, True), (25.0, False), (4.0, True)])
def test_the_line_is_half_a_millilitre_at_the_vial(single_vial, dose_mg, diluted):
    d = oc.resolve_dose_volume(_ped_candidate(dose_mg), oc.PatientContext())
    assert (d.dilute_from is not None) == diluted
    if diluted:
        assert (d.volume_ml, d.concentration_mg_ml) == (round(dose_mg / 5, 3), 5.0)
    else:
        assert (d.volume_ml, d.concentration_mg_ml) == (0.5, 50.0)


def test_a_two_vial_kit_still_asks_first(gen):
    # The conftest kit asks which ketamine vial: no volume, no dilution, until told.
    r = run(PED20)["response"]
    assert "Dilute first" not in r and "5mg/mL ketamine dilution" not in r, r


# ── the volume audit: the diluted strength only as the signed dilution ─────

@pytest.fixture
def ped_ctx(single_vial):
    return oc.extract_patient_context(PED20)


@pytest.mark.parametrize("line, kept", [
    (DRAW20 + " " + RECIPE, True),
    ("Draw 0.8 mL of 5mg/mL ketamine IV (4 mg).", False),          # not named a dilution
    ("Draw 0.4 mL of 5mg/mL ketamine dilution IV (4 mg).", False),  # wrong arithmetic
    ("Draw 0.4 mL of 10mg/mL ketamine dilution IV (4 mg).", False), # not the signed dilution
    ("Draw 0.8 mL of 5mg/mL ketamine dilution IM (4 mg).", False),  # no IM dilution is signed
])
def test_the_audit_accepts_only_the_signed_dilution(ped_ctx, line, kept):
    text = "**GIVE**\n- " + line + " Indication: moderate to severe pain / analgesia."
    out, issues = oc.audit_volume_lines(text, ped_ctx)
    assert (issues == [] and out == text) == kept, (issues, out)


def test_the_audit_refuses_a_dilution_while_the_kit_asks_which_vial():
    ctx = oc.extract_patient_context(PED20)   # conftest kit: two ketamine vials
    text = "**GIVE**\n- " + DRAW20 + " Indication: moderate to severe pain / analgesia."
    _out, issues = oc.audit_volume_lines(text, ctx)
    assert issues, "a dilution starts from a vial; none is confirmed"


def test_the_spoken_dilution_sentence_is_a_fixed_template():
    _, said = spoken.dose_sentences(DRAW20 + " " + RECIPE, spoken._drug_index())
    assert said == ["Give ketamine, four milligrams, intravenously.",
                    "Dilute one millilitre of ketamine, fifty milligrams per millilitre, "
                    "from your kit, in nine millilitres of normal saline.",
                    "Draw zero point eight millilitres of the dilution."]


# ── a model answer that repeats the offered line ────────────────────────────
# The card is code-made; the generator is offered the same GIVE line
# (build_allowed_dose_block). Repeated verbatim it must not hold: the
# recipe's volumes are the signed dilution's own (owner, #181 review: "An mL
# serves when it comes from a confirmed vial OR from a signed entry's own
# recipe line"). Any other recipe or volume still holds.

@pytest.mark.parametrize("text, holds", [
    ("- " + DRAW20 + " " + RECIPE + " Indication: moderate to severe pain / analgesia.", False),
    ("Mix 2 mL of 50mg/mL ketamine in 8 mL normal saline.", True),     # not the signed recipe
    ("Mix 1 mL of 100mg/mL ketamine in 9 mL normal saline.", True),    # not the kit's vial
    ("Mix 1 mL of 50mg/mL ketamine in 9 mL normal saline, give 2 mL IV.", True),  # 2 mL follows from nothing
])
def test_the_signed_recipe_volumes_follow_from_the_dilution(ped_ctx, text, holds):
    assert bool(oc.unconfirmed_volume_issues(text, ped_ctx)) == holds


def test_no_recipe_volume_serves_while_the_kit_asks_which_vial():
    ctx = oc.extract_patient_context(PED20)   # conftest kit: two ketamine vials
    assert oc.unconfirmed_volume_issues(RECIPE, ctx)


def test_the_brief_keeps_the_per_kg_basis_and_the_recipe():
    import brief
    item = DRAW20 + " " + RECIPE + " Indication: moderate to severe pain / analgesia."
    assert brief.dose_line(item, weight_kg=20) == (
        "Draw 0.8 mL of 5mg/mL ketamine dilution IV (4 mg) (0.2 mg/kg × 20 kg). " + RECIPE)


def test_a_dilution_line_in_another_shape_is_never_spoken_as_the_vial():
    line = "Draw 0.8 mL of 5mg/mL ketamine dilution IV (4 mg). Dilute first: see cautions."
    _, said = spoken.dose_sentences(line, spoken._drug_index())
    assert said == ["Give ketamine, four milligrams, intravenously.", spoken.DILUTION_ON_SCREEN]


@pytest.mark.parametrize("stated, kept", [("500 mg / 10 mL", True), ("200 mg / 20 mL", False)])
def test_the_audit_takes_the_dilution_only_from_the_confirmed_vial_it_is_made_from(
        both_signed, stated, kept):
    ctx = oc.extract_patient_context(f"{PED20}, I have {stated}")
    text = "**GIVE**\n- " + DRAW20 + " " + STATED_RECIPE + " Indication: moderate to severe pain / analgesia."
    out, issues = oc.audit_volume_lines(text, ctx)
    assert (issues == [] and out == text) == kept, (issues, out)
