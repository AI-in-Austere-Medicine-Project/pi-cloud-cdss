"""
EdgeCDSS — the brief. Answer first, depth on request.

Every response carries a `brief`: at most three short lines a medic can act on
without reading the card underneath. The card is not shortened and is not
rewritten; it is still served whole in `response`. The brief is a PROJECTION of
it, and that is the only thing that makes it safe to put first:

  1. **No new clinical content.** Every line is lifted from a section the
     response already contains — a safety hold, a GIVE line, the TLDR, a DO THIS
     step, a contraindication — or states a value computed from what the card
     was computed from. The only words this module adds are joins ("Contraindicated
     — ", " · ") and the two computed phrasings under rule 2.

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

     Two computed additions, each derived from the same source the card used
     and omitted rather than guessed when they cannot be:
       - the per-kg basis, "(0.25 mg/kg × 25 kg)", when the signed contract
         entry for that drug, route and indication is per-kg and recomputing it
         at the patient's confirmed weight gives exactly the printed dose (a
         capped dose does not, so it gets no basis it does not follow);
       - for a line the card printed with no volume, when exactly ONE
         presentation of that drug is signed: "At 50 mg/mL that's 0.13 mL —
         confirm vial", rounded and bounded by the same syringe rules
         drug_concentrations applies to every volume. Zero or several signed
         presentations, or a volume no syringe can draw, keep the card's own
         no-volume reason. The CONFIRM VIAL block is untouched either way.

  Three slots when the response doses: (a) the dose line(s); (b) the card's
     first next action — the first DO THIS step that is neither equipment
     preamble ("Confirm monitoring and airway equipment ready.") nor a restated
     "Give <the dosed drug>", else the first WATCH line; (c) the critical
     contraindications. A response with no dose keeps the lead / optional /
     critical order below.

  3. **What must not be missed is required.** A safety hold, a gate question, a
     pre-gate refusal headline, and every critical contraindication are
     REQUIRED lines: they are placed before anything optional, and when they do
     not fit in three lines they are joined onto fewer lines rather than
     dropped. Brevity loses to those, every time.

"Critical" is a structural rule, not a clinical judgement made here:
  - a CONTRAINDICATIONS item that records something specific to the drug's
    indication. "None recorded" is a gap in the record, and hypersensitivity /
    allergy is boilerplate every drug carries: both stay in the section, which
    folds, and neither reaches the brief;
  - a DON'T item that says "never", says "contraindicated", or names a drug the
    response is dosing — the generator is told to put a dosed drug's signed
    contraindications in DON'T, so that is where they arrive on that path.
`critical_sections` tells the client what not to fold. It holds the sections
with critical items, and EVERY non-empty DON'T section whether or not a line in
it is critical: models write "Don't give succinylcholine if crush injury", which
the rule above does not catch, and a contraindication one tap away is one a
medic under load does not read. The client never folds DON'T either, so the two
agree without depending on each other.

Sentence case throughout: an all-caps English word ("NO VOLUME", "FENTANYL
DOSING") is lowercased; an acronym (IV, TBI, PEEP, CICO) is not.

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
# Hypersensitivity / allergy: true of every drug, so it tells the medic nothing
# about THIS patient. It stays in the CONTRAINDICATIONS section.
_BOILERPLATE_CONTRA_RE = re.compile(r"\b(?:hypersensitiv\w*|allerg\w*)\b", re.IGNORECASE)
# Equipment readiness said before every procedure, not a next action.
_PREAMBLE_RE = re.compile(
    r"^(?:confirm|ensure|check|verify|have)\b.*\b(?:ready|available|prepared|"
    r"at hand|on hand|set up)\.?$", re.IGNORECASE)
WATCH_SECTIONS = ("WATCH", "WATCH FOR")
# The card's no-volume tail, as render_give_line writes it.
_NO_VOLUME_RE = re.compile(r"^(?P<head>.*?\.)\s+NO VOLUME\s+—\s+(?P<why>.+?)\.?$")
_MG_LINE_RE = re.compile(
    r"^(?P<drug>.+?) (?P<route>\S+): (?P<value>\d+(?:\.\d+)?) (?P<unit>mg|mcg|g)\.$")
_DRAW_LINE_RE = re.compile(
    r"^Draw [\d.]+ mL of [\d.]+ ?mg/mL (?P<drug>.+?) (?P<route>\S+) "
    r"\((?P<value>\d+(?:\.\d+)?) (?P<unit>mg|mcg|g)\)\.$")
_TO_MG = {"mg": 1.0, "mcg": 0.001, "g": 1000.0}
# All-caps tokens of four or more letters that are acronyms, not shouting.
# Three letters and under are left alone (IV, TBI, GCS, TXA): nearly all
# acronyms, and the shouted short words are listed in _SHOUTED_SHORT.
ACRONYMS = frozenset({
    "ACLS", "ARDS", "ASAP", "AVPU", "BIPAP", "CASEVAC", "CICO", "COPD", "CPAP", "CRASH",
    "DOPE", "ECMO", "EFAST", "ETCO2", "FAST", "HRIG", "LTOWB", "MARCH", "MASCAL",
    "MEDEVAC", "NSAID", "NSAIDS", "PALS", "PEEP", "PPE", "RASS", "RSDL", "SIRS",
    "SPO2", "TACEVAC", "TCCC", "ZMIST",
})
_SHOUTED_SHORT = frozenset({"NO", "YES", "DO", "NOT", "AND", "OR", "IF", "NOW",
                            "GIVE", "STOP", "VENT", "THE", "FOR", "TO", "OF"})
_CAPS_TOKEN_RE = re.compile(r"(?<![\w'’-])[A-Z][A-Z'’-]*[A-Z](?![\w'’-])")


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


def _sentence_case(line: str) -> str:
    """Lowercase shouted words, keep acronyms, capitalise a lowered first word."""
    first_lowered = False

    def fix(m):
        nonlocal first_lowered
        word = m.group(0)
        letters = re.sub(r"[^A-Z]", "", word)
        shouted = (word in _SHOUTED_SHORT or
                   (len(letters) >= 4 and word not in ACRONYMS))
        if not shouted:
            return word
        if not line[:m.start()].strip(" [(\"'"):
            first_lowered = True
        return word.lower()

    out = _CAPS_TOKEN_RE.sub(fix, line)
    if first_lowered:
        i = next((k for k, ch in enumerate(out) if ch.isalpha()), None)
        if i is not None:
            out = out[:i] + out[i].upper() + out[i + 1:]
    return out


def _indication(item: str) -> str:
    idx = item.find(" Indication:")
    return item[idx + len(" Indication:"):].strip().rstrip(". ").strip() if idx >= 0 else ""


def per_kg_basis(drug: str, route: str, value: float, unit: str,
                 indication: str, weight_kg) -> str:
    """"(0.25 mg/kg × 25 kg)" when the printed dose IS that product, else "".

    Found from the signed contract entry for this drug, route and indication,
    recomputed with drug_contracts.resolve_dose at the confirmed weight. Only
    when the recomputation reproduces the printed number: a capped dose, a
    different entry, or a generated line whose indication was reworded gets no
    basis rather than one it does not follow.
    """
    if weight_kg is None or not indication:
        return ""
    try:
        import drug_contracts
    except Exception:
        return ""
    for entry in drug_contracts.servable_entries().get(drug, []):
        if entry.get("route") != route or entry.get("indication") != indication:
            continue
        rng = entry.get("dose_range") or {}
        if not rng.get("per_kg") or not isinstance(rng.get("min"), (int, float)):
            continue
        r = drug_contracts.resolve_dose(entry, weight_kg)
        if (r.get("display_value") is None or r.get("display_units") != unit
                or abs(r["display_value"] - value) > 1e-9):
            continue
        return f"({rng['min']:g} {rng['units']} × {weight_kg:g} kg)"
    return ""


def conditional_volume(drug: str, dose_mg: float) -> str:
    """"At 50 mg/mL that's 0.13 mL — confirm vial", or "" to keep the card's line."""
    try:
        import drug_concentrations
    except Exception:
        return ""
    vol, conc = drug_concentrations.single_signed_volume(drug, dose_mg)
    if vol is None:
        return ""
    return f"At {conc:g} mg/mL that's {vol:g} mL — confirm vial."


