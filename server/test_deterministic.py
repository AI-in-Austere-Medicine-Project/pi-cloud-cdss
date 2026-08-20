"""
EdgeCDSS — deterministic-layer unit tests.
Runs offline (no API calls, no server). Regression-pins parser fixes.

    cd server && ./run_unit_tests.sh
    (or: python3 -m pytest test_deterministic.py -q, or: python3 test_deterministic.py)

Requires no third-party packages beyond pytest, and no OPENAI_API_KEY.
"""

import os
import re
import subprocess
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai_client import (  # noqa: E402
    PatientContext, build_allowed_actions, extract_patient_context,
    wants_medication_dose, _has_word,
)
from test_fixtures import S3_QUERY  # noqa: E402


# ── P-0: the module must import with no SDK and no API key ──────────────────

def test_import_is_offline_safe():
    """openai_client must import without the openai package or an API key set.

    The whole offline suite depends on this: the client is built lazily in
    get_client(), not at module scope.
    """
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    here = os.path.dirname(os.path.abspath(__file__))
    proc = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, %r); import openai_client" % here],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_llm_client_is_not_built_at_import():
    import openai_client
    assert openai_client._client is None, "client must not be constructed until first LLM call"


# ── Fix 2026-07-18: word-boundary matching for short tokens ──────────────────

def test_kidney_is_not_pediatric():
    ctx = extract_patient_context("55 year old male with kidney stone pain")
    # 'kidney' must not trip the 'kid' pediatric term (age keeps him adult)
    assert ctx.is_pediatric is False

def test_girlfriend_boyfriend_not_pediatric():
    assert extract_patient_context("my girlfriend has severe wrist pain, 70kg").is_pediatric is False
    assert extract_patient_context("boyfriend fell off a ladder, 90kg").is_pediatric is False

def test_real_pediatric_terms_still_fire():
    assert extract_patient_context("6 year old boy 20kg burn").is_pediatric is True
    assert extract_patient_context("need RSI doses for a kid").is_pediatric is True
    assert extract_patient_context("toddler ingestion").is_pediatric is True

def test_rock_is_not_rocuronium():
    assert _has_word("a rock fell on his leg", "roc") is False
    assert _has_word("give roc now", "roc") is True
    assert _has_word("procedure planned", "roc") is False

def test_epidural_is_not_epi():
    assert _has_word("concern for epidural hematoma", "epi") is False
    assert _has_word("push dose epi please", "epi") is True

def test_wants_dose_word_boundaries():
    assert wants_medication_dose("a rock fell on his leg, splint advice") is False
    assert wants_medication_dose("give roc 1.2mg/kg") is True
    assert wants_medication_dose("ketamine for pain") is True


def test_adult_age_is_authoritative():
    # "55 year old" must not be pediatric-gated by the phrase "year old"
    assert extract_patient_context("55 year old male with kidney stone pain").is_pediatric is False
    assert extract_patient_context("45 year old with a fracture 80kg").is_pediatric is False

def test_child_age_still_authoritative():
    assert extract_patient_context("6 year old with a burn").is_pediatric is True
    assert extract_patient_context("15 yo with wrist fx").is_pediatric is True

def test_low_weight_without_age_is_pediatric():
    assert extract_patient_context("patient 20kg needs analgesia").is_pediatric is True


# ── SC-2 (v4.1): is_pediatric must be re-derived per turn, not latched ───────

def test_adult_age_clears_pediatric_flag():
    """A stated adult age after a pediatric context must clear the flag.

    Reproduced on v4.0 HEAD: the flag was write-once True, so a 45-year-old
    inheriting a child's context stayed pediatric-gated forever.
    """
    ctx = extract_patient_context("6 year old 20kg burn")
    assert ctx.is_pediatric is True
    ctx = extract_patient_context("45 year old male 80kg", prior_ctx=ctx)
    assert ctx.age_years == 45.0
    assert ctx.is_pediatric is False


def test_pediatric_flag_sticky_without_age():
    """No age in the turn -> flag unchanged. "IV" must not un-pediatric a child."""
    ctx = extract_patient_context("6 year old 20kg burn")
    for follow_up in ["IV", "now what", "give ketamine"]:
        ctx = extract_patient_context(follow_up, prior_ctx=ctx)
        assert ctx.is_pediatric is True, follow_up


