"""The ketamine analgesia card comes back, with the mL, when its request is completed.

Live harness, 2026-10-24 (owner: "goal is the llm giving a straight answer in
mL"). The card for "ketamine for pain 80kg adult IV access" gives 20 mg and
asks the vial. The answer, "500 mg / 10 mL", named no ketamine, so the card's
pre-gate (which reads the current turn) did not fire; it went to the model,
which echoed the vial question. A child's "500" got no dose at all. And
"need to give ketamine 80kg adult IV" -> vial -> "500" -> which indication ->
"pain" went to the model, which wrote 80 mg (held). The RSI bundle already
resumes on its vial answer (rsi_bundle_should_resume); the analgesia card did
not. Now it resumes on the vial answer and on "pain" as the indication
answer, and serves the canonical "Draw X mL of 50mg/mL ketamine IV (Y mg)".

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        return "STUB"
    monkeypatch.setattr(providers, "chat", chat)


def run_flow(turns):
    hist, out = [], []
    for q in turns:
        r = oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(hist))
        out.append(r)
        hist.append({"query": q, "response": r["response"]})
    return out


@pytest.mark.parametrize("turns, line", [
    (["ketamine for pain 80kg adult IV access", "500 mg / 10 mL"],
     "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)"),
    (["ketamine for pain 80kg adult IV access", "500"],
     "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)"),
    (["6 year old 20 kg, arm fracture, ketamine IV for pain", "500"],
     "Draw 0.08 mL of 50mg/mL ketamine IV (4 mg)"),
    (["ketamine for pain 80kg adult IV access", "Show the vial math for that dose.", "500"],
     "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)"),
    (["need to give ketamine 80kg adult IV", "500", "pain"],
     "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)"),
])
def test_the_card_comes_back_with_the_ml(turns, line):
    r = run_flow(turns)[-1]
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", (r["source_mode"], r["response"][:200])
    assert line in r["response"], r["response"]


@pytest.mark.parametrize("turns", [
    # another indication is not the analgesia card
    ["need to give ketamine 80kg adult IV", "500", "agitation"],
    # an RSI in flight resumes as RSI
    ["RSI 80 kg male, IV established, ketamine and rocuronium", "500"],
])
def test_other_requests_do_not_get_the_analgesia_card(turns):
    r = run_flow(turns)[-1]
    assert "Indication: moderate to severe pain" not in r["response"], r["response"]