def dose_line(item: str, weight_kg=None) -> str:
    """One dose, for slot (a): the GIVE clause verbatim, then what it computes to."""
    clause = dose_clause(item)
    m = _NO_VOLUME_RE.match(clause)
    head, why = (m.group("head"), m.group("why")) if m else (clause, None)
    parsed = _MG_LINE_RE.match(head) or _DRAW_LINE_RE.match(head)
    out = head
    if parsed:
        value, unit = float(parsed.group("value")), parsed.group("unit")
        basis = per_kg_basis(parsed.group("drug"), parsed.group("route"), value, unit,
                             _indication(item), weight_kg)
        if basis:
            out = f"{head[:-1]} {basis}."
    if why is not None:
        cond = (conditional_volume(parsed.group("drug"),
                                   float(parsed.group("value")) * _TO_MG[parsed.group("unit")])
                if parsed else "")
        out += " " + (cond or f"No volume — {why}.")
    return out


def _next_action(sections, dosed):
    """Slot (b): the first real step, else the first thing to watch."""
    for item in _section(sections, ACTION_SECTIONS):
        c = _clean(item)
        if not c or _PREAMBLE_RE.match(c) or len(c) > OPTIONAL_MAX_CHARS:
            continue
        low = c.lower()
        if low.startswith("give ") and any(
                re.search(r"(?<!\w)" + re.escape(d) + r"(?!\w)", low) for d in dosed):
            continue
        if _DOSE_RE.search(c):
            continue
        return c
    for item in _section(sections, WATCH_SECTIONS):
        c = _clean(item)
        if c and len(c) <= OPTIONAL_MAX_CHARS and not _DOSE_RE.search(c):
            return c
    return ""


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
    return "" if section == "GIVE" else section.capitalize()


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
        # One card item can list several ("Hypersensitivity; Cardiac
        # dilatation"): the boilerplate goes, the rest stays.
        for part in what.split(";"):
            part = part.strip().rstrip(". ")
            if not part or _BOILERPLATE_CONTRA_RE.search(part):
                continue
            if part not in by_drug[drug]:
                by_drug[drug].append(part)
    return [f"Contraindicated — {d}: {'; '.join(by_drug[d])}." if d
            else f"Contraindicated — {'; '.join(by_drug[d])}."
            for d in order if by_drug[d]]


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


