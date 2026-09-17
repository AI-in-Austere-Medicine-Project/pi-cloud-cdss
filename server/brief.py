"""
EdgeCDSS — the brief. Answer first, depth on request.

Every response carries a `brief`: at most three short lines a medic can act on
without reading the card underneath. The card is not shortened and is not
rewritten; it is still served whole in `response`. The brief is a PROJECTION of
it, and that is the only thing that makes it safe to put first:

  1. **No new clinical content.** Every line is lifted from a section the
     response already contains — a safety hold, a GIVE line, the TLDR, a DO THIS
     step, a contraindication. The only words this module adds are the joins
     between items ("Contraindicated — ", " · ").

  2. **A dose goes in verbatim or not at all.** If the response has a dose line
     under GIVE, POST-INTUBATION SEDATION or DRIP, that line's drug, dose and
     route go in exactly as printed, up to its `Indication:` clause. The
     canonical "Draw X mL of Ymg/mL drug route (Z mg)" survives intact, so
     CANONICAL_GIVE_RE reads the same numbers off the brief that it reads off
     the card. A candidate line that states a dose in other words is dropped
     rather than risk a second, differently-worded number on top of the screen.
     When the brief carries more than one dose, each is prefixed with what it
     is for — its own Indication clause, in brackets, or its section's name
     when it has none. RSI serves ketamine twice, 160 mg to induce and 40 mg to
     sedate after the tube, and two bare "ketamine IV" doses side by side is
     how one gets given for the other.

  3. **What must not be missed is required.** A safety hold, a gate question, a
     pre-gate refusal headline, and every critical contraindication are
     REQUIRED lines: they are placed before anything optional, and when they do
     not fit in three lines they are joined onto fewer lines rather than
     dropped. Brevity loses to those, every time.

"Critical" is a structural rule, not a clinical judgement made here:
  - a CONTRAINDICATIONS item that records something (the "None recorded" line
    is a gap in the record, not a contraindication);
  - a DON'T item that says "never", says "contraindicated", or names a drug the
    response is dosing — the generator is told to put a dosed drug's signed
    contraindications in DON'T, so that is where they arrive on that path.
The sections holding critical items are returned as `critical_sections`, which
is how the client knows not to collapse them.

This module reads text and returns text. It is called once, at the end of
openai_client._finalise, after the gate and after every notice, so nothing in
it can reach what the gate saw or change what the gate decided.
"""

import re

MAX_LINES = 3

# Owned by openai_client.build_safety_hold. Restated rather than imported so
# this module stays importable on its own; test_brief pins the two together.
HOLD_OPENER = "Clinical safety hold. This response was blocked."
HOLD_ISSUES_LABEL = "Issues identified:"
DISCLAIMER = "Guideline-based support only. Not a substitute for clinical judgment."

# The sections whose items are doses. Everything under them that states a
# number with a unit is a dose line for the purposes of rule 2.
DOSE_SECTIONS = ("GIVE", "POST-INTUBATION SEDATION", "DRIP")
# Where the generator's own brief arrives, and where the fallbacks come from,
# in the order they are tried.
BRIEF_SECTION = "BRIEF"
SUMMARY_SECTIONS = ("TLDR",)
ACTION_SECTIONS = ("DO THIS", "DO NOW", "TREAT", "SETTINGS")
CONTRAINDICATION_SECTIONS = ("CONTRAINDICATIONS",)
DONT_SECTIONS = ("DON'T", "DONT", "DO NOT")

# A line longer than this is not a brief line. Only OPTIONAL candidates are
# held to it — a required line is never dropped for its length.
OPTIONAL_MAX_CHARS = 180

# A heading is a bold run with no lower-case letters: **GIVE**, **DON'T**,
# **SOURCE**: text. The rule is what keeps the notices out — "🔄 **Starting a
# new patient…**" and "⚠️ **Couldn't read that vital…**" are bold sentences,
# not headings — and the per-drug lines of "why this dose?" with them.
_HEADING_RE = re.compile(r"^\s*(?:⚠️\s*)?\*\*([^*a-z]*[A-Z][^*a-z]*)\*\*:?\s*(.*)$")
_ITEM_RE = re.compile(r"^(?:[-•*]|\d+[.)])\s+")
_DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*"
    r"(?:mg|mcg|µg|g|ml|units?|meq|iu)\b", re.IGNORECASE)
