"""Signing batch 3, the last: the owner's rulings (2026-10-21).

Owner, 2026-10-21 (Andrew Azelton, signer), on the batch 3 review packet
(docs/authoring/SIGNING_BATCH3_PACKET_2026-10-21.pdf): "Apply exactly; sign
nothing not listed." Signed by AI-AIM for him, with set_contract.py:

- SIGN E05, E06, E10, E11, E13 (relabelled), E16, E17 (relabelled), E18, E19
  (split: calcium chloride 1 g, calcium gluconate 3 g), E20 (adult only),
  E21, E23, E27, U01, U02, U03 (split: chest, maxillofacial), U04-U12.
- RETIRE E01, E03 (batch 1 covers ketamine IM, adult and paediatric), E04,
  E07, E08, E12, E22, E24-E26, E28-E42 (E31's product entries to v1.1), and
  the paediatric half of E20: out of the bank, into retired_entries, recorded
  in UNSIGNED_CONTRACTS.
- DEFER E02, E09, E14, E15: unsigned, holding. P1 and P2 stay unsigned holds.

Every signed label must land in an indication class (#165), and no label
signed before this batch may change class: a class is what the dose check
narrows to (A32), so a new label in an old class is a dose that class accepts.

The verbatim check reads the PDFs, which are not in the repository. Point
JTS_PDF_DIR at the JTS/SMOG corpus; without it that test skips.

    cd server && ./run_unit_tests.sh
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts  # noqa: E402
import openai_client as oc  # noqa: E402
import procedure_contracts  # noqa: E402

SERVER = pathlib.Path(__file__).resolve().parents[1]
PDF_DIR = pathlib.Path(os.environ.get("JTS_PDF_DIR", SERVER / "data/jts_protocols"))
RULING = "OWNER RULING 2026-10-21 (Andrew Azelton)"
DATE = "2026-10-21"

MIDAZ_PACING = "procedural sedation for pacing / cardioversion"
PROPOFOL_INDUCTION = "induction of anaesthesia, hypotensive trauma patient (reduced dose)"
TRANSFUSION = "hypocalcaemia after massive transfusion"
CEFAZ_BRAIN = "penetrating brain injury (post-injury antimicrobial prophylaxis)"
CEFAZ_SPINE = "penetrating spinal cord injury (post-injury antimicrobial prophylaxis)"
CEFAZ_CHEST = "penetrating chest injury without esophageal disruption (post-injury prophylaxis)"
CEFAZ_FACE = "open maxillofacial fracture (post-injury prophylaxis)"
CEFAZ_PRESURG = "single pre-surgical dose for open wounds (Role 1 / Role 2 without surgical support)"
CEFAZ_VENTRIC = "ventriculostomy in place (prophylaxis)"
CEFTRI_TBI = "open or penetrating TBI (CNS-penetrating antimicrobial prophylaxis)"
CEFTRI_TBI_PEDS = "penetrating TBI / CNS injury (post-injury prophylaxis)"
CEFTRI_COVID = "severe COVID-19 with possible bacterial pneumonia co-infection"


def _r(lo, hi, units, per_kg=False):
    return {"min": lo, "max": hi, "units": units, "per_kg": per_kg}


# key -> (dose_range, max_single value or None, max_cumulative value or None,
#         [(citation marker, printed page)], [serve-tier substrings])
SIGNED = {
    # E05
    ("epinephrine", "push-dose vasopressor for hypotension", "adult", "IV"): (
        _r(5.0, 20.0, "mcg"), None, None,
        [("CPG ID83", 24), ("SMOG", 12)], ["every 2-5 minutes", "10 mcg/mL"]),
    # E06
    ("epinephrine", "infusion for refractory shock", "adult", "IV"): (
        _r(2.0, 10.0, "mcg/min"), None, None,
        [("CPG ID83", 24), ("CPG ID91", 40), ("SMOG", 114)],
        ["4 mcg/min", "30 mL/kg", "MAP 65"]),
    # E10
    ("ertapenem", "penetrating abdominal injury", "adult", "IV"): (
        _r(1.0, 1.0, "g"), None, None,
        [("CPG ID24", 11), ("CPG ID24", 12)], ["One dose", "10 days"]),
    # E11
    ("moxifloxacin", "combat wound prophylaxis (oral)", "adult", "PO"): (
        _r(400.0, 400.0, "mg"), None, None,
        [("CPG ID24", 12), ("CPG ID62", 24), ("SMOG", 64)], ["One dose", "10 days"]),
    # E13, relabelled
    ("midazolam", MIDAZ_PACING, "adult", "IV"): (
        _r(2.5, 5.0, "mg"), None, None,
        [("SMOG", 140)], ["15-30 minutes", "shock", "analgesic"]),
    # E16
    ("dextrose", "neonatal hypoglycaemia", "peds", "IV"): (
        _r(0.5, 0.5, "g/kg", True), 25.0, None,
        [("SMOG", 105)], ["5 mL/kg", "D10"]),
    # E17, relabelled
    ("propofol", PROPOFOL_INDUCTION, "adult", "IV"): (
        _r(0.5, 1.0, "mg/kg", True), None, None,
        [("CPG ID40", 3)], ["hypotensive"]),
    # E18
    ("propofol", "sedation infusion", "adult", "IV"): (
        _r(10.0, 75.0, "mcg/kg/min", True), None, None,
        [("SMOG", 12), ("SMOG", 153), ("CPG ID30", 22)],
        ["definitive airway", "100 mcg/kg/min"]),
    # E19, split by salt
    ("calcium chloride", TRANSFUSION, "adult", "IV"): (
        _r(1.0, 1.0, "g"), None, None,
        [("CPG ID18", 9), ("CPG ID73", 8), ("SMOG", 16)],
        ["first unit", "every 4 units", "1.2 mmol/L"]),
    ("calcium gluconate", TRANSFUSION, "adult", "IV"): (
        _r(3.0, 3.0, "g"), None, None,
        [("SMOG", 16), ("SMOG", 102)],
        ["first unit", "every 4 units", "1.2 mmol/L"]),
    # E20, the adult half
    ("naloxone", "opioid-induced respiratory depression", "adult", "IN"): (
        _r(0.4, 2.0, "mg"), None, 10.0,
        [("CPG ID61", 13)], ["2-3 minutes", "10 mg"]),
    # E21
    ("phytomenadione", "warfarin reversal", "adult", "IV"): (
        _r(10.0, 10.0, "mg"), None, None,
        [("Stroke", 12)], ["prothrombin complex concentrate"]),
    # E23
    ("artesunate", "severe malaria", "adult", "IV"): (
        _r(2.4, 2.4, "mg/kg", True), None, None,
        [("CPG ID83", 8)], ["0, 12, 24 and 48 hours", "Coartem or Malarone", "medevac"]),
    # U01
    ("cefazolin", CEFAZ_BRAIN, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID24", 11), ("SMOG", 64), ("CPG ID30", 7)],
        ["6-8 hours", "5 days or until the CSF leak is closed, whichever is longer"]),
    # U02
    ("cefazolin", CEFAZ_SPINE, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID24", 12), ("SMOG", 64)], ["6-8 hours", "surgical team"]),
    # U03, split
    ("cefazolin", CEFAZ_CHEST, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID24", 11), ("SMOG", 64)], ["6-8 hours for 24 hours"]),
    ("cefazolin", CEFAZ_FACE, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID24", 11), ("SMOG", 64)], ["6-8 hours for 24 hours"]),
    # U04
    ("cefazolin", CEFAZ_PRESURG, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID24", 9)], ["One dose"]),
    # U05
    ("cefazolin", CEFAZ_VENTRIC, "adult", "IV"): (
        _r(1.0, 1.0, "g"), None, None,
        [("CPG ID30", 13), ("CPG ID30", 23)], ["Three times daily", "while the ventriculostomy"]),
    # U06
    ("ceftriaxone", CEFTRI_TBI, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID63", 8), ("CPG ID63", 20), ("CPG ID24", 11)], ["every 24 hours", "5 days"]),
    # U07: 100 mg/kg/day, served as one daily dose, capped at the adult 2 g
    ("ceftriaxone", CEFTRI_TBI_PEDS, "peds", "IV"): (
        _r(100.0, 100.0, "mg/kg", True), 2.0, 2.0,
        [("CPG ID24", 12), ("CPG ID63", 8)], ["daily total", "2 g in 24 hours"]),
    # U08
    ("ceftriaxone", CEFTRI_COVID, "adult", "IV"): (
        _r(2.0, 2.0, "g"), None, None,
        [("CPG ID85", 17)], ["every 24 hours"]),
    # U09
    ("midazolam", "procedural sedation (incl. cardioversion, transcutaneous pacing)", "peds", "IV"): (
        _r(0.05, 0.1, "mg/kg", True), None, None,
        [("SMOG", 140), ("SMOG", 47), ("SMOG", 50)], ["15-30 minutes"]),
    # U10
    ("midazolam", "procedural / conscious sedation", "peds", "IN"): (
        _r(0.2, 0.5, "mg/kg", True), 10.0, 10.0,
        [("SMOG", 140)], ["5 mg per nostril", "off-label"]),
    # U11
    ("midazolam", "post-intubation sedation bolus", "adult", "IV"): (
        _r(1.0, 4.0, "mg"), None, None,
        [("CPG ID61", 12)], ["every 5 minutes"]),
    # U12
    ("midazolam", "sedation / anxiolysis", "adult", "IM"): (
        _r(2.0, 4.0, "mg"), None, None,
        [("CPG ID91", 35)], ["IM is not recommended", "15-20 minutes"]),
}

# E27, ruled SIGN; the bank has no tablet unit (drug_contracts.classify_units
# fails closed on anything that is not a mass), so it cannot be served as
# "4 tablets". Left unsigned with the ruling written on it, for the owner.
SIGN_BLOCKED = {
    ("artemether + lumefantrine", "uncomplicated P. falciparum malaria", "adult", "PO"): "tablet",
}

RETIRED = [
    ("ketamine", "prolonged sedation infusion — SMOG (en route)", "adult", "IV"),            # E01
    ("ketamine", "moderate to severe pain / analgesia", "adult|peds", "IM"),                 # E03
    ("ketamine", "moderate to severe pain / analgesia", "peds", "IN"),                       # E04
    ("rocuronium", "redose interval", "adult", "IV"),                                        # E07
    ("rocuronium", "redose interval", "peds", "IV"),                                         # E08
    ("ceftriaxone", "sepsis", "peds", "IV"),                                                 # E12
    ("phytomenadione", "haemorrhagic disease of the newborn — prophylaxis", "peds", "IM"),   # E22
    ("artesunate", "severe malaria", "peds", "IV"),                                          # E24
    ("artesunate", "severe malaria — pre-referral only", "adult|peds", "PR"),                # E25
    ("artemether", "severe malaria", "adult|peds", "IM"),                                    # E26
    ("artemether + lumefantrine", "uncomplicated P. falciparum malaria", "peds", "PO"),      # E28
    ("quinine", "severe malaria", "adult", "IV"),                                            # E29
    ("quinine", "severe malaria", "peds", "IV"),                                             # E30
    ("antivenom immunoglobulin", "envenoming", "adult|peds", "IV"),                          # E31
    ("oral rehydration salts", "cholera / acute watery diarrhoea — rehydration", "adult|peds", "PO"),  # E32
    ("zinc sulfate", "acute diarrhoea — adjunct to ORS", "peds", "PO"),                      # E33
    ("isoniazid", "drug-susceptible tuberculosis — first-line", "adult", "PO"),              # E34
    ("isoniazid", "drug-susceptible tuberculosis — first-line", "peds", "PO"),               # E35
    ("rifampicin", "drug-susceptible tuberculosis — first-line", "adult", "PO"),             # E36
    ("rifampicin", "drug-susceptible tuberculosis — first-line", "peds", "PO"),              # E37
    ("pyrazinamide", "drug-susceptible tuberculosis — first-line", "adult", "PO"),           # E38
    ("pyrazinamide", "drug-susceptible tuberculosis — first-line", "peds", "PO"),            # E39
    ("ethambutol", "drug-susceptible tuberculosis — first-line", "adult", "PO"),             # E40
    ("ethambutol", "drug-susceptible tuberculosis — first-line", "peds", "PO"),              # E41
    ("ethambutol + isoniazid + pyrazinamide + rifampicin",
     "drug-susceptible tuberculosis — intensive phase", "adult", "PO"),                     # E42
    ("naloxone", "opioid-induced respiratory depression", "peds", "IN"),                     # E20, peds half
]

DEFERRED = [
    ("ketamine", "prolonged sedation infusion", "peds", "IV"),                               # E02
    ("fentanyl", "analgesia infusion", "adult", "IV"),                                       # E09
    ("midazolam", "sedation infusion for the ventilated patient", "adult", "IV"),            # E14
    ("midazolam", "sedation infusion for the ventilated patient — ICU order set (fixed rate)",
     "adult", "IV"),                                                                         # E15
]

# The labels this batch replaced. None may be left in the bank.
GONE_LABELS = [
    ("midazolam", "procedural sedation — SMOG (pacing / cardioversion)"),
    ("propofol", "induction of anaesthesia"),
    ("naloxone", "opioid-induced respiratory depression", "adult|peds", "IN"),
]

_ids = lambda k: "-".join(k[::2]) + "-" + k[1][:18]


def _bank():
    return json.loads((SERVER / "drug_contracts.json").read_text())


def _drugs():
    return {d["generic_name"]: d for d in _bank()["drugs"]}


def _find(drug, indication, population, route):
    d = _drugs().get(drug)
    if d is None:
        return [], None
    return [e for e in d["dose_entries"]
            if (e["indication"], e["population"], e["route"]) == (indication, population, route)], d


def _entry(*key):
    hits, d = _find(*key)
    assert len(hits) == 1, (key, len(hits))
    return hits[0], d


def _serve(e):
    return drug_contracts.serve_cautions(e)


def _value(limit):
    return limit.get("value") if isinstance(limit, dict) else None


# ── Signed ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", list(SIGNED), ids=_ids)
def test_the_ruled_entries_are_signed_and_servable(key):
    e, d = _entry(*key)
    assert e["signoff"] is True and e["reviewed_by"] == "AI-AIM" and e["review_date"] == DATE, key
    assert not e["version"].endswith("-draft"), e["version"]
    ok, why = drug_contracts.entry_is_servable(e, d)
    assert ok, (key, why)
    assert e["adjudication"].startswith(RULING), e.get("adjudication")
    assert e["adjudicated_on"] == DATE


@pytest.mark.parametrize("key", list(SIGNED), ids=_ids)
def test_the_signed_dose_is_the_ruled_dose(key):
    e, _ = _entry(*key)
    rng, max_single, max_cum, _, _ = SIGNED[key]
    assert e["dose_range"] == rng, (key, e["dose_range"])
    assert _value(e.get("max_single")) == max_single, (key, e.get("max_single"))
    assert _value(e.get("max_cumulative")) == max_cum, (key, e.get("max_cumulative"))


@pytest.mark.parametrize("key", list(SIGNED), ids=_ids)
def test_the_ruled_citations_are_on_the_entry(key):
    e, _ = _entry(*key)
    for marker, page in SIGNED[key][3]:
        assert any(marker in s["citation"] and s.get("page") == page for s in e["sources"]), \
            (key, marker, page, [(s["citation"][-60:], s.get("page")) for s in e["sources"]])


@pytest.mark.parametrize("key", list(SIGNED), ids=_ids)
def test_the_ruled_watch_lines_serve_with_the_dose(key):
    e, _ = _entry(*key)
    served = " ".join(_serve(e))
    for text in SIGNED[key][4]:
        assert text in served, (key, text, _serve(e))


@pytest.mark.parametrize("key", list(SIGNED), ids=_ids)
def test_every_source_carries_a_printed_page_and_a_quote(key):
    e, _ = _entry(*key)
    for s in e["sources"]:
        if s.get("tier") == 2:          # the WHO EML form records, kept as they were
            continue
        assert isinstance(s.get("page"), int) and s["page"] > 0, s
        assert isinstance(s.get("pdf_page"), int) and s["pdf_page"] > 0, s
        assert f"p.{s['page']}" in s["citation"], s["citation"]
        assert s.get("quote", "").strip() and s.get("supports"), s


def test_the_split_and_relabelled_labels_are_gone():
    for g in GONE_LABELS:
        drug, label = g[0], g[1]
        hits = [e for e in _drugs()[drug]["dose_entries"] if e["indication"] == label
                and (len(g) == 2 or (e["population"], e["route"]) == g[2:])]
        assert not hits, g


def test_calcium_chloride_is_its_own_drug_and_the_bare_word_calcium_names_no_salt():
    """The salts differ threefold and are now signed at different doses (1 g
    chloride, 3 g gluconate, both for transfusion), so the bare word 'calcium'
    no longer means calcium gluconate. The alias lint refuses it anyway: an
    alias may not word-match inside another drug's name. Each salt is named
    by name; a dose stated for bare 'calcium' is recognised and holds."""
    for name in ("calcium chloride", "calcium gluconate"):
        assert "calcium" not in [a.lower() for a in _drugs()[name]["aliases"]]
    assert drug_contracts.ALIAS_COLLISIONS == []
    assert drug_contracts.resolve_drugs("calcium chloride 1 g after the first unit") == ["calcium chloride"]
    assert drug_contracts.resolve_drugs("calcium gluconate after 4 units of blood") == ["calcium gluconate"]
    assert drug_contracts.resolve_drugs("calcium after 4 units of blood") == []
    q = "80 kg adult, hemorrhagic shock, 4 units of whole blood in, calcium dose"
    issues = _issues(q, "**GIVE**\n- Calcium 1 g IV/IO slow push.")
    assert any("calcium" in i.lower() for i in issues), issues


def test_paediatric_ceftriaxone_is_capped_at_the_adult_dose():
    """100 mg/kg/day, divided every 12-24 hours (ID24 p.12), served as one dose
    every 24 hours; never above the adult 2 g in 24 hours (ID63 p.8)."""
    e, _ = _entry("ceftriaxone", CEFTRI_TBI_PEDS, "peds", "IV")
    assert drug_contracts.resolve_dose(e, 30.0)["dose_mg"] == 2000.0
    assert drug_contracts.resolve_dose(e, 12.0)["dose_mg"] == 1200.0


# ── Ruled SIGN, not signable as written ─────────────────────────────────────

@pytest.mark.parametrize("key", list(SIGN_BLOCKED), ids=_ids)
def test_a_sign_ruling_the_bank_cannot_serve_stays_unsigned_with_the_reason(key):
    e, _ = _entry(*key)
    assert e["signoff"] is False
    assert e["adjudication"].startswith(RULING) and "SIGN" in e["adjudication"]
    assert SIGN_BLOCKED[key] in e["adjudication"]


# ── Retired ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", RETIRED, ids=_ids)
def test_the_retired_entries_leave_the_bank_and_are_recorded(key):
    hits, _ = _find(*key)
    assert not hits, key
    rec = [r for r in _bank()["retired_entries"]
           if (r["generic_name"], r["indication"], r["population"], r["route"]) == key]
    assert len(rec) == 1, key
    assert rec[0]["retired_on"] == DATE and rec[0]["retired_reason"].startswith(RULING), rec[0]


def test_e03_is_covered_by_batch_1s_signed_ketamine_im():
    """Owner: retire E03 'confirm first that batch 1 covers adult and peds
    ketamine IM'. It does: both are signed and servable."""
    live = drug_contracts.servable_entries()["ketamine"]
    im = {(e["population"], e["indication"]) for e in live if e["route"] == "IM"}
    assert ("adult", "breakthrough pain — IM/IN (prolonged field care)") in im
    assert ("peds", "moderate to severe pain / analgesia") in im


