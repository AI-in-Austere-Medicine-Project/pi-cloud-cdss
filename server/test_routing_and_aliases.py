"""
EdgeCDSS — clinical router alias resolution (F-2 / Q-3) and vent-vs-RSI
routing (S-4 / Q-2).

Offline: no ChromaDB, no OpenAI. The router loads protocol_index.json and
query_aliases.json from disk only.

    cd server && ./run_unit_tests.sh
"""

import glob
import json
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from clinical_router import ClinicalRouter  # noqa: E402
from openai_client import (  # noqa: E402
    has_hypotension_or_shock, is_rsi_or_post_intubation_context,
    is_vent_settings_query, looks_like_sepsis, should_use_rsi_pregate,
)
from test_fixtures import (  # noqa: E402
    ALIAS_CONTEXT_DEPENDENT_CASES,
    ALIAS_SHADOWS_A_REAL_DRUG,
    ALIAS_STANDALONE_CASES, F2_ROWS, S4_VENT_QUERY, S4_VENT_REFUSED,
)

_ROUTER = ClinicalRouter()


def _resolved_keys(query):
    """Alias keys the router resolved for this query."""
    _, resolved = _ROUTER.resolve_aliases(query)
    return [entry.split(" → ")[0] for entry in resolved]


# ── Q-2: vent settings must not route to the RSI bundle (S-4) ───────────────

def test_vent_settings_query_does_not_route_to_rsi():
    """The S-4 case: asked for vent settings, answered with an RSI paralytic bundle."""
    assert is_rsi_or_post_intubation_context(S4_VENT_QUERY) is True   # substring collision intact
    assert is_vent_settings_query(S4_VENT_QUERY) is True
    assert should_use_rsi_pregate(S4_VENT_QUERY) is False


def test_both_logged_forms_of_the_s4_question_avoid_rsi():
    """Same clinical question, two logged phrasings, two days apart.

    Only the routing half is asserted here. The 07-18 form was answered with
    "AUSTERE-CDS handles medical queries only." — that refusal is Q-1, which is
    out of scope for v4.1, so this test cannot assert what it does return.
    """
    for query in (S4_VENT_QUERY, S4_VENT_REFUSED):
        assert should_use_rsi_pregate(query) is False, query


def test_rsi_query_still_routes_to_rsi():
    """Guard against over-correcting: real RSI requests must keep the pre-gate."""
    for query in ["RSI an 80kg male trauma patient ketamine and rocuronium",
                  "need to RSI a badly burned 70kg male",
                  "I need to intubate a 6 year old"]:
        assert should_use_rsi_pregate(query) is True, query


def test_post_intubation_vent_phrasing_still_rsi():
    """Why the fix is a guard, not deletion of "ventilator" from the RSI terms.

    Deleting the term would break these; the guard keeps them.
    """
    for query in ["patient on the vent post intubation needs sedation 80kg",
                  "post-intubation sedation for an 80kg male",
                  "patient intubated need a ketamine drip for sedation 80kg male"]:
        assert should_use_rsi_pregate(query) is True, query


def test_vent_settings_terms_are_not_rsi_terms():
    """A pure vent-settings query with no RSI vocabulary stays out of both paths."""
    assert should_use_rsi_pregate("what tidal volume and PEEP for a 70kg male") is False


# ── Q-3: word-boundary alias matching ───────────────────────────────────────

def test_alias_substring_poisoning_fixed():
    """The four F-2 rows: no alias may resolve from inside a longer word."""
    for query, spurious in F2_ROWS:
        keys = _resolved_keys(query)
        for key in spurious:
            assert key not in keys, f"{key!r} still resolves inside {query!r}"


def test_standalone_aliases_still_resolve():
    """Short keys stay useful when typed as words — this is why they are not deleted."""
    for query, key, standard in ALIAS_STANDALONE_CASES:
        enhanced, resolved = _ROUTER.resolve_aliases(query)
        assert key in _resolved_keys(query), f"{key!r} did not resolve in {query!r}"
        assert standard in enhanced


def test_context_dependent_aliases_need_corroboration():
    """F-6 supersedes part of the v4.1 decision above, for one subset.

    v4.1 word-anchored the short keys and kept them resolving alone, which is
    right for "tq" and wrong for "k": anchoring cannot help when the collision
    IS the whole word. "his K is 6.8 with peaked T waves" resolved k ->
    ketamine and searched a hyperkalaemia emergency as a ketamine question.

    Paired, so this cannot be satisfied by deleting the keys.
    """
    for alone, corroborated, key in ALIAS_CONTEXT_DEPENDENT_CASES:
        assert key not in _resolved_keys(alone), (
            f"{key!r} resolved with nothing to corroborate it, in {alone!r}")
        assert key in _resolved_keys(corroborated), (
            f"{key!r} failed to resolve even when corroborated, in "
            f"{corroborated!r} — the key is now dead rather than guarded")


def test_every_context_dependent_key_is_corroborable():
    """Two ways this list can be wrong, both of them silent.

    A key the alias table does not have is dead config. A key whose STANDARD
    names nothing in the protocol index can never be corroborated, so listing
    it does not guard it — it disables it permanently, and the medic sees a
    word that used to resolve quietly stop resolving.
    """
    for key in ClinicalRouter.CONTEXT_DEPENDENT_ALIASES:
        assert key in _ROUTER.query_aliases, f"{key!r} is not an alias key"
        assert _ROUTER._protocols_for_alias(key), (
            f"{key!r} names no protocol, so it can never be corroborated — "
            f"guarding it here disables it instead of guarding it")


def test_multiword_aliases_resolve():
    for query, key in [("rocky onium please", "rocky onium"),
                       ("start a norepi drip", "norepi drip")]:
        assert key in _resolved_keys(query)


