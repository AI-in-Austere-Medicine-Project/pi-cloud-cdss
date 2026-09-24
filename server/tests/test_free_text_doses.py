"""
EdgeCDSS — a dose stated outside the canonical GIVE line is still checked.

The regression: with CDSS_LLM_PROVIDER=local, qwen2.5:3b wrote "1 mg IV
fentanyl" for an 80 kg adult whose contract is fentanyl 80 mcg (12.5x), and its
own validator called that SAFE 5 times out of 5 (gpt-4o-mini: UNSAFE 3/3). The
deterministic check read only "Draw X mL of Y mg/mL drug (Z mg)", so nothing
else stood in the way. free_text_dose_issues() is that missing check; these
tests pin it, on the local path end to end and on its own.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

QUERY = "80 kg adult, IV access, fentanyl dose for pain"
FREELANCE = "**GIVE**\n- 1 mg IV fentanyl for pain.\n"
# What qwen2.5:3b's validator actually returned for FREELANCE, 5 runs of 5.
LOCAL_VALIDATOR_VERDICT = ('{"result": "SAFE", "issues": [], "rationale": "Response is '
                           'correct and within the allowed doses for fentanyl."}')


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["Pain management protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


def _ctx():
    return oc.PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                             route_preference="IV")


def _allowed():
    return oc.build_allowed_doses(QUERY, _ctx())


@pytest.fixture
def recorded(monkeypatch):
    """providers.chat stand-in: records every call, answers as `replies` says."""
    calls = []
    replies = {"generator": FREELANCE, "validator": LOCAL_VALIDATOR_VERDICT}

    def fake_chat(system, messages, *, model, temperature=0.2, max_tokens=700):
        role = "validator" if system == oc.VALIDATOR_PROMPT else "generator"
        calls.append({"role": role, "system": system, "messages": messages,
                      "model": model, "temperature": temperature,
                      "max_tokens": max_tokens})
        return replies[role]

    monkeypatch.setattr(providers, "chat", fake_chat)
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_MODEL", "CDSS_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return calls


# ── the regression, end to end on the local path ─────────────────────────────

def test_the_contract_is_what_the_regression_assumes():
    # 1 mcg/kg IN at 80 kg (NASEMSO), and since 2026-09-24 the 50 mcg IV fixed
    # dose (JTS PFC ID61). 1 mg is 12.5x the first and 20x the second.
    fentanyl = {(d.route, round(d.dose_mg, 6)) for d in _allowed() if d.drug == "fentanyl"}
    assert fentanyl == {("IN", 0.08), ("IV", 0.05)}, \
        f"the 80 kg fentanyl contract moved; re-derive the 12.5x case: {fentanyl}"
    assert all(1.0 / mg >= 12.5 for _, mg in fentanyl)


def test_local_1_mg_iv_fentanyl_is_blocked_even_when_the_validator_says_safe(
        monkeypatch, recorded):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    r = oc._query_with_rag_internal(QUERY, _JtsHit())
    assert [c["model"] for c in recorded] == ["qwen2.5:3b", "qwen2.5:3b"]
    assert r["validator_result"] == "UNSAFE"
    assert r["response"].startswith(oc.build_safety_hold([], "").split("\n")[0])
    assert "1 mg IV fentanyl" not in r["response"]
    assert any("fentanyl 1 mg" in i for i in r["validator_issues"]), r["validator_issues"]


def test_the_post_check_alone_blocks_it():
    det = oc.run_deterministic_checks(QUERY, FREELANCE, _ctx(), _allowed())
    assert det.passed is False
    assert det.issues == ["The answer stated fentanyl 1 mg, which is not the signed "
                          "fentanyl dose for this patient. Ask again for fentanyl "
                          "dosing to get the signed dose."]


def test_the_contract_reaches_the_local_generator_exactly_as_it_reaches_the_cloud(
        monkeypatch, recorded):
    oc._query_with_rag_internal(QUERY, _JtsHit())
    cloud = [dict(c) for c in recorded]
    recorded.clear()
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    oc._query_with_rag_internal(QUERY, _JtsHit())
    local = [dict(c) for c in recorded]

    assert [c["model"] for c in cloud] == ["gpt-4o-mini", "gpt-4o-mini"]
    assert [c["model"] for c in local] == ["qwen2.5:3b", "qwen2.5:3b"]
    block = oc.build_allowed_dose_block(_allowed())
    assert "fentanyl IN: 80 mcg" in block
    for c, l in zip(cloud, local):
        # Everything but the model: system prompt (with ALLOWED_DOSES in it),
        # every message, temperature and max_tokens.
        assert {k: v for k, v in c.items() if k != "model"} == \
            {k: v for k, v in l.items() if k != "model"}, c["role"]
    assert block in cloud[0]["system"], "ALLOWED_DOSES is not in the generator prompt"
    assert block in cloud[1]["messages"][-1]["content"], \
        "ALLOWED_DOSES is not in the validator's input"


# ── free_text_dose_issues on its own ─────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "**GIVE**\n- Give fentanyl 80 mcg IN.",                     # the contract dose
    "**TREAT**\n1. Give fentanyl 0.08 mg.",                      # same, in mg
    "**PREP**\n- Fentanyl 50 mcg/mL ampoule.",                   # a concentration
    "**CAUTIONS**\n- Max fentanyl 200 mcg cumulative.",          # a limit
    "**TREAT**\n1. Do not exceed fentanyl 300 mcg.",             # a limit
    "**DON'T**\n- Fentanyl 1 mg IV.",                            # DON'T section
    "**PREP**\n- Mix 4 mg norepinephrine in 250 mL NS.",         # a preparation
    "**GIVE**\n- Draw 1.6 mL of 50mg/mL ketamine IV (80 mg). Indication: x.",  # canonical
    "**TREAT**\n1. Give foobarol 5 mg.",                         # not a bank drug
    "**TREAT**\n1. Reassess in 5 min; pain score 8.",            # no drug
])
def test_what_is_not_a_freelanced_dose(text):
    assert oc.free_text_dose_issues(text, _allowed()) == [], text


def test_a_per_kg_dose_is_checked_at_the_patients_weight():
    """1 mcg/kg is a per-kg DOSE, not a rate (G-MTN-03, benchmark run 2). At
    80 kg it is 80 mcg, the signed IN dose, and passes; with no weight it cannot
    be matched to anything signed, and holds. A per-kg RATE is still not a dose."""
    text = "**TREAT**\n1. Fentanyl 1 mcg/kg IV."
    assert oc.free_text_dose_issues(text, _allowed(), _ctx()) == []
    assert oc.free_text_dose_issues(text, _allowed(), NO_WEIGHT) != []
    assert oc.free_text_dose_issues("**TREAT**\n1. Fentanyl infusion 1 mcg/kg/hr.",
                                    _allowed(), NO_WEIGHT) == []


@pytest.mark.parametrize("text,drug", [
    ("**GIVE**\n- 1 mg IV fentanyl for pain.", "fentanyl 1 mg"),
    ("**TREAT**\n2. Give fentanyl 100mcg IV.", "fentanyl 100mcg"),
    ("**TLDR**\n- Fentanyl 25–100 mcg IV.", "fentanyl 25–100 mcg"),   # one end outside
    ("**TREAT**\n1. Give ketamine 20 mg IV.", "ketamine 20 mg"),      # not in contract
    ("**TREAT**\n1. TXA 2 g IV.", "tranexamic acid 2 g"),             # alias, grams
])
def test_what_is(text, drug):
    issues = oc.free_text_dose_issues(text, _allowed())
    assert len(issues) == 1 and drug in issues[0], issues


def test_a_number_goes_with_the_nearest_drug_in_its_clause():
    text = "**TREAT**\n1. Give fentanyl 80 mcg IN, then ketamine 20 mg IV."
    issues = oc.free_text_dose_issues(text, _allowed(), _ctx())
    assert len(issues) == 1 and "stated ketamine 20 mg" in issues[0], issues


def test_no_contract_means_no_free_text_dose():
    """SC-6's rule for the canonical line, now for any form of it."""
    issues = oc.free_text_dose_issues("**TREAT**\n1. Fentanyl 50 mcg IV.", [])
    assert issues and "stated fentanyl 50 mcg with no signed fentanyl dose" in issues[0]