def test_a_drug_with_every_entry_retired_is_still_recognised_and_its_dose_holds():
    """Retiring an entry must not make its drug unknown: a dose beside a name
    the check does not know passes. The drug stays in the bank, with no entry."""
    d = _drugs()["quinine"]
    assert d["dose_entries"] == []
    q = "70 kg adult, severe malaria, quinine dose"
    ctx = oc.rebuild_patient_context_from_history(q)
    issues = oc.run_deterministic_checks(q, "**GIVE**\n- Quinine 1400 mg IV over 4 hours.",
                                         ctx, oc.build_allowed_doses(q, ctx)).issues
    assert any("quinine" in i.lower() for i in issues), issues


# ── Deferred, and the procedure holds ───────────────────────────────────────

@pytest.mark.parametrize("key", DEFERRED, ids=_ids)
def test_the_deferred_entries_stay_unsigned_with_the_ruling(key):
    e, d = _entry(*key)
    assert e["signoff"] is False
    assert not drug_contracts.entry_is_servable(e, d)[0]
    assert f"{RULING}: DEFER" in e["extraction_notes"], e["extraction_notes"][-300:]


@pytest.mark.parametrize("row_id", ["P1", "P2"])
def test_p1_and_p2_stay_unsigned_holds(row_id):
    rows = json.loads((SERVER / "procedure_contracts.json").read_text())["rows"]
    row = next(r for r in rows if r["id"] == row_id)
    assert row["signoff"] is False
    assert row_id in procedure_contracts.inert_rows()
    assert f"{RULING}: hold" in row["extraction_notes"]