def test_no_alias_shadows_a_real_drug():
    """An alias may never be another real drug's name.

    Word anchoring cannot help here — "vitamin k" IS the whole phrase, and it
    was anchored correctly the whole time. The collision was that the phrase
    belongs to a different drug, so the fix is that vitamin K resolves to
    nothing here and has its own contract in drug_contracts.json instead.
    """
    for query, forbidden in ALIAS_SHADOWS_A_REAL_DRUG:
        assert forbidden not in _resolved_keys(query), (
            f"{forbidden!r} still resolves in {query!r} — it is a real drug's "
            f"name, not an alias")
        _, resolved = _ROUTER.resolve_aliases(query)
        assert not any("ketamine" in r for r in resolved), (
            f"{query!r} still enhances retrieval with ketamine: {resolved}")


def test_every_alias_key_is_not_another_drugs_name():
    """The class, as a property over the whole alias table.

    drug_contracts.lint_alias_collisions() enforces this inside the contract
    file; this asserts it across the router's table too, so the two cannot
    drift into disagreeing about what a drug name is.
    """
    import drug_contracts as dc
    for alias in _ROUTER.query_aliases:
        assert alias.lower() not in dc.DRUGS, (
            f"alias {alias!r} is the generic name of a contracted drug — an "
            f"alias may never shadow a real drug")


def test_no_alias_matches_inside_a_word():
    """Property over the whole table: no key may fire when embedded in a token."""
    for alias in _ROUTER.query_aliases:
        if " " in alias:
            continue          # multi-word keys cannot be embedded in one token
        embedded = f"xx{alias}xx"
        assert alias not in _resolved_keys(embedded), f"{alias!r} matched inside {embedded!r}"


def test_patient_does_not_resolve_physician_assistant():
    """The single highest-frequency poisoning: 'pa' inside 'patient' (44 hits)."""
    enhanced, _ = _ROUTER.resolve_aliases("severe TBI patient GCS 6 BP 90/60 needs management")
    assert "physician assistant" not in enhanced


def test_kg_does_not_resolve_ketamine():
    """'k' inside '34kg' / 'dka' (54 hits)."""
    for query in ["34kg", "17 kg", "Vent settings dka", "80kg male fx to tib fib"]:
        enhanced, _ = _ROUTER.resolve_aliases(query)
        assert "ketamine" not in enhanced.lower(), query


# ── Corpus-level check ──────────────────────────────────────────────────────
# The audit corpus lives outside this repo (../../data/sessions). When it is
# present the total hit count is pinned exactly; when it is absent the test
# SKIPS LOUDLY rather than passing, so an absent corpus is never mistaken for
# a green result.

_CORPUS = os.getenv(
    "CDSS_AUDIT_SESSIONS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "sessions"),
)

# Measured on the 135-entry corpus at the time of the v4.1 audit:
#   plain substring: 187 hits   word-boundary: 44 hits   spurious removed: 143
EXPECTED_CORPUS_ALIAS_HITS = 44
EXPECTED_CORPUS_QUERIES = 135


def _corpus_queries():
    files = sorted(glob.glob(os.path.join(_CORPUS, "*.jsonl")))
    if not files:
        return None
    return [json.loads(line)["query"] for f in files for line in open(f)]


def test_corpus_alias_hit_count():
    queries = _corpus_queries()
    if queries is None:
        pytest.skip(f"audit corpus not present at {_CORPUS} — set CDSS_AUDIT_SESSIONS")
    assert len(queries) == EXPECTED_CORPUS_QUERIES
    hits = sum(len(_resolved_keys(q)) for q in queries)
    assert hits == EXPECTED_CORPUS_ALIAS_HITS, (
        f"alias hits over the audit corpus changed: {hits} != {EXPECTED_CORPUS_ALIAS_HITS}. "
        "Either the matcher or query_aliases.json changed — re-measure before updating."
    )


# ── substring routing: the fourth specimen ──────────────────────────────────
#
# has_hypotension_or_shock matched "map " inside "roadmap", "ams" inside
# "milligrams", and "altered" inside "unaltered". Same failure class as the F-2
# alias table, FIXED_PREP_TERMS and the vitals labels: short medical tokens are
# substrings of longer ordinary words, and this parser reads free text typed
# one-handed. Every hit here routes a casualty.

@pytest.mark.parametrize("text", [
    "check the roadmap for evac timing",          # map
    "give 500 milligrams of ceftriaxone",         # ams
    "draw 2 grams of TXA",                        # ams
    "follow the treatment algorithm diagrams",    # ams
    "review the exams from the aid station",      # ams
    "unaltered mental status, GCS 15",            # altered — an explicit negation
])
def test_ordinary_words_do_not_route_as_shock(text):
    assert has_hypotension_or_shock(text) is False, text


@pytest.mark.parametrize("text", [
    "patient is hypotensive",
    "septic shock",
    "he is in shock",
    "patient was shocked twice",                  # inflections still count
    "poor perfusion",
    "altered mental status",
    "MAP 55",
    "BP 82/40",
])
def test_real_shock_language_still_routes(text):
    assert has_hypotension_or_shock(text) is True, text


def test_a_dose_in_grams_no_longer_routes_a_casualty_as_septic():
    """The compound failure. looks_like_sepsis is infection AND shock, so
    "milligrams" supplied the shock half for any infected patient — and the
    sepsis path is the one that flags TXA as hemorrhage misuse."""
    infected_dose = "fever and purulent wound, give 500 milligrams ceftriaxone"
    assert looks_like_sepsis(infected_dose) is False
    assert looks_like_sepsis("fever, purulent wound, hypotensive") is True