# ── what the medic reads ─────────────────────────────────────────────────────

NO_WEIGHT = oc.PatientContext()


@pytest.mark.parametrize("text,allowed,ctx,expected", [
    # A drug with no signed contract at all: not answerable here yet.
    ("**TREAT**\n- 2g cefazolin IV for the open fracture.", [], _ctx(),
     "The answer stated cefazolin 2g, but EdgeCDSS has no signed cefazolin "
     "dose. It cannot be answered here until one is signed: use local "
     "protocol or medical control."),
    # A signed contract exists, but nothing builds without a weight.
    ("**TREAT**\n- Titrate naloxone 2–4mg to respiratory effort.", [], NO_WEIGHT,
     "The answer stated naloxone 2–4mg with no signed naloxone dose for this "
     "patient: no weight is confirmed. Give the weight in kg and ask for "
     "naloxone by name."),
    # A signed contract exists; this question did not build it.
    ("**TREAT**\n- Use lorazepam 4mg IV now.", [], _ctx(),
     "The answer stated lorazepam 4mg with no signed lorazepam dose for this "
     "question. Ask for lorazepam by name, with what it is for, to get the "
     "signed dose."),
    # The contract was built; the answer stated a different number.
    ("**TREAT**\n- IN fentanyl 100mcg.", None, _ctx(),
     "The answer stated fentanyl 100mcg, which is not the signed fentanyl dose "
     "for this patient. Ask again for fentanyl dosing to get the signed dose."),
])
def test_the_hold_names_the_drug_and_dose_and_what_would_answer_it(text, allowed, ctx, expected):
    allowed = _allowed() if allowed is None else allowed
    det = oc.run_deterministic_checks("q", text, ctx, allowed)
    outcome = oc.apply_safety_gate(text, det, {"result": "SAFE", "issues": [],
                                               "rationale": ""}, ctx, "q")
    assert outcome.blocked
    assert outcome.response.startswith("Clinical safety hold.")
    assert f"- {expected}" in outcome.response, outcome.response
    # No signed number is quoted in a hold: a dose renders with its cautions.
    assert "0.08" not in outcome.response and "80 mcg" not in outcome.response
    assert "ALLOWED_DOSES" not in outcome.response