def test_unsigned_contracts_records_batch_3():
    doc = (SERVER.parent / "docs/UNSIGNED_CONTRACTS_2026-10-08.md").read_text()
    assert "## Signing batch 3 rulings (2026-10-21)" in doc
    section = doc.split("## Signing batch 3 rulings (2026-10-21)", 1)[1]
    for word in ("E01", "E42", "antivenom", "v1.1", "E02", "E09", "E14", "E15", "P1", "P2", "E27"):
        assert word in section, word


# ── Indication classes ──────────────────────────────────────────────────────

NEW_CLASSES = {
    "push-dose vasopressor for hypotension": "shock",
    "infusion for refractory shock": "shock",
    "penetrating abdominal injury": "wound infection prophylaxis",
    "combat wound prophylaxis (oral)": "wound infection prophylaxis",
    MIDAZ_PACING: "sedation",
    "neonatal hypoglycaemia": "hypoglycaemia",
    PROPOFOL_INDUCTION: "RSI",
    "sedation infusion": "sedation",
    TRANSFUSION: "hypocalcaemia",
    "warfarin reversal": "anticoagulant reversal",
    "severe malaria": "malaria",
    "uncomplicated P. falciparum malaria": "malaria",
    CEFAZ_BRAIN: "penetrating CNS injury",
    CEFAZ_SPINE: "penetrating CNS injury",
    CEFAZ_CHEST: "wound infection prophylaxis",
    CEFAZ_FACE: "wound infection prophylaxis",
    CEFAZ_PRESURG: "wound infection prophylaxis",
    CEFAZ_VENTRIC: "ventriculostomy",
    CEFTRI_TBI: "penetrating CNS injury",
    CEFTRI_TBI_PEDS: "penetrating CNS injury",
    CEFTRI_COVID: "pneumonia",
    "procedural sedation (incl. cardioversion, transcutaneous pacing)": "sedation",
    "procedural / conscious sedation": "sedation",
    "post-intubation sedation bolus": "sedation",
    "sedation / anxiolysis": "sedation",
}

