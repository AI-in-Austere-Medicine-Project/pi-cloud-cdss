"""
F-6 — the router must not route on one generic word or a substring.

Baseline evidence (runs/baseline-gpt4omini). The router rewrote the ChromaDB
query on 57 of 138 model-reaching turns. Measured misroutes, all at HIGH:

    "criteria for terminating resuscitation in the field"  -> Burn Care
    "rising end tidal CO2 during a resuscitation"          -> Burn Care
    "his K is 6.8 ... order of treatment"       -> Chemical Agent Exposure
    "organophosphate exposure from a farm sprayer"         -> Concussion
    "standard dilution for a keppra bag"                   -> Concussion

The last two are the F-2 substring class, alive in term_to_protocols: word
boundaries were added to the alias table in v4.1 and never to the protocol
index, so the index term "pra" matched inside "s-pra-yer" and "kep-pra".
"""
import json
import pytest

from clinical_router import ClinicalRouter

router = ClinicalRouter()


def routed(query):
    r = router.route(query)
    return (r.confidence in ("HIGH", "MEDIUM"), r.protocol_title, r.enhanced_search_query)


# ── (query, protocol-that-must-not-match) ───────────────────────────────────

MUST_NOT_MATCH = [
    ("what are the criteria for terminating resuscitation in the field", "Burn"),
    ("what does a rising end tidal CO2 tell me during a resuscitation", "Burn"),
    ("his K is 6.8 and the ECG has peaked T waves, what is the order of treatment",
     "Chemical"),
    ("organophosphate exposure from a farm sprayer, what are the signs", "Progressive"),
    ("what is the standard dilution for a keppra bag", "Progressive"),
    ("cat scratch three days ago, now febrile and hypotensive", "Telemedicine"),
]


@pytest.mark.parametrize("query,forbidden", MUST_NOT_MATCH)
def test_router_does_not_route_on_a_single_ambiguous_term(query, forbidden):
    used, title, enhanced = routed(query)
    assert not (used and forbidden.lower() in (title or "").lower()), (
        f"{query!r} routed to {title!r}")
    if not used:
        # Alias resolution is a separate, legitimate enhancement — "keppra" ->
        # "levetiracetam" is an unambiguous drug synonym and stays. What must
        # NOT be appended is the wrong protocol's search-term list.
        assert forbidden.lower() not in enhanced.lower(), enhanced


@pytest.mark.parametrize("query,term", [
    ("organophosphate exposure from a farm sprayer", "pra"),
    ("what is the standard dilution for a keppra bag", "pra"),
    ("the patient is unaltered and following commands", "altered"),
])
def test_index_terms_are_word_anchored(query, term):
    """The F-2 fix, applied to the layer it was never applied to."""
    assert term in query.lower(), "the substring really is present"
    assert not router._term_pattern(term).search(query.lower()), (
        f"{term!r} matched inside a longer word in {query!r}")


# ── the routings that must survive ─────────────────────────────────────────
# The router is the mitigation the 2026-08-21 retrieval diagnosis credits for
# burn queries surfacing at all (+0.118 and +0.176 on the two live narratives).
# A specificity rule that takes those with it is not a fix.

MUST_STILL_ROUTE = [
    ("he's got burns and broken bones from a car wreck, what do I do first", "Burn"),
    ("My patient is 30 years old and maybe like 190 lbs. his Tesla rear ended a "
     "semi and he's got broken bones and estimated 70% burns.", "Burn"),
    ("40% TBSA burns, what fluid resuscitation does he need?", "Burn"),
    ("severe TBI patient GCS 6 BP 90/60 needs management", "Brain"),
    ("need basic vent settings for TBI patient", "Brain"),
]


@pytest.mark.parametrize("query,expected", MUST_STILL_ROUTE)
def test_good_routings_survive(query, expected):
    used, title, _ = routed(query)
    assert used, f"{query!r} lost its routing"
    assert expected.lower() in (title or "").lower(), title


