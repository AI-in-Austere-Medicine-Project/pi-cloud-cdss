"""A concentration in the question is the vial, never a requested dose.

Owner, 2026-10-23 (live finding, post-freeze): "Need to give ketamine. 75kg IV
established and we have a 500mg/10ml vial" was held as a 500 mg dose request.
The overdose pre-gate read "ketamine … 500mg" as the dose asked for. A
concentration phrase (N mg/N mL, N mg in N mL, N mg/mL; with or without "vial",
"amp", "ampule", "bag") in the question is a vial concentration, never a
requested dose. A dose stated outside such a phrase is still checked.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
LIVE = "Need to give ketamine. 75kg IV established and we have a 500mg/10ml vial"


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def seen(monkeypatch):
    out = {"allowed": None}
    real = oc.build_allowed_doses

    def build(history, ctx, **kw):
        doses = real(history, ctx, **kw)
        out["allowed"] = doses
        return doses

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        # The generator writes the first dose it is offered, as qwen does.
        d = out["allowed"][0]
        return (f"**GIVE**\n- {d.drug} {d.dose_mg:g} mg {d.route} "
                f"({d.volume_ml:g} mL of {d.concentration_mg_ml:g} mg/mL), "
                f"{d.indication}.\n")

    monkeypatch.setattr(oc, "build_allowed_doses", build)
    monkeypatch.setattr(providers, "chat", chat)
    return out


def run(query, history=None):
    return oc._query_with_rag_internal(query, _JtsHit(), conversation_history=history or [])


def test_the_live_query_stores_the_vial_concentration():
    ctx = oc.rebuild_patient_context_from_history(LIVE)
    assert ctx.confirmed_weight_kg == 75.0 and ctx.route_preference == "IV"
    assert ctx.confirmed_concentrations == {"ketamine": 50.0}


def test_the_live_query_is_not_a_dose_request():
    ctx = oc.rebuild_patient_context_from_history(LIVE)
    assert oc.detect_requested_medication_overdose(LIVE, ctx) == []


def test_the_live_query_is_not_held_and_asks_which_indication(seen):
    r = run(LIVE)
    assert r["response"].startswith("Which indication for ketamine"), r["response"]
    assert r["validator_result"] != "UNSAFE", r


def test_after_pain_the_signed_iv_analgesia_dose_is_served_in_mg_and_ml(seen):
    # Since 2026-10-24 the deterministic analgesia card answers "pain" here
    # (ketamine_analgesia_should_resume), not the model.
    first = run(LIVE)
    r = run("pain", [{"query": LIVE, "response": first["response"]}])
    resp = r["response"]
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", resp[:200]
    assert r["validator_result"] not in ("UNSAFE", "BLOCKED"), r
    # 0.375 mL at the vial: drawn from the signed 5 mg/mL dilution (K3; #195
    # ruling 1, owner, 2026-10-28).
    assert "Draw 3.75 mL of 5mg/mL ketamine dilution IV (18.75 mg)" in resp, resp
    assert "Indication: moderate to severe pain / analgesia" in resp


@pytest.mark.parametrize("q", [
    "ketamine drip, 80 kg, IV established, we have 1 mg in 250 mL bag",
    "Need ketamine for pain. 80kg IV. Have 1 mg in 250 mL bag",
])
def test_one_mg_in_a_250_ml_bag_is_not_a_dose_request(q):
    assert oc.requested_doses_mg(q) == []


@pytest.mark.parametrize("q", [
    "Need to give ketamine. 75kg IV established and we have a 500mg/10ml vial",
    "ketamine, 75 kg, IV, 500 mg / 10 mL",
    "ketamine, 75 kg, IV, 500 mg in 10 mL amp",
    "ketamine, 75 kg, IV, we have the 500 mg per 10 ml ampule",
    "ketamine, 75 kg, IV, 50 mg/mL vial",
    "ketamine, 75 kg, IV, 50mg per ml",
    "ketamine drip, 80 kg, mixing 500 mg in 250 mL bag",
    "rocuronium, 80 kg, 100mg/10ml vial",
    "succinylcholine, 80 kg, 200 mg / 10 mL",
])
def test_a_concentration_phrase_is_never_a_requested_dose(q):
    ctx = oc.rebuild_patient_context_from_history(q)
    assert oc.requested_doses_mg(q) == [], q
    assert oc.detect_requested_medication_overdose(q, ctx) == [], q


@pytest.mark.parametrize("q, drug", [
    ("80 kg adult, give ketamine 500 mg IV, we have a 500mg/10ml vial", "ketamine"),
    ("we have a 500mg/10ml vial, 80 kg adult, give ketamine 500 mg IV", "ketamine"),
    ("80 kg adult, give rocuronium 300 mg, 100mg/10ml vial", "rocuronium"),
    ("80 kg adult, give ketamine 500 mg over 10 minutes", "ketamine"),
])
def test_a_dose_outside_the_phrase_still_holds(q, drug):
    ctx = oc.rebuild_patient_context_from_history(q)
    issues = oc.detect_requested_medication_overdose(q, ctx)
    assert any(drug in i for i in issues), (q, issues)