def test_pediatric_age_still_sets_flag():
    """The reverse direction: a child's age after an adult context sets the flag."""
    ctx = extract_patient_context("45 year old male 80kg")
    assert ctx.is_pediatric is False
    ctx = extract_patient_context("6 year old", prior_ctx=ctx)
    assert ctx.is_pediatric is True


def test_low_weight_heuristic_unchanged_when_no_age():
    """Pin the elif branch — SC-2 must not disturb weight-only detection."""
    assert extract_patient_context("patient 20kg needs analgesia").is_pediatric is True
    assert extract_patient_context("patient 80kg needs analgesia").is_pediatric is False
    ctx = extract_patient_context("toddler with a burn")
    assert ctx.is_pediatric is True and ctx.age_years is None


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError:
                print(f"FAIL {name}")
                fails += 1
    sys.exit(1 if fails else 0)


# ── SC-7 (minimal form): ALLOWED_ACTIONS carries no hard-coded dose ─────────
# Owner decision 2026-08-20 (PLAN_v4.1.md §5.5): pull SC-7's minimal form in so
# the S-3 seizure case becomes a weight-free protocol answer instead of the
# safety hold SC-6 would otherwise produce.

DOSE_TOKEN_RE = re.compile(r'\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|units?|meq)\b', re.I)


SEIZURE_TRIGGER_QUERY = "patient having active seizure"   # 07-18.jsonl:35, :62


def test_seizure_adult_default_carries_no_numeric_dose():
    """A hard-coded 'levetiracetam (Keppra) 1500mg' reached the prompt verbatim.

    ALLOWED_ACTIONS is weight-free protocol guidance; a number in it is a dose
    the generator can copy without any contract having authorised it.
    """
    ctx = PatientContext()                      # adult, no confirmed weight
    actions = build_allowed_actions(SEIZURE_TRIGGER_QUERY, ctx)
    joined = " ".join(actions)
    assert "SEIZURE_ADULT_DEFAULT" in joined
    assert "levetiracetam" in joined.lower(), "the drug stays; only the number goes"
    assert DOSE_TOKEN_RE.search(joined) is None, f"hard-coded dose still present: {joined}"


def test_s3_query_never_reached_the_hard_coded_action():
    """Pins a correction to PLAN_v4.1.md §0/§5.5, measured 2026-08-20.

    The plan asserted the hard-coded 1500mg in build_allowed_actions() was the
    source of the S-3 GIVE line, and that stripping it would turn S-3 into a
    weight-free protocol answer. It is not the source: the S-3 query reads
    "ststus SZ", which matches none of the three seizure triggers
    ("seizure" / "seizing" / "status epilepticus"), and the record logged
    history_turns=0, so no earlier turn supplied one either. The 1500mg was
    generator-produced under source_mode=GENERAL_MEDICAL.

    Consequence: SC-7-minimal does NOT soften SC-6 for S-3. That case is still
    a safety hold. Changing that would need the trigger list widened (a
    different change, with its own false-positive surface), not this one.
    """
    for ctx in (PatientContext(), PatientContext(age_years=40.0)):
        assert build_allowed_actions(S3_QUERY, ctx) == []


def test_no_allowed_action_anywhere_carries_a_dose():
    """Meta-test: the same defect must not arrive via a different branch.

    ALLOWED_ACTIONS is weight-free protocol guidance by contract; every number
    with a dose unit belongs in ALLOWED_DOSES, which is built from a confirmed
    weight. Non-dose numbers ('within 3 hours') are fine and stay allowed.
    """
    queries = [
        S3_QUERY,
        "adult in status epilepticus",
        "6 year old seizing",
        "active abdominal bleeding, hemorrhagic shock",
        "massive bleeding after blast",
    ]
    contexts = [
        PatientContext(),
        PatientContext(age_years=4.0, is_pediatric=True),
        PatientContext(age_years=4.0, is_pediatric=True, confirmed_weight_kg=17.0),
        PatientContext(age_years=40.0, confirmed_weight_kg=80.0),
    ]
    for q in queries:
        for ctx in contexts:
            for action in build_allowed_actions(q, ctx):
                assert DOSE_TOKEN_RE.search(action) is None, (
                    f"ALLOWED_ACTIONS must carry no dose; query={q!r} action={action!r}")


def test_pediatric_seizure_branch_unchanged():
    """SC-7-minimal touches the adult branch only; SC-9 stays out of scope."""
    ctx = PatientContext(age_years=6.0, is_pediatric=True)
    actions = build_allowed_actions("6 year old seizing", ctx)
    assert any(a.startswith("SEIZURE_PEDIATRIC") for a in actions)