# Every label signed before this batch, and its class (main, 24652bb).
BEFORE = [
    ('RSI induction', 'RSI'),
    ('RSI induction — haemodynamically unstable / in extremis', 'RSI'),
    ('RSI paralytic', 'RSI'),
    ('RSI paralytic — 5 years and above', 'RSI'),
    ('RSI paralytic — under 5 years', 'RSI'),
    ('RSI pre-dose — paediatric intubation', 'RSI'),
    ('active seizure', 'seizure'),
    ('acute pain / analgesia', 'pain'),
    ('acute pain / analgesia — JTS PFC fixed dose', 'pain'),
    ('agitated or violent patient / behavioural emergency', 'agitation'),
    ('agitated or violent patient — dissociative sedation', 'agitation'),
    ('anaphylaxis', 'anaphylaxis'),
    ('background pain — low-dose analgesia (prolonged field care)', 'pain'),
    ('breakthrough pain — IM/IN (prolonged field care)', 'pain'),
    ('bronchiolitis with severe respiratory distress — nebulised', 'bronchiolitis'),
    ('cardiac arrest', 'cardiac arrest'),
    ('cardiogenic shock / pulmonary oedema with SBP under 100', 'shock'),
    ('croup with stridor at rest — nebulised', 'croup'),
    ('hyperkalaemia — membrane stabilisation', 'hyperkalaemia'),
    ('mild to moderate pain / analgesia', 'pain'),
    ('moderate to severe pain / analgesia', 'pain'),
    ('neonatal resuscitation — HR below 60 despite ventilation', 'neonatal resuscitation'),
    ('nerve agent or organophosphate poisoning — autoinjector', 'poisoning'),
    ('nerve agent poisoning — escalating IV/IO bolus', 'poisoning'),
    ('ongoing sedation (prolonged field care)', 'sedation'),
    ('ongoing sedation — loading dose (infusion pump available)', 'sedation'),
    ('open fracture / wound prophylaxis', 'wound infection prophylaxis'),
    ('opioid-induced respiratory depression', 'opioid overdose'),
    ('organophosphate or carbamate poisoning', 'poisoning'),
    ('post-intubation sedation — repeated bolus (no infusion pump)', 'sedation'),
    ('procedural sedation', 'sedation'),
    ('prolonged sedation infusion', 'sedation'),
    ('refractory seizure (benzodiazepine-refractory)', 'seizure'),
    ('sepsis', 'sepsis'),
    ('severe TBI — seizure prophylaxis, loading dose', 'TBI seizure prophylaxis'),
    ('severe TBI — signs of herniation, bolus', 'TBI herniation'),
    ('shock unresponsive to IV fluids — infusion', 'shock'),
    ('shock — push dose', 'shock'),
    ('status epilepticus', 'seizure'),
    ('status epilepticus, refractory', 'seizure'),
    ('symptomatic bradycardia', 'bradycardia'),
    ('symptomatic bradycardia — infusion', 'bradycardia'),
    ('symptomatic bradycardia — push dose', 'bradycardia'),
    ('symptomatic hypoglycaemia', 'hypoglycaemia'),
    ('symptomatic hypoglycaemia — alert patient', 'hypoglycaemia'),
    ('traumatic haemorrhage', 'haemorrhage'),
    ('traumatic haemorrhage — loading dose', 'haemorrhage'),
    ('vasodilatory shock infusion', 'shock'),
    ('vasodilatory/haemorrhagic shock infusion', 'shock'),
]