_NEVER_RE = re.compile(r"\b(?:never|contraindicat\w*)\b", re.IGNORECASE)
_CONTRA_ITEM_RE = re.compile(r"^(.+?) — .+?: (.+)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _norm_heading(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("’", "'")).strip().upper()


def _clean(line: str) -> str:
    """One line as it should read in the brief: no list marker, no bold."""
    return _ITEM_RE.sub("", line.strip()).replace("**", "").strip()


def parse_sections(text: str):
    """(preamble_paragraphs, [(heading, [lines])]).

    The preamble is everything before the first heading, split into
    paragraphs. Section lines keep their indentation so a top-level item can be
    told from a sub-bullet.
    """
    preamble, sections = [], []
    current = None
    buf = []
    for raw in (text or "").splitlines():
        m = _HEADING_RE.match(raw)
        if m:
            if current is None:
                preamble = _paragraphs(buf)
            current = (_norm_heading(m.group(1)), [])
            sections.append(current)
            rest = m.group(2).strip()
            # "**GIVE** [use ALLOWED_DOSES values exactly]" is a template echo.
            if rest and not rest.startswith("["):
                current[1].append(rest)
            continue
        if current is None:
            buf.append(raw)
        elif (current[0] == BRIEF_SECTION and not raw.strip()
              and any(l.strip() for l in current[1])):
            # The brief is a short block. Whatever follows it without a heading
            # of its own is answer text, not brief, and must not be read — or
            # hidden by a client — as part of it.
            current = ("", [])
            sections.append(current)
        else:
            current[1].append(raw)
    if current is None:
        preamble = _paragraphs(buf)
    return preamble, sections


def _paragraphs(lines):
    out, cur = [], []
    for line in lines:
        if line.strip():
            cur.append(line.strip())
        elif cur:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def _top_items(lines):
    """Top-level items of a section, cleaned. Sub-bullets and banners excluded."""
    items = []
    for line in lines:
        if not line.strip() or line.startswith("  "):
            continue
        s = line.strip()
        if s == DISCLAIMER or s.startswith("⚠️"):
            continue
        c = _clean(s)
        if c:
            items.append(c)
    return items


def _section(sections, names):
    out = []
    for name, lines in sections:
        if name in names:
            out += _top_items(lines)
    return out


def _is_notice(paragraph: str) -> bool:
    # The boundary reset, the unreadable-vital note, the stripped-volume note
    # and the general-reference label. They are about the answer, not in it,
    # and the client renders them on their own, unfolded.
    return paragraph.startswith(("⚠️", "🔄"))


def dose_clause(item: str) -> str:
    """A dose line up to its Indication clause, otherwise exactly as printed."""
    idx = item.find(" Indication:")
    return (item[:idx] if idx >= 0 else item).rstrip()


def dose_label(section: str, item: str) -> str:
    """What a dose is for, in the card's own words.

    The Indication clause when there is one, otherwise the section it sits
    under. An indication that itself states a dose ("pain, max 3 doses of 50
    mg") is not used: that would be a second number on the line, and rule 2 is
    that a dose is said once. GIVE is not a label, so a GIVE line with no
    indication gets none.
    """
    idx = item.find(" Indication:")
    if idx >= 0:
        indication = item[idx + len(" Indication:"):].strip().rstrip(". ").strip()
        if indication and not _DOSE_RE.search(indication):
            return indication
    return "" if section == "GIVE" else section


def _dosed_drugs(clauses, medication_terms):
    text = " ".join(clauses).lower()
    return {t for t in medication_terms
            if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text)}


def _contraindication_lines(items):
    """Recorded contraindications, one per drug, in the card's own words."""
    by_drug, order = {}, []
    for item in items:
        if item.lower().startswith("none recorded"):
            continue
        m = _CONTRA_ITEM_RE.match(item)
        drug, what = (m.group(1), m.group(2)) if m else ("", item)
        if drug not in by_drug:
            by_drug[drug] = []
            order.append(drug)
        what = what.rstrip(". ")
        if what not in by_drug[drug]:
            by_drug[drug].append(what)
    return [f"Contraindicated — {d}: {'; '.join(by_drug[d])}." if d
            else f"Contraindicated — {'; '.join(by_drug[d])}."
            for d in order]


