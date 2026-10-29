"""An adult dose request that only a weight can answer asks for the weight.

Live harness, 2026-10-24: "need to give ketamine" -> "IV or IM?" -> "IV" went
to the model with nothing offered (every adult ketamine entry is per kg), and
the model's mg/kg answer was held. The weight question was only asked for a
child. Now an adult is asked too, when a drug the request names has signed
per-kg entries and nothing can be offered without a weight. A drug with a
fixed adult dose (fentanyl IV, naloxone) is still answered without one.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
WEIGHT_Q = "Need weight in kg before dosing."


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


@pytest.mark.parametrize("turns", [
    ["need to give ketamine", "IV"],
    ["adult male, need to give ketamine IV"],
    ["morphine IV for pain, adult male"],
])
def test_an_adult_per_kg_request_with_no_weight_asks_the_weight(turns):
    r = run_flow(turns)[-1]
    assert r["response"] == WEIGHT_Q, r["response"]


def test_the_whole_path_to_the_ml():
    rs = run_flow(["need to give ketamine", "IV", "80 kg", "500", "pain"])
    assert [r["response"].split("—")[0].strip() for r in rs[:4]] == [
        "IV or IM? Do you have access?", WEIGHT_Q, "Which ketamine do you have",
        "Which indication for ketamine"]
    # #195 ruling 1 (owner, 2026-10-28): 20 mg is 0.4 mL at the vial, so it is
    # drawn from the signed 5 mg/mL dilution (K3).
    assert "Draw 4 mL of 5mg/mL ketamine dilution IV (20 mg)" in rs[4]["response"], rs[4]["response"]


@pytest.mark.parametrize("q", [
    "fentanyl IV for pain, adult male",
    "naloxone dose, adult",
])
def test_a_fixed_adult_dose_is_not_asked_the_weight(q):
    (r,) = run_flow([q])
    assert r["response"] != WEIGHT_Q, r["response"]