def build_brief(response_text: str, medication_terms=(), weight_kg=None) -> dict:
    """{"brief": str, "critical_sections": [str]} for one served response.

    `weight_kg` is the patient's CONFIRMED weight, the one the dose calculators
    use; it is only ever used to show the per-kg basis of a printed dose.
    """
    out = _build(response_text, medication_terms, weight_kg)
    out["brief"] = "\n".join(_sentence_case(l) for l in out["brief"].split("\n"))
    return out


def _build(response_text, medication_terms, weight_kg):
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
    doses = [dose_line(item, weight_kg) for _, item in dose_items]
    if len(dose_items) > 1:
        labels = [dose_label(name, item) for name, item in dose_items]
        doses = [f"[{label}] {line}" if label else line
                 for label, line in zip(labels, doses)]

    critical, critical_sections = [], []
    contra = _contraindication_lines(_section(sections, CONTRAINDICATION_SECTIONS))
    if contra:
        critical += contra
    for name, lines in sections:
        if name in CONTRAINDICATION_SECTIONS and contra and name not in critical_sections:
            critical_sections.append(name)
        if name in DONT_SECTIONS:
            hits = [i for i in _top_items(lines)
                    if not _BOILERPLATE_CONTRA_RE.search(i)
                    and (_NEVER_RE.search(i)
                    or any(re.search(r"(?<!\w)" + re.escape(d) + r"(?!\w)", i.lower())
                           for d in dosed))]
            critical += hits
            if _top_items(lines) and name not in critical_sections:
                critical_sections.append(name)

    # ── Three slots when the response doses ─────────────────────────────────
    if doses:
        slot_b = _next_action(sections, dosed)
        lines = _fit(lead, [" · ".join(doses)], [slot_b] if slot_b else [],
                     [" · ".join(critical)] if critical else [])
        return {"brief": "\n".join(lines), "critical_sections": critical_sections}

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
