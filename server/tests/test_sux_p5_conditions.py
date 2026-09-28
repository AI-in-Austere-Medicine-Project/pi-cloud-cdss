"""
EdgeCDSS — A12: succinylcholine leaves ALLOWED_DOSES under a P5 condition.

Owner, #98 review (A6 ruling 6). P5 (signed, #100) holds an answer that
advises succinylcholine when burns, spinal cord injury or hyperkalaemia is
recorded. The builder should never have offered it: on main the RSI bundle
dropped succinylcholine only on the substrings "burn" and "crush", so
  * spinal cord injury and hyperkalaemia (K >= 5.5, owner ruling) still got it;
  * "burns ... RSI with sux" got BOTH paralytics: the bundle chose rocuronium,
    and the named-drug path added succinylcholine back;
  * "burns, sux dose" outside an RSI query got it.

The condition is A6's P5 detector (negation-aware; K >= 5.5 mmol/L), plus the
builder's existing "burn" and "crush" words, kept so nothing that is
excluded today is offered succinylcholine again. Rocuronium fills the role.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _paralytics(query):
    ctx = oc.extract_patient_context(query)
    return sorted({d.drug for d in oc.build_allowed_doses(query, ctx)
                   if d.drug in ("succinylcholine", "rocuronium")})


P5 = [
    "80kg male, 40% TBSA burns, RSI with sux",
    "80kg male, spinal cord injury, RSI with succinylcholine",
    "80kg male, paraplegic after a fall, RSI with sux",
    "80kg male, K is 6.1, RSI with sux",
    "80kg male, hyperkalemia, peaked T waves, RSI with succinylcholine",
    "80kg male, crush injury, RSI with sux",
]


@pytest.mark.parametrize("query", P5)
def test_a_p5_condition_gets_rocuronium_not_succinylcholine(query):
    assert _paralytics(query) == ["rocuronium"], query


@pytest.mark.parametrize("query", [
    "80kg burns, sux dose",
    "80kg male with a spinal cord injury, succinylcholine dose",
])
def test_outside_rsi_a_p5_condition_gets_no_succinylcholine(query):
    assert "succinylcholine" not in _paralytics(query), query


@pytest.mark.parametrize("query", [
    "80kg male, 40% TBSA burns, RSI with sux",
    "80kg male, K is 6.1, RSI with sux",
])
def test_the_rsi_card_serves_rocuronium(query):
    ctx = oc.extract_patient_context(query)
    text = oc.build_rsi_response(ctx, query) or ""
    assert "rocuronium" in text and "succinylcholine IV" not in text, text


# ── Controls: no P5 condition ──────────────────────────────────────────────

def test_without_a_p5_condition_a_named_sux_is_offered():
    assert _paralytics("80kg male, RSI with sux") == ["succinylcholine"]


def test_k_under_the_threshold_does_not_exclude_it():
    assert _paralytics("80kg male, K is 5.2, RSI with sux") == ["succinylcholine"]


def test_unnamed_rsi_still_gets_rocuronium():
    assert _paralytics("80kg male, needs RSI") == ["rocuronium"]
