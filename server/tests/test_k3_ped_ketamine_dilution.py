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

def test_an_adult_dose_with_no_signed_dilution_is_unchanged(single_vial, gen):
    r = run("ketamine for pain, 75 kg IV")["response"]
    assert ADULT_DRAW in r, r
    assert "Dilute first" not in r, r


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