@pytest.mark.parametrize("label,cls", list(NEW_CLASSES.items()))
def test_every_label_signed_in_batch_3_has_its_class(label, cls):
    assert oc.indication_class(label) == cls, (label, oc.indication_class(label))


@pytest.mark.parametrize("label,cls", BEFORE)
def test_no_label_signed_before_batch_3_changes_class(label, cls):
    assert oc.indication_class(label) == cls, (label, oc.indication_class(label))


# ── What the check does with them ───────────────────────────────────────────

def _issues(history, text):
    ctx = oc.rebuild_patient_context_from_history(history)
    return oc.run_deterministic_checks(history, text, ctx, oc.build_allowed_doses(history, ctx)).issues


SHOCK = "80 kg adult, BP 70/40 after 2 L of fluid, still in shock, epinephrine infusion rate"


def test_the_signed_epinephrine_shock_rate_serves():
    assert _issues(SHOCK, "**GIVE**\n- Epinephrine infusion: start at 4 mcg/min, titrate to MAP 65.") == []


def test_an_epinephrine_shock_rate_above_the_signed_range_holds():
    issues = _issues(SHOCK, "**GIVE**\n- Epinephrine infusion: start at 20 mcg/min.")
    assert any("epinephrine" in i and "20 mcg/min" in i for i in issues), issues


