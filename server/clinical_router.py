"""
EdgeCDSS — Clinical Router
Version: 1.0.0

Uses protocol_index.json, safety_rules.json, and query_aliases.json
to route clinical queries to the correct JTS protocol before ChromaDB search.

Replaces keyword-based pre-gates in openai_client.py with JSON-backed routing.

Usage:
  from clinical_router import ClinicalRouter
  router = ClinicalRouter()
  result = router.route(query, patient_ctx, full_query_history)
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# POISONING / TOXIDROME DETECTION
# ─────────────────────────────────────────────────────────────────────────────
#
# Why this lives in the router module and not beside looks_like_sepsis() in
# openai_client: both the deterministic pre-gates and route() need it, and
# clinical_router is the lower module in the import graph — openai_client
# imports this one, and the reverse would be a cycle. It is vocabulary, which
# is what this module already holds (CONTEXT_DEPENDENT_ALIASES,
# GENERIC_ROUTING_TERMS).
#
# What it is for (2026-09-03 feedback review, entry 44): "I have a patient who
# overdosed on beta blockers. HR 30, BP 50/20" was answered as SEPSIS. A named
# toxidrome is an out-of-corpus question — the JTS bank is 89 trauma CPGs and
# holds no beta-blocker, CCB, TCA, opioid or organophosphate protocol — so the
# honest answer is the general-reference banner, not the nearest in-corpus
# shock card served with full confidence.
#
# INTENT fires on its own. An AGENT NAME never does: "give fentanyl 50 mcg" is
# a prescription and "opioid overdose" is a poisoning, and the word that
# separates them is the intent, not the drug. Agent names widen the detector
# only where an exposure cue supplies the same meaning that intent would
# ("organophosphate exposure from a farm sprayer" names no overdose).
_POISONING_INTENT = (
    # Inflections are listed rather than matched by prefix, for the reason
    # _SHOCK_WORDS gives: a loose right-hand boundary is how "ams" came to
    # match "milligrams". Every hit here changes how a casualty is routed.
    "overdose", "overdosed", "overdosing", "overdoses",
    "od on", "od'd", "od'ed",
    "ingested", "ingestion", "swallowed",
    "poisoning", "poisoned", "self-poisoning",
    "took too much", "toxidrome", "toxicity", "intoxication",
    "tox screen", "poison control",
)

_EXPOSURE_CUES = (
    "exposure", "exposed", "contaminated", "contamination",
    "inhaled", "huffed", "drank",
)

_POISONING_AGENTS = (
    # Cardiac — the three whose antidotes the corpus does not carry
    # (glucagon, calcium/high-dose insulin, bicarbonate).
    "beta blocker", "beta blockers", "beta-blocker", "beta-blockers",
    "metoprolol", "propranolol", "atenolol", "labetalol",
    "calcium channel blocker", "calcium channel blockers",
    "calcium-channel blocker", "calcium-channel blockers",
    "ccb", "diltiazem", "verapamil", "amlodipine", "nifedipine",
    "digoxin", "digitalis",
    "tca", "tcas", "tricyclic", "tricyclics",
    "amitriptyline", "nortriptyline", "imipramine",
    # Opioid and sedative.
    "opioid", "opioids", "opiate", "opiates", "heroin",
    "oxycodone", "oxycontin", "methadone", "fentanyl patch",
    "benzodiazepine", "benzodiazepines", "barbiturate", "barbiturates",
    # Cholinergic / chemical agents.
    "organophosphate", "organophosphates", "nerve agent", "nerve agents",
    "sarin", "soman", "tabun", "vx", "carbamate",
    "insecticide", "pesticide", "cyanide", "carbon monoxide", "chlorine gas",
    # Common civilian ingestions.
    "acetaminophen", "paracetamol", "tylenol", "salicylate", "salicylates",
    "sulfonylurea", "glyburide", "glipizide",
    "methanol", "ethylene glycol", "antifreeze",
    "lithium", "hydrocarbon", "hydrocarbons",
)


def _anchored(terms) -> "re.Pattern":
    """One word-anchored alternation over a term group.

    Longest-first so "beta blockers" is tried before "beta blocker" — with
    both ends anchored the shorter would not match the plural anyway, and
    ordering makes that independent of the tuple's order.
    """
    body = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + body + r")(?!\w)")


_POISONING_INTENT_RE = _anchored(_POISONING_INTENT)
_EXPOSURE_CUES_RE = _anchored(_EXPOSURE_CUES)
_POISONING_AGENTS_RE = _anchored(_POISONING_AGENTS)


def looks_like_poisoning(query: str) -> bool:
    """Whether the query presents a poisoning, overdose or toxidrome."""
    q = (query or "").lower()
    if _POISONING_INTENT_RE.search(q):
        return True
    return bool(_POISONING_AGENTS_RE.search(q) and _EXPOSURE_CUES_RE.search(q))


@dataclass
class RoutingResult:
    """Output of the clinical router."""
    matched_protocol: Optional[str]       # protocol_id or None
    protocol_title: Optional[str]
    clinical_domain: Optional[str]
    missing_context: list                  # what we need before answering
    safety_concerns: list                  # hard stops identified
    enhanced_search_query: str            # improved ChromaDB query
    aliases_resolved: list                # slang terms resolved
    confidence: str                       # HIGH / MEDIUM / LOW


class ClinicalRouter:
    """
    Routes clinical queries to JTS protocols using structured JSON index.
    Replaces string-matching keyword gates.
    """

    def __init__(self, app_dir: str = None):
        # default: alongside this file (server/); override with CDSS_APP_DIR
        import os
        self.app_dir = Path(app_dir or os.getenv("CDSS_APP_DIR") or Path(__file__).parent)
        self.protocol_index = self._load_json("protocol_index.json")
        self.safety_rules = self._load_json("safety_rules.json")
        self.query_aliases = self._load_json("query_aliases.json")

        # Build fast lookup structures
        self._term_patterns = {}
        self._build_lookup_index()

    def _load_json(self, filename: str) -> dict:
        path = self.app_dir / filename
        if not path.exists():
            print(f"⚠️  {filename} not found. Run tools/build_protocol_index.py first.")
            return {}
        with open(path) as f:
            return json.load(f)

    def _build_lookup_index(self):
        """Build reverse lookup: term → protocol_id list."""
        self.term_to_protocols = {}

        for protocol_id, meta in self.protocol_index.items():
            all_terms = (
                meta.get("aliases", []) +
                meta.get("primary_conditions", []) +
                meta.get("medications", []) +
                meta.get("procedures", []) +
                meta.get("search_terms", [])
            )
            for term in all_terms:
                t = term.lower().strip()
                if t not in self.term_to_protocols:
                    self.term_to_protocols[t] = []
                if protocol_id not in self.term_to_protocols[t]:
                    self.term_to_protocols[t].append(protocol_id)

        # Compile every term's matcher now, so the first clinical query of the
        # day is not the one that pays for 625 regex compilations.
        for t in self.term_to_protocols:
            self._term_pattern(t)

    # F-6 (eval baseline). Short alias keys that are ordinary English words or
    # ordinary clinical abbreviations with a second meaning. Word anchoring
    # cannot help here — the collision IS the whole word — so these resolve
    # only when a second term pointing at the same protocol also matched.
    #
    # Measured: "his K is 6.8 and the ECG has peaked T waves" resolved
    # k -> ketamine and searched a hyperkalaemia emergency as a ketamine
    # question (G-TRP-12).
    # Only keys whose STANDARD names something in the protocol index are here.
    # Corroboration is measured against index terms, so a key whose standard
    # names nothing can never be corroborated — putting it here would not
    # guard it, it would silently kill it. Measured: "cat" -> combat
    # application tourniquet, "map" -> mean arterial pressure, "pa" ->
    # physician assistant and "mag" -> magnesium sulfate all name nothing in
    # the index, so they keep their v4.1 behaviour (word-anchored, resolving
    # freely) and are noted in the PR rather than quietly disabled.
    # test_every_context_dependent_key_is_corroborable pins this.
    CONTEXT_DEPENDENT_ALIASES = frozenset({
        "k", "hs", "cold", "march", "tube", "pus",
    })

    # Index terms that are ordinary clinical prose rather than a topic. A term
    # here cannot carry a routing ON ITS OWN; corroborated by any second
    # matched term it counts normally.
    #
    # This is a stoplist and not a rule because no rule in the data works.
    # Measured over the 625 index terms and the 160-scenario bank:
    #   - document frequency does not separate them: "treatment" claims ONE
    #     protocol and "burns" claims three.
    #   - index field does not: "resuscitation" is in primary_conditions,
    #     "hypothermia" is only in search_terms and is good.
    #   - term LENGTH is inverted: "tbi" is 3 characters and correct,
    #     "resuscitation" is 13 and wrong.
    # So the generic terms are a DATA defect in protocol_index.json, and this
    # is the narrowest place to neutralise them without editing the clinical
    # index. Both entries below are measured misroutes:
    #   "what are the criteria for terminating resuscitation in the field"
    #        -> Burn Care [HIGH]                                (G-GEN-05)
    #   "what does a rising end tidal CO2 tell me during a resuscitation"
    #        -> Burn Care [HIGH]                                (G-GEN-03)
    #   "his K is 6.8 ... what is the order of treatment"
    #        -> Medical Management of Chemical Agent Exposure   (G-TRP-12)
    # FLAGGED FOR OWNER REVIEW: this list is routing vocabulary, and the
    # durable fix is removing these words from the index entries that claim
    # them.
    GENERIC_ROUTING_TERMS = frozenset({"resuscitation", "treatment"})

    def _protocols_for_alias(self, alias: str) -> set:
        """Protocols the alias points at, via its key and its standard term.

        The standard is prose — "ketamine (context-dependent)", "sepsis
        (context-dependent)" — so the parenthetical is stripped and the
        remainder tried whole and word by word. An alias whose standard names
        nothing in the index has no protocols, and therefore can never be
        corroborated: it fails closed, which is the right direction for a
        token this ambiguous.
        """
        out = set(self.term_to_protocols.get(alias, ()))
        standard = re.sub(r'\([^)]*\)', ' ', self.query_aliases.get(alias, "")).lower()
        out |= set(self.term_to_protocols.get(standard.strip(), ()))
        for word in standard.split():
            out |= set(self.term_to_protocols.get(word, ()))
        return out

    def _term_pattern(self, term: str):
        """Word-boundary matcher for a protocol-index term.

        Compiled ONCE per term at index-build time. Compiling on every call
        cost 125 ms per route() against 625 index terms — measured, and a
        180x regression on the 0.7 ms this took before word anchoring. The
        router runs on every query that reaches retrieval.

        The same fix F-2 applied to the alias table, which was never applied to
        term_to_protocols. Measured: "organophosphate exposure from a farm
        sprayer" matched the index term "pra" inside "s-pra-yer" and routed to
        Progressive Return to Activity at HIGH confidence.
        """
        cached = self._term_patterns.get(term)
        if cached is None:
            cached = re.compile(r'(?<!\w)' + re.escape(term) + r'(?!\w)')
            self._term_patterns[term] = cached
        return cached

    @staticmethod
    @lru_cache(maxsize=512)
    def _alias_pattern(alias: str):
        """Word-boundary matcher for one alias key.

        Lookarounds rather than \\b because several keys are multi-word
        ("push dose epi", "rocky onium", "vitamin k") and behave predictably
        at both ends regardless of their first and last characters.
        """
        return re.compile(r'(?<!\w)' + re.escape(alias) + r'(?!\w)')

    def resolve_aliases(self, query: str) -> tuple[str, list]:
        """Replace field slang with standard clinical terms.

        Matched on word boundaries (F-2, v4.1). Plain substring matching made
        44 of the 88 alias keys fire inside longer words: "patient" resolved
        "pa" -> physician assistant, "dka"/"34kg" resolved "k" -> ketamine,
        "medication" resolved "cat" -> combat application tourniquet. Measured
        over the 135 logged queries, that injected 143 spurious terms (187 ->
        44 hits) into the ChromaDB search string.
        """
        q = query.lower()
        resolved = []
        enhanced = query

        matched = [alias for alias in self.query_aliases
                   if self._alias_pattern(alias).search(q)]
        # Protocol-index terms present in the query. Corroboration is measured
        # against THESE, not against other aliases: the ruling is "resolves
        # only with a second same-protocol term present", and an alias rarely
        # has a second alias beside it.
        query_terms = {t for t in self.term_to_protocols
                       if self._term_pattern(t).search(q)}

        for alias in matched:
            if alias in self.CONTEXT_DEPENDENT_ALIASES:
                mine = self._protocols_for_alias(alias)
                corroborated = any(
                    term != alias and set(self.term_to_protocols[term]) & mine
                    for term in query_terms)
                if not corroborated:
                    continue
            standard = self.query_aliases[alias]
            resolved.append(f"{alias} → {standard}")
            # Don't replace in query text — just note the resolution
            # Use standard term for search enhancement
            enhanced = enhanced + " " + standard

        return enhanced, resolved

    def check_safety_rules(self, query: str, full_history: str) -> list:
        """Check query against safety rules. Return list of concerns."""
        concerns = []
        combined = (full_history + " " + query).lower()

        for rule_id, rule in self.safety_rules.items():
            # Check if this drug/intervention is being requested
            drug = rule.get("drug", rule.get("drug_or_intervention", "")).lower()
            never_give = [x.lower() for x in rule.get("never_give", [])]

            # Check WPW-type rules
            if rule.get("condition", "").lower() in combined:
                for forbidden in never_give:
                    if forbidden in combined:
                        concerns.append(
                            f"SAFETY: {rule.get('condition')} — do not give {forbidden}. "
                            f"Reason: {rule.get('reason', 'contraindicated')}"
                        )

            # Check drug contraindications
            if drug and drug in combined:
                for contra in rule.get("contraindications", []):
                    # Simple check — could be made more sophisticated
                    contra_terms = contra.lower().split()[:3]
                    if all(t in combined for t in contra_terms if len(t) > 3):
                        concerns.append(
                            f"SAFETY: {drug} may be contraindicated — {contra}"
                        )

        return concerns

    def identify_missing_context(self, protocol_id: str, patient_ctx) -> list:
        """Return list of required context that's currently missing."""
        if not protocol_id or protocol_id not in self.protocol_index:
            return []

        required = self.protocol_index[protocol_id].get("required_context", [])
        missing = []

        for req in required:
            req_lower = req.lower()
            if "weight" in req_lower and not getattr(patient_ctx, "confirmed_weight_kg", None):
                missing.append("confirmed patient weight in kg")
            elif "access" in req_lower and getattr(patient_ctx, "access_state", "UNKNOWN") == "UNKNOWN":
                missing.append("IV/IO access status")
            elif "route" in req_lower and getattr(patient_ctx, "route_preference", "UNKNOWN") == "UNKNOWN":
                missing.append("administration route (IV or IM)")
            elif "time" in req_lower and "injury" in req_lower:
                missing.append("time since injury (critical for TXA eligibility)")
            elif "mechanism" in req_lower:
                missing.append("mechanism of injury")

        return missing

    def route(self, query: str, patient_ctx=None, full_history: str = "") -> RoutingResult:
        """
        Route a clinical query to the best matching JTS protocol.
        Returns RoutingResult with protocol match, missing context, and enhanced search query.
        """
        # Step 1: Resolve aliases
        enhanced_query, aliases_resolved = self.resolve_aliases(query)

        # Step 2: Score protocols by term matches.
        # Word-anchored (F-6): bare `term in combined` matched "pra" inside
        # "sprayer". Distinct terms are tracked alongside the score, because
        # the score alone cannot tell one term counted twice from two terms.
        combined = (full_history + " " + query).lower()
        q_lower = query.lower()
        scores = {}
        terms_hit = {}

        for term, protocol_ids in self.term_to_protocols.items():
            pattern = self._term_pattern(term)
            in_combined = pattern.search(combined) is not None
            in_query = pattern.search(q_lower) is not None
            if not in_combined and not in_query:
                continue
            for pid in protocol_ids:
                if in_combined:
                    scores[pid] = scores.get(pid, 0) + 1
                if in_query:
                    scores[pid] = scores.get(pid, 0) + 2  # current query worth more
                terms_hit.setdefault(pid, set()).add(term)

        # Step 3: Find best match
        matched_protocol = None
        protocol_title = None
        clinical_domain = None
        confidence = "LOW"

        if scores:
            best_pid = max(scores, key=scores.get)
            best_score = scores[best_pid]
            hits = terms_hit.get(best_pid, set())
            # One distinct term is the NORM, not a weak signal — measured over
            # the bank, a typical query matches exactly one index term, so
            # requiring two would disable routing almost entirely and take the
            # burn-narrative mitigation with it (the +0.118 the 2026-08-21
            # retrieval diagnosis attributes to the router).
            #
            # So: a routing needs at least one term that is not generic prose,
            # OR two distinct terms — a generic term corroborated by a second
            # term is a real signal.
            specific = (bool(hits - self.GENERIC_ROUTING_TERMS)
                        or len(hits) >= 2)

            if specific and best_score >= 3:
                confidence = "HIGH"
            elif specific and best_score >= 1:
                confidence = "MEDIUM"

            if specific and best_score >= 1:
                matched_protocol = best_pid
                meta = self.protocol_index.get(best_pid, {})
                protocol_title = meta.get("title", best_pid)
                clinical_domain = meta.get("clinical_domain", "unknown")

                # Add protocol search terms to enhanced query
                search_terms = meta.get("search_terms", [])[:5]
                if search_terms:
                    enhanced_query += " " + " ".join(search_terms)

        # Step 4: Check safety rules
        safety_concerns = self.check_safety_rules(query, full_history)

        # Step 5: Identify missing context
        missing_context = self.identify_missing_context(matched_protocol, patient_ctx)

        return RoutingResult(
            matched_protocol=matched_protocol,
            protocol_title=protocol_title,
            clinical_domain=clinical_domain,
            missing_context=missing_context,
            safety_concerns=safety_concerns,
            enhanced_search_query=enhanced_query.strip(),
            aliases_resolved=aliases_resolved,
            confidence=confidence
        )

    def get_protocol_summary(self, protocol_id: str) -> dict:
        """Return full metadata for a protocol."""
        return self.protocol_index.get(protocol_id, {})

    def get_all_domains(self) -> dict:
        """Return count of protocols per clinical domain."""
        domains = {}
        for meta in self.protocol_index.values():
            d = meta.get("clinical_domain", "unknown")
            domains[d] = domains.get(d, 0) + 1
        return dict(sorted(domains.items(), key=lambda x: -x[1]))

    def test_routing(self, queries: list):
        """Quick test of routing on a list of queries."""
        print("\nClinical Router Test")
        print("=" * 60)
        for query in queries:
            result = self.route(query)
            print(f"\nQuery: {query}")
            print(f"  Protocol: {result.protocol_title or 'No match'} [{result.confidence}]")
            print(f"  Domain: {result.clinical_domain or 'unknown'}")
            if result.aliases_resolved:
                print(f"  Aliases: {', '.join(result.aliases_resolved[:2])}")
            if result.missing_context:
                print(f"  Missing: {', '.join(result.missing_context[:2])}")
            if result.safety_concerns:
                print(f"  ⚠️  Safety: {result.safety_concerns[0][:80]}")
            print(f"  Search: {result.enhanced_search_query[:80]}")


if __name__ == "__main__":
    # Run a quick test after building the index
    router = ClinicalRouter()

    print(f"\nLoaded {len(router.protocol_index)} protocols")
    print(f"Domains: {router.get_all_domains()}")

    test_queries = [
        "need to give ketamine to a 6yo with arm fx",
        "patient has bp 70/40 active abdominal bleeding no fever",
        "failed intubation failed igel patient desaturating",
        "80kg male temp 38.2C pus draining from wound initiate DCR",
        "patient with WPW give adenosine",
        "need to RSI an 80kg trauma patient",
        "septic patient give TXA",
        "need to give blood",
        "will albuterol work for this patient",
        "now they are in vtach",
    ]

    router.test_routing(test_queries)
