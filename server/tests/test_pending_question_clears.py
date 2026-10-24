"""A pending question does not swallow the next request.

Owner, 2026-10-24 (live log, finding 1): after "have a 6 year old in pain.
need to give ketamine iV established weight is 45kg", the turns "Now I need to
give mag", "i need to give magnesium" and "I dont want to give ketamine i want
to give magnesium now" each got the ketamine vial question again. "A pending
question clears when the next turn names a different drug, negates the drug,
or is not an answer to it; the new request is then handled normally."

Cause: the pre-gate asked the vial (and route, and which-indication)
questions for every drug named anywhere in the conversation, and the dose
builder offered every drug named anywhere in it. Found with it (same class):
"fentanyl instead" got the ketamine route question; "what about magnesium for
asthma" was offered only ketamine doses; and "80 kg adult, IV", the answer to
the route question, skipped the vial and indication questions.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
LIVE_FIRST = "have a 6 year old in pain. need to give ketamine iV established weight is 45kg"
LIVE_NEXT = [
    "Now I need to give mag",
    "i need to give magnesium",
    "I dont want to give ketamine i want to give magnesium now",
]


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
        out["allowed"] = [d.drug for d in doses]
        return doses

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        return "STUB"

    monkeypatch.setattr(oc, "build_allowed_doses", build)
    monkeypatch.setattr(providers, "chat", chat)
    return out


def run_flow(turns):
    hist, out = [], []
    for q in turns:
        r = oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(hist))
        out.append(r)
        hist.append({"query": q, "response": r["response"]})
    return out


def _is_ketamine_question(text):
    t = text.lower()
    return t.startswith("which ketamine") or t.startswith("which indication for ketamine") \
        or t.startswith("iv or im?")


@pytest.mark.parametrize("next_turn", LIVE_NEXT)
def test_the_live_magnesium_turn_is_not_the_ketamine_vial_question(seen, next_turn):
    first, nxt = run_flow([LIVE_FIRST, next_turn])
    assert "ketamine" in first["response"].lower()
    assert not _is_ketamine_question(nxt["response"]), nxt["response"]
    assert "ketamine" not in (seen["allowed"] or []), seen["allowed"]


def test_the_whole_live_session(seen):
    rs = run_flow([LIVE_FIRST] + LIVE_NEXT)
    for q, r in zip(LIVE_NEXT, rs[1:]):
        assert not _is_ketamine_question(r["response"]), (q, r["response"])


def test_a_different_drug_clears_the_route_question(seen):
    _, r = run_flow(["need ketamine 80kg", "fentanyl instead"])
    assert not _is_ketamine_question(r["response"]), r["response"]
    assert "ketamine" not in (seen["allowed"] or []), seen["allowed"]


def test_a_new_drug_is_not_offered_the_old_drugs_doses(seen):
    run_flow(["need to give ketamine", "80 kg adult, IV", "what about magnesium for asthma"])
    assert "ketamine" not in (seen["allowed"] or []), seen["allowed"]


def test_a_turn_that_does_not_answer_the_pending_question_clears_it(seen):
    rs = run_flow(["need to give ketamine 80 kg adult IV", "what about his airway"])
    assert rs[0]["response"].startswith("Which ketamine do you have"), rs[0]["response"]
    assert not _is_ketamine_question(rs[1]["response"]), rs[1]["response"]


def test_the_answer_to_the_route_question_gets_the_next_question(seen):
    rs = run_flow(["need to give ketamine", "80 kg adult, IV"])
    assert rs[0]["response"].startswith("IV or IM?"), rs[0]["response"]
    assert rs[1]["response"].startswith("Which ketamine do you have"), rs[1]["response"]


@pytest.mark.parametrize("turns, expect", [
    # the answers to each question keep the pending request
    (["need to give ketamine 80 kg adult IV", "500"], "Which indication for ketamine"),
    (["need to give ketamine 80 kg adult IV", "500 mg / 10 mL"], "Which indication for ketamine"),
    (["need ketamine for a 6yo arm fx", "20 kg"], "IV or IM?"),
    (["need to give ketamine 80 kg adult IV", "500", "yes"], "Which indication for ketamine"),
    # the same drug named again is still that request
    (["need to give ketamine 80 kg adult IV", "the ketamine is 500 mg in 10 mL"],
     "Which indication for ketamine"),
])
def test_an_answer_keeps_the_pending_request(seen, turns, expect):
    r = run_flow(turns)[-1]
    assert r["response"].startswith(expect), r["response"]


@pytest.mark.parametrize("q, drugs", [
    ("I dont want to give ketamine i want to give magnesium now", {"ketamine"}),
    ("not ketamine, fentanyl", {"ketamine"}),
    ("instead of ketamine give fentanyl", {"ketamine"}),
    ("do not give ketamine", {"ketamine"}),
    ("ketamine for pain, 80 kg, no IV", set()),
    ("give ketamine, no allergies", set()),
])
def test_negated_drugs(q, drugs):
    assert oc.negated_drugs(q) == drugs


# ── live harness, 2026-10-24: a stray digit is not a vial answer ─────────────

@pytest.mark.parametrize("not_an_answer", [
    "what does a GCS of 9 mean",
    "BP is 90/60 now",
    "he is 25 years old",
])
def test_a_number_that_is_not_a_vial_does_not_answer_the_vial_question(seen, not_an_answer):
    rs = run_flow(["need to give ketamine 80kg adult IV", not_an_answer])
    assert rs[0]["response"].startswith("Which ketamine do you have"), rs[0]["response"]
    assert not _is_ketamine_question(rs[1]["response"]), rs[1]["response"]


@pytest.mark.parametrize("answer", ["500", "500 in 10", "50 mg/mL", "the 500 mg vial", "50"])
def test_a_declared_presentation_answers_the_vial_question(answer):
    assert oc.answers_pending_question("vial", answer, "need to give ketamine 80kg adult IV")