def test_the_ventriculostomy_dose_does_not_pass_for_an_open_fracture():
    """Cefazolin's 1 g is signed for a ventriculostomy only. An open fracture
    question accepts the 2 g, not the 1 g: A32 narrows to the stated class."""
    q = "80 kg adult, open tib fib fracture, cefazolin dose for infection prophylaxis"
    assert _issues(q, "**GIVE**\n- Cefazolin 2 g IV.") == []
    issues = _issues(q, "**GIVE**\n- Cefazolin 1 g IV.")
    assert any("cefazolin" in i.lower() for i in issues), issues


def test_a_bare_cefazolin_question_is_asked_which_indication():
    q = "80 kg adult, cefazolin dose"
    ctx = oc.rebuild_patient_context_from_history(q)
    asked = oc.which_indication_question(q, ctx)
    assert asked and "cefazolin" in asked and "ventriculostomy" in asked, asked


def test_calcium_chloride_after_transfusion_serves_and_the_gluconate_dose_is_not_it():
    q = "80 kg adult, hemorrhagic shock, 4 units of whole blood in, calcium chloride dose"
    assert _issues(q, "**GIVE**\n- Calcium chloride 1 g IV/IO slow push.") == []
    issues = _issues(q, "**GIVE**\n- Calcium chloride 3 g IV/IO slow push.")
    assert any("calcium chloride" in i.lower() for i in issues), issues


