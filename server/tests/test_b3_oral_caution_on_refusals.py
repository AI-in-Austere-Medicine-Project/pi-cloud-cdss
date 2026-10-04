"""B3 (owner, #95 review): the vitals caution must not tell an answer that
already refuses oral intake that "anything by mouth carries an aspiration risk".

The caution table's oral-route rules (vitals_rules.json, group
oral_route_aspiration) arm on the patient (GCS <= 8, stated altered mental
status, glucose < 70) and fire on any oral-route word in the answer, so "nothing
by mouth", "do not give oral fluids" and "cannot safely swallow" fire them too.
A4 made the free-text oral-route check refusal-aware (oral_route_advised); the
caution table now asks the same question. Format only: a caution never holds.

The evidence is run 3's R2-DEPRESSED-GCS answers (GCS 7, "he seems thirsty, can
I let him drink"): every one refuses oral intake, verbatim in
test_depressed_gcs_oral_route.R2_REFUSALS.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402
import vitals as vitals_mod  # noqa: E402
from test_depressed_gcs_oral_route import R2_HISTORY, R2_REFUSALS, _r2_full_query  # noqa: E402

ASPIRATION = "aspiration risk"
R2_QUERY = "he seems thirsty, can I let him drink"


class _Hit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                "distances": [[0.5]]}


def _served(monkeypatch, answer):
    monkeypatch.setattr(providers, "chat", lambda system, messages, **k:
                        '{"result":"SAFE","issues":[],"rationale":"ok"}'
                        if system == oc.VALIDATOR_PROMPT else answer)
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_MODEL", "CDSS_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return oc._query_with_rag_internal(R2_QUERY, _Hit(), conversation_history=R2_HISTORY)


def _conflicts(response, advised, query=None):
    ctx = oc.rebuild_patient_context_from_history(query or _r2_full_query())
    return vitals_mod.conflicts(response, ctx.vitals,
                                flags={"ams_stated": ctx.ams_stated, "oral_route_advised": advised})


@pytest.mark.parametrize("name", sorted(R2_REFUSALS))
def test_a_served_refusal_gets_no_oral_caution(monkeypatch, name):
    r = _served(monkeypatch, R2_REFUSALS[name])
    assert r["validator_result"] != "UNSAFE", r["response"]
    assert not any(ASPIRATION in c for c in r.get("vitals_cautions") or []), name
    assert ASPIRATION + " at this level" not in r["response"]


def test_a_refusal_with_the_flag_gets_no_oral_caution():
    assert not any(ASPIRATION in c for c in _conflicts("Keep him nothing by mouth.", False))


@pytest.mark.parametrize("advice", [
    "Let him drink small sips of water.",
    "Encourage oral fluids as tolerated.",
    "Give oral glucose gel now.",
])
def test_advice_by_mouth_still_gets_the_caution(advice):
    assert oc.oral_route_advised(advice)
    assert any(ASPIRATION in c for c in _conflicts(advice, True)), advice


def test_the_hypoglycaemia_rule_is_refusal_aware_too():
    q = "diabetic found confused, glucose 50"
    assert any("glucose" in c for c in _conflicts("Give oral glucose gel.", True, q))
    assert not _conflicts("Nothing by mouth; give IV dextrose.", False, q)


def test_without_the_flag_the_table_behaves_as_before():
    # vitals.conflicts with no oral_route_advised flag is unchanged.
    ctx = oc.rebuild_patient_context_from_history(_r2_full_query())
    out = vitals_mod.conflicts("Keep him nothing by mouth.", ctx.vitals,
                               flags={"ams_stated": ctx.ams_stated})
    assert any(ASPIRATION in c for c in out)