def test_a_generic_term_routes_when_corroborated():
    """"resuscitation" alone is prose. "burns" plus "resuscitation" is a topic."""
    assert not routed("terminating resuscitation")[0]
    used, title, _ = routed("40% TBSA burns, what fluid resuscitation does he need?")
    assert used and "burn" in title.lower()


# ── (b) short ambiguous alias keys need corroboration ──────────────────────

def test_a_short_ambiguous_alias_does_not_resolve_alone():
    _, resolved = router.resolve_aliases(
        "his K is 6.8 and the ECG has peaked T waves")
    assert not any(r.startswith("k →") for r in resolved), resolved


def test_the_same_alias_resolves_when_corroborated():
    """"k" beside ketamine's own protocol vocabulary is a real resolution."""
    _, resolved = router.resolve_aliases("push the k for induction, ketamine 100mg/mL")
    assert any("ketamine" in r for r in resolved)


@pytest.mark.parametrize("alias", sorted(ClinicalRouter.CONTEXT_DEPENDENT_ALIASES))
def test_every_context_dependent_alias_is_short_or_an_ordinary_word(alias):
    """The list is for collisions word anchoring cannot fix — where the
    collision IS the whole word. A long unambiguous key does not belong."""
    assert len(alias) <= 6, alias


def test_no_alias_key_of_two_characters_or_less_yields_high_confidence_alone():
    """The property test. A two-character token is never enough on its own."""
    for alias in router.query_aliases:
        if len(alias) > 2:
            continue
        result = router.route(f"the {alias} situation")
        assert result.confidence != "HIGH", (
            f"alias {alias!r} alone produced HIGH confidence "
            f"-> {result.protocol_title}")


# ── no good routing was lost across the bank ───────────────────────────────

def test_the_bank_lost_no_correct_routing():
    """Measured: of 160 bank queries, 56 routings were preserved unchanged and
    7 were dropped — every one of the 7 a misroute, listed in MUST_NOT_MATCH
    or adjacent to it. This pins the preserved count so a later tightening
    cannot quietly take good routings with it.
    """
    path = "/home/andrew/projects/cdss-eval/scenarios/scenarios.jsonl"
    try:
        queries = [json.loads(l)["query"] for l in open(path)]
    except OSError:
        pytest.skip("eval bank not present")
    routed_n = sum(1 for q in queries
                   if router.route(q).confidence in ("HIGH", "MEDIUM"))
    assert routed_n >= 55, (
        f"only {routed_n} of {len(queries)} bank queries still route; the "
        f"baseline preserved 56")


# ── the cost of correctness ─────────────────────────────────────────────────

def test_route_does_not_recompile_the_index_on_every_call():
    """Word anchoring replaced `term in combined` with a regex per term.

    Compiled per call against 625 index terms that cost 125 ms per route() —
    a 180x regression on the 0.7 ms substring matching took, paid on every
    query that reaches retrieval. Patterns are compiled once at index-build
    time now.

    Asserted structurally rather than by wall clock, so it does not flake on a
    loaded Jetson: the cache must be populated at construction and route()
    must not add to it.
    """
    r = ClinicalRouter()
    assert len(r._term_patterns) == len(r.term_to_protocols), (
        "every index term should have a compiled matcher after __init__")
    before = len(r._term_patterns)
    r.route("severe TBI patient GCS 6 BP 90/60 needs management")
    r.route("he's got burns and broken bones from a car wreck")
    assert len(r._term_patterns) == before, (
        "route() compiled new patterns — the cache is not being used")


def test_alias_patterns_are_cached_too():
    info_before = ClinicalRouter._alias_pattern.cache_info()
    ClinicalRouter._alias_pattern("ketamine")
    ClinicalRouter._alias_pattern("ketamine")
    info_after = ClinicalRouter._alias_pattern.cache_info()
    assert info_after.hits > info_before.hits
