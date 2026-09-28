"""
EdgeCDSS — A14: "absent lung sounds" is a tension sign.

Found in #101; placed by the owner in the #103 review. The tension check read
"absent / decreased / no ... breath sounds" and "air entry", not "lung
sounds". A live-log query, "shot in the chest ... blood pressure 80/40 ...
absent lung sounds on the left side", got the DCR card, not the tension card
that A1's ruling 1 puts first (JTS ID74 p.5: "Absent or markedly decreased
breath sounds in a patient with known thoracic trauma indicate the need for
intervention"). "Lung sounds" is what a medic says as often as "breath
sounds"; so is the reversed order, "breath sounds absent".

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

DCR_MARK = "Start damage-control resuscitation"
REASSESS = "then reassess for hemorrhage — DCR"

# The live-log query, verbatim.
LIVE = ("I have a patient has been shot in the chest currently GCS is seven blood "
        "pressure 80/40 heart rate of 150. I do have iOS established and we have "
        "absent lung sounds on the left side.")


class _NoRetrieval:
    def query(self, *a, **k):
        raise AssertionError("a deterministic card reached retrieval")


class _Retrieval:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: "STUB")


def run(q, retrieval=None):
    return oc._query_with_rag_internal(q, retrieval or _NoRetrieval())


def test_the_live_query_takes_the_tension_card_first_and_keeps_dcr():
    r = run(LIVE)
    assert "needle decompression" in r["response"].lower(), r["response"][:200]
    assert DCR_MARK not in r["response"], "the DCR card fired instead of decompression"
    assert REASSESS in r["response"], "the haemorrhage was dropped"


@pytest.mark.parametrize("query", [
    "GSW to the chest, absent lung sounds on the left, BP 84/50",
    "stab wound to the chest, decreased lung sounds on the right, BP 86/52",
    "blast to the chest, diminished lung sounds left side",
    "chest trauma, no lung sounds on the right",
    "shot in the chest, lung sounds absent on the left",
    "penetrating chest wound, breath sounds absent on the right",
])
def test_lung_sound_phrasings_are_tension_signs_after_chest_trauma(query):
    assert oc.looks_like_tension_pneumothorax(query), query
    assert "needle decompression" in run(query)["response"].lower(), query


@pytest.mark.parametrize("query", [
    "GSW to the chest, lung sounds clear and equal bilaterally, BP 84/50",
    "shot in the chest, lung sounds present on both sides",
    "chest trauma, normal lung sounds, sats 98",
])
def test_normal_lung_sounds_are_not_a_tension_sign(query):
    assert not oc.looks_like_tension_pneumothorax(query), query