# ── Verbatim ────────────────────────────────────────────────────────────────

def _norm(t):
    return re.sub(r"\s+", " ", t).strip()


def _page_texts(pdf, page):
    """The page as text, whole and one half-page column at a time: SMOG prints
    ADULT and PEDIATRIC side by side, and a whole-page extraction interleaves them."""
    run = lambda *a: subprocess.run(["pdftotext", *a, "-f", str(page), "-l", str(page), str(pdf), "-"],
                                    capture_output=True, text=True, check=True).stdout
    width, height = 612, 792
    info = subprocess.run(["pdfinfo", "-f", str(page), "-l", str(page), str(pdf)],
                          capture_output=True, text=True).stdout
    m = re.search(rf"Page\s+{page} size:\s+([\d.]+) x ([\d.]+)", info)
    if m:
        width, height = int(float(m[1])), int(float(m[2]))
    half = width // 2
    texts = [run("-layout"), run()]
    for x in (0, half):
        crop = ["-x", str(x), "-y", "0", "-W", str(half), "-H", str(height)]
        texts += [run(*crop), run("-layout", *crop)]
    return [_norm(t) for t in texts]


@pytest.mark.skipif(shutil.which("pdftotext") is None or not PDF_DIR.is_dir(),
                    reason="the source PDFs (JTS_PDF_DIR) or pdftotext are not available")
@pytest.mark.parametrize("key", list(SIGNED), ids=_ids)
def test_every_quote_is_verbatim_on_its_cited_page(key):
    e, _ = _entry(*key)
    for s in e["sources"]:
        if not str(s.get("url", "")).startswith("local:server/data/jts_protocols/"):
            continue        # NASEMSO and WHO: not in the JTS corpus
        texts = _page_texts(PDF_DIR / s["url"].split("/")[-1], s["pdf_page"])
        for part in s["quote"].replace(" [sic]", "").split(" … "):
            assert any(_norm(part) in t for t in texts), (key, s["citation"], part)