def _fit(lead, doses, optional, critical):
    """Assemble at most MAX_LINES lines. Required groups merge; never drop."""
    groups = [list(lead), list(doses), list(critical)]

    def count():
        return sum(len(g) for g in groups)

    # Merge order: doses first (one line reads as one bundle), then the
    # critical group, then the lead. Each merge keeps every word.
    for i in (1, 2, 0):
        if count() > MAX_LINES and len(groups[i]) > 1:
            groups[i] = [" · ".join(groups[i])]
    lead_l, dose_l, crit_l = groups
    if count() > MAX_LINES:
        flat = lead_l + dose_l + crit_l
        flat = flat[:MAX_LINES - 1] + [" · ".join(flat[MAX_LINES - 1:])]
        return flat
    room = MAX_LINES - count()
    return lead_l + dose_l + list(optional[:room]) + crit_l


def build_brief(response_text: str, medication_terms=()) -> dict:
    """{"brief": str, "critical_sections": [str]} for one served response."""
    preamble, sections = parse_sections(response_text)
    content = [p for p in preamble if not _is_notice(p) and p != DISCLAIMER]

    # ── A safety hold is the whole brief ────────────────────────────────────
    if content and content[0].startswith(HOLD_OPENER):
        issues = []
        text = response_text or ""
        start = text.find(HOLD_ISSUES_LABEL)
        if start >= 0:
            for line in text[start + len(HOLD_ISSUES_LABEL):].splitlines():
                if not line.strip():
                    if issues:
                        break
                    continue
                if not _ITEM_RE.match(line.strip()):
                    break
                issues.append(_clean(line))
        tail = [p for p in content[1:] if not p.startswith(HOLD_ISSUES_LABEL)]
        lead = [HOLD_OPENER]
        if issues:
            lead.append(f"{HOLD_ISSUES_LABEL} {'; '.join(issues)}")
        lead += tail[:1]
        return {"brief": "\n".join(_fit(lead, [], [], [])), "critical_sections": []}

    # ── No sections: a gate question, an ask, a refusal, reference prose ────
    # Both generator prompts say "lead with the answer", and every fixed
    # no-section response is one paragraph, so the brief is the first
    # paragraph's own sentences, up to the limit.
    if not sections:
        first = content[0] if content else ""
        lead = [s for s in _SENTENCE_RE.split(first) if s.strip()][:MAX_LINES]
        return {"brief": "\n".join(_clean(s) for s in lead), "critical_sections": []}

    # ── Sections ────────────────────────────────────────────────────────────
    # A preamble paragraph ahead of the sections is a pre-gate headline — the
    # sepsis-DCR refusal leads with its refusal. Required.
    lead = [_clean(content[0])] if content else []

    dose_items = [(name, item) for name, lines in sections if name in DOSE_SECTIONS
                  for item in _top_items(lines) if _DOSE_RE.search(item)]
    clauses = [dose_clause(item) for _, item in dose_items]
    dosed = _dosed_drugs(clauses, medication_terms)
    doses = clauses
    if len(dose_items) > 1:
        labels = [dose_label(name, item) for name, item in dose_items]
        doses = [f"[{label}] {clause}" if label else clause
                 for label, clause in zip(labels, clauses)]

    critical, critical_sections = [], []
    contra = _contraindication_lines(_section(sections, CONTRAINDICATION_SECTIONS))
    if contra:
        critical += contra
    for name, lines in sections:
        if name in CONTRAINDICATION_SECTIONS and contra and name not in critical_sections:
            critical_sections.append(name)
        if name in DONT_SECTIONS:
            hits = [i for i in _top_items(lines)
                    if _NEVER_RE.search(i)
                    or any(re.search(r"(?<!\w)" + re.escape(d) + r"(?!\w)", i.lower())
                           for d in dosed)]
            if hits:
                critical += hits
                if name not in critical_sections:
                    critical_sections.append(name)

    # Optional lines, in priority order: the generator's own BRIEF when it
    # wrote one, then the TLDR (the fallback the prompt contract names), then
    # the first actions, then — for a card with none of those, like "why this
    # dose?" — the top of its first section.
    seen = {x.lower() for x in lead + doses + critical}
    optional = []
    pools = (_section(sections, (BRIEF_SECTION,)),
             _section(sections, SUMMARY_SECTIONS),
             _section(sections, ACTION_SECTIONS),
             _top_items(sections[0][1]))
    for pool in pools:
        for item in pool:
            c = _clean(item)
            if (not c or c.lower() in seen or len(c) > OPTIONAL_MAX_CHARS
                    or c.startswith("[")):
                continue
            # Rule 2: once the response doses, the dose is said once, in the
            # GIVE line's own words.
            if doses and _DOSE_RE.search(c):
                continue
            seen.add(c.lower())
            optional.append(c)

    lines = _fit(lead, doses, optional, critical)
    return {"brief": "\n".join(lines), "critical_sections": critical_sections}
