"""D2b (owner, 2026-10-04 #129 review, 2026-10-05 split, 2026-10-06 rulings): the
generator prompt asks for the canonical headers.

B2 normalises what a model writes; the prompt itself still asked for the drift.
Its second template ("RESPONSE FORMAT — NON-JTS SCOPE") asked for a condition
explainer ("**[CONDITION]** — What it is: … Why it matters: …"), TREAT, and
"WATCH FOR | TLDR | SOURCE" on one line, with no DON'T or EVAC; the first asked
for EVAC IF. The owner's rulings: drop the explainer; the canonical set in both
templates (DO THIS, GIVE, WATCH, DON'T, EVAC, TLDR, SOURCE), with BRIEF, DRIP,
VENT and POST-INTUBATION SEDATION kept (B2). Deterministic cards are untouched.
"""
import os
import re

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import brief  # noqa: E402
import openai_client as oc  # noqa: E402

BASE = oc.GENERATOR_BASE
HEADER_RE = re.compile(r"^\*\*([^*a-z]*[A-Z\[][^*a-z]*)\*\*", re.MULTILINE)


def _template(title):
    start = BASE.index(f"RESPONSE FORMAT — {title}")
    nxt = BASE.find("RESPONSE FORMAT — ", start + 10)
    return BASE[start: nxt if nxt != -1 else len(BASE)]


def _headers(text):
    return [h.strip() for h in HEADER_RE.findall(text)]


def test_every_header_the_prompt_asks_for_is_canonical_or_kept():
    for title in ("JTS SCOPE", "NON-JTS SCOPE"):
        for h in _headers(_template(title)):
            mapped = brief.canonical_header(h)
            assert mapped == "KEEP" or (isinstance(mapped, tuple) and mapped == (h, "")), (title, h)


def test_the_drift_is_gone():
    for word in ("**TREAT**", "**WATCH FOR**", "**EVAC IF**", "**[CONDITION]**",
                 "What it is:", "Why it matters:"):
        assert word not in BASE, word


def test_the_second_template_has_the_whole_canonical_set():
    assert _headers(_template("NON-JTS SCOPE")) == [
        "BRIEF", "DO THIS", "GIVE", "WATCH", "DON'T", "EVAC", "TLDR", "SOURCE"]


def test_the_first_template_asks_for_evac():
    assert _headers(_template("JTS SCOPE")) == [
        "BRIEF", "DO THIS", "GIVE", "DRIP", "VENT", "POST-INTUBATION SEDATION",
        "WATCH", "DON'T", "EVAC", "TLDR", "SOURCE"]


def test_the_truncation_notice_names_the_canonical_sections():
    assert "EVAC IF" not in oc.TRUNCATED_NOTICE and "EVAC" in oc.TRUNCATED_NOTICE
