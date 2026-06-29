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
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


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

    def __init__(self, app_dir: str = "/home/akaclinicalco/cdss-cloud/app"):
        self.app_dir = Path(app_dir)
        self.protocol_index = self._load_json("protocol_index.json")
        self.safety_rules = self._load_json("safety_rules.json")
        self.query_aliases = self._load_json("query_aliases.json")

        # Build fast lookup structures
        self._build_lookup_index()

    def _load_json(self, filename: str) -> dict:
        path = self.app_dir / filename
        if not path.exists():
            print(f"⚠️  {filename} not found. Run build_protocol_index.py first.")
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

    def resolve_aliases(self, query: str) -> tuple[str, list]:
        """Replace field slang with standard clinical terms."""
        q = query.lower()
        resolved = []
        enhanced = query

        for alias, standard in self.query_aliases.items():
            if alias in q:
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

        # Step 2: Score protocols by term matches
        combined = (full_history + " " + query).lower()
        scores = {}

        for term, protocol_ids in self.term_to_protocols.items():
            if term in combined:
                for pid in protocol_ids:
                    scores[pid] = scores.get(pid, 0) + 1

        # Boost score for terms in current query (not just history)
        q_lower = query.lower()
        for term, protocol_ids in self.term_to_protocols.items():
            if term in q_lower:
                for pid in protocol_ids:
                    scores[pid] = scores.get(pid, 0) + 2  # current query worth more

        # Step 3: Find best match
        matched_protocol = None
        protocol_title = None
        clinical_domain = None
        confidence = "LOW"

        if scores:
            best_pid = max(scores, key=scores.get)
            best_score = scores[best_pid]

            if best_score >= 3:
                confidence = "HIGH"
            elif best_score >= 1:
                confidence = "MEDIUM"

            if best_score >= 1:
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
