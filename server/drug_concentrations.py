"""
EdgeCDSS — concentration master list. The inventory of record.

THE RULE THIS MODULE EXISTS TO ENFORCE
──────────────────────────────────────
The system NEVER emits a volume in mL from an unconfirmed concentration.

A milligram dose is a clinical claim, sourced from a guideline and signed off in
drug_contracts.json. A millilitre volume is a claim about THE VIAL IN THE BAG,
and no guideline knows what is in the bag. Until this session's kit says
otherwise, the honest answer is the mg and a request to confirm.

What went wrong before this module: the dose calculators divided by literal
concentrations — ketamine /100.0, succinylcholine /20.0, rocuronium /10.0,
lorazepam /2.0 — and the served text said "Draw 7.1 mL of 20mg/mL
succinylcholine". A deployment stocking the WHO/austere strength of 50 mg/mL
would have drawn 7.1 mL of it: 355 mg instead of 142 mg, two and a half times
the intended dose of a depolarising paralytic, during RSI. Those literals are
gone. Every volume in the system now derives from this file and nowhere else.

CONCENTRATION IS A CONFIRMED INPUT, LIKE WEIGHT
───────────────────────────────────────────────
Weight has a rule: no dose without a confirmed weight. Concentration now has
the matching one: no VOLUME without a confirmed concentration. Both degrade the
same way — the answer gets less specific, never less correct. mg-only is a
useful answer. A wrong mL is not.

THE VIAL IS DECLARED AS THE VIAL IS LABELLED
────────────────────────────────────────────
A medic reads "500 mg / 10 mL" off the label, not "50 mg/mL". So a presentation
is declared as mass_mg and volume_ml, and concentration_mg_ml is DERIVED and
checked against them. Declaring 500 mg in 10 mL and writing 5 mg/mL is caught
at load, because the two disagree — a guardrail that only exists because the
declaration matches the label.

ASKING IS DISAMBIGUATION, NOT AN INPUT CHANNEL
──────────────────────────────────────────────
Where a drug has more than one signed presentation — or is marked
confirm_required, as ketamine is, because 500 mg/10 mL and 200 mg/20 mL are
both common and differ five-fold — the system ASKS which vial, the same way it
asks IV or IM.

It asks BETWEEN DECLARED, SIGNED PRESENTATIONS. It never accepts a
free-typed concentration. A number typed into a chat box under time pressure
has none of this file's guardrails, no signoff and no audit trail, and
accepting one would reintroduce exactly the hazard this module removes by a
route with less protection than the one it replaced.

SIGNOFF IS ASYMMETRIC, AND THAT IS THE POINT
────────────────────────────────────────────
Declaring or changing a concentration requires signoff. REVOKING one does not.

Fail-closed makes signoff cheap: an unsigned entry degrades to mg-only, which
is still correct. So signoff gates an enhancement, never the core answer. And
when the kit changes mid-deployment and no signer is reachable, anyone can pull
the concentration and the system degrades safely — instead of confidently
serving a volume for a vial nobody stocks any more, which is the original bug
wearing a different hat.
"""

import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
from typing import Optional

_DIR = pathlib.Path(__file__).parent

PENDING = "PENDING_CLINICAL_SIGNOFF"

SIGNOFF_AUTHORS = tuple(
    a.strip() for a in os.getenv("CDSS_CARD_AUTHORS",
                                 "clinician,AI-AIM").split(",")
    if a.strip())

CONFIG = _DIR / "drug_concentrations.json"
CHANGE_LOG = pathlib.Path(os.getenv("CDSS_CONCENTRATION_LOG",
                                    str(_DIR / "drug_concentrations.log.jsonl")))

# Tier 1 of the sane-range check. Structural only — nothing here is a clinical
# judgement about any particular drug, because this module is not allowed to
# author clinical content any more than the contract engine is. A concentration
# outside this is a typo or a unit error, not a vial.
ABSOLUTE_MIN_MG_ML = 0.001
ABSOLUTE_MAX_MG_ML = 1000.0

# Tier 2. How far a declared strength may sit from every strength the approved
# sources cite for that drug before it is refused outright rather than merely
# flagged. Ten-fold is the decimal slip — 500 for 50, 5 for 50 — which is the
# error this catches and the one that hurts most.
ORDER_OF_MAGNITUDE = 10.0


@dataclasses.dataclass
class ConcentrationRejection:
    """A declared concentration that cannot be real.

    Surfaced, never silently dropped — same discipline as vitals.VitalRejection.
    A silently ignored declaration leaves the owner believing the kit is
    described when it is not, and the system emitting no volumes for a reason
    nobody can see.
    """
    generic_name: str
    raw: str
    reason: str


# ─────────────────────────────────────────────────────────────────────────────
# LOAD + VALIDATE
# ─────────────────────────────────────────────────────────────────────────────

def _sourced_strengths(generic_name: str) -> list:
    """Concentrations the approved sources cite for this drug, via the contracts.

    Reused rather than restated: drug_contracts.json already carries WHO and
    NASEMSO strengths with citations, and a second hand-maintained table of the
    same numbers would drift from it.
    """
    try:
        import drug_contracts
    except Exception:
        return []
    drug = (drug_contracts.DRUGS or {}).get(generic_name)
    if not drug:
        return []
    out = []
    for f in drug.get("forms", []):
        if not isinstance(f, dict):
            continue
        # A source that lists several strengths for one form (WHO gives
        # ketamine at 10 AND 50 mg/mL) carries them as options. Both are
        # equally "what the source says", so both corroborate.
        values = list(f.get("concentration_mg_ml_options") or [])
        if isinstance(f.get("concentration_mg_ml"), (int, float)):
            values.append(f["concentration_mg_ml"])
        for c in values:
            if not (isinstance(c, (int, float)) and c > 0):
                continue
            # tier 0 forms are the pre-contract hardcodes being migrated away
            # from — they are exactly what this module exists to stop trusting,
            # so they do not get to corroborate anything.
            tiers = {s.get("tier") for s in (f.get("sources") or [])
                     if isinstance(s, dict)}
            if tiers & {1, 2}:
                out.append(float(c))
    return sorted(set(out))


def _validate(entry: dict, pres: dict) -> Optional[str]:
    """Reason this presentation cannot be stored, or None if it can."""
    name = entry.get("generic_name")
    mass, vol = pres.get("mass_mg"), pres.get("volume_ml")
    conc = pres.get("concentration_mg_ml")

    for field, value in (("mass_mg", mass), ("volume_ml", vol),
                         ("concentration_mg_ml", conc)):
        if not isinstance(value, (int, float)):
            return f"{field} is not a number"
        if value != value or value in (float("inf"), float("-inf")):
            return f"{field} is not finite"
        if value <= 0:
            return f"{field} must be greater than zero"

    # The label check. mass/volume is how the vial reads; concentration is
    # derived. If they disagree, one of them was transcribed wrong and there is
    # no way to know which — so neither is usable.
    derived = mass / vol
    if abs(derived - conc) > max(0.001, conc * 0.001):
        return (f"declared {mass:g} mg in {vol:g} mL is {derived:g} mg/mL, but "
                f"concentration_mg_ml says {conc:g} — these must agree")

    if not (ABSOLUTE_MIN_MG_ML <= conc <= ABSOLUTE_MAX_MG_ML):
        return (f"{conc:g} mg/mL is outside the plausible range "
                f"{ABSOLUTE_MIN_MG_ML:g}-{ABSOLUTE_MAX_MG_ML:g} mg/mL")

    sourced = _sourced_strengths(name)
    if sourced:
        if all(conc >= s * ORDER_OF_MAGNITUDE or conc <= s / ORDER_OF_MAGNITUDE
               for s in sourced):
            return (f"{conc:g} mg/mL is more than {ORDER_OF_MAGNITUDE:g}x away "
                    f"from every strength the approved sources cite for "
                    f"{name} ({', '.join(f'{s:g}' for s in sourced)} mg/mL) — "
                    f"this is the shape of a decimal error")

    if pres.get("signoff") is True and pres.get("corroboration") == "OFF_SOURCE" \
            and not str(pres.get("justification") or "").strip():
        return ("signed as OFF_SOURCE with no justification — a strength no "
                "approved source cites must say why it is right")

    return None


def _corroboration(generic_name: str, conc: float) -> str:
    sourced = _sourced_strengths(generic_name)
    if not sourced:
        return "NO_SOURCED_STRENGTH"
    return "SOURCE_MATCHED" if any(abs(conc - s) < 1e-9 for s in sourced) \
        else "OFF_SOURCE"


def _load() -> tuple:
    try:
        raw = json.loads(CONFIG.read_text())
    except FileNotFoundError:
        print(f"⚠️  {CONFIG.name} not found — no concentrations are declared, "
              f"so no volumes will be served.")
        return {}, [], None
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  {CONFIG.name} is unreadable ({e}) — no concentrations are "
              f"declared, so no volumes will be served.")
        return {}, [], None

    entries, rejections = {}, []
    for entry in raw.get("entries", []):
        if not isinstance(entry, dict) or not entry.get("generic_name"):
            continue
        name = entry["generic_name"]
        kept = []
        for pres in entry.get("presentations", []):
            if not isinstance(pres, dict):
                continue
            reason = _validate(entry, pres)
            label = pres.get("label_text") or str(pres.get("concentration_mg_ml"))
            if reason:
                rejections.append(ConcentrationRejection(name, str(label), reason))
                continue
            pres = dict(pres)
            pres.setdefault("corroboration",
                            _corroboration(name, pres["concentration_mg_ml"]))
            kept.append(pres)
        entries[name] = {**entry, "presentations": kept}
    return entries, rejections, raw


ENTRIES, REJECTIONS, _RAW = _load()

for _r in REJECTIONS:
    print(f"⚠️  concentration REJECTED — {_r.generic_name} {_r.raw!r}: {_r.reason}")


def kit_id() -> str:
    return (_RAW or {}).get("kit_id", "unknown")


# ─────────────────────────────────────────────────────────────────────────────
# THE FENCE
# ─────────────────────────────────────────────────────────────────────────────

def presentation_is_signed(pres: dict) -> bool:
    if pres.get("signoff") is not True:
        return False
    if str(pres.get("reviewed_by") or "").strip() not in SIGNOFF_AUTHORS:
        return False
    rd = str(pres.get("review_date") or "").strip()
    return bool(rd) and rd != PENDING


def signed_presentations(generic_name: str) -> list:
    entry = ENTRIES.get(generic_name)
    if not entry:
        return []
    return [p for p in entry.get("presentations", []) if presentation_is_signed(p)]


# resolve() outcomes
RESOLVED = "RESOLVED"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
NONE_DECLARED = "NONE_DECLARED"


def resolve(generic_name: str, confirmed: Optional[dict] = None) -> tuple:
    """(status, concentration_mg_ml, presentation).

    confirmed is this patient's already-answered concentrations, {drug: mg/mL}.

    NONE_DECLARED and NEEDS_CONFIRMATION both mean the same thing to the
    caller — do not emit a volume — but they are different questions for the
    medic, so they stay distinguishable.
    """
    signed = signed_presentations(generic_name)
    if not signed:
        return NONE_DECLARED, None, None

    if confirmed and generic_name in confirmed:
        want = confirmed[generic_name]
        for p in signed:
            if abs(p["concentration_mg_ml"] - want) < 1e-9:
                return RESOLVED, p["concentration_mg_ml"], p
        # A confirmation that no longer matches anything signed is stale — the
        # list changed under it. Ask again rather than serve the old answer.
        return NEEDS_CONFIRMATION, None, None

    entry = ENTRIES.get(generic_name) or {}
    if len(signed) == 1 and not entry.get("confirm_required"):
        return RESOLVED, signed[0]["concentration_mg_ml"], signed[0]
    return NEEDS_CONFIRMATION, None, None


def confirmation_question(generic_name: str) -> Optional[str]:
    """The ASK, phrased in what is printed on the vial."""
    signed = signed_presentations(generic_name)
    if not signed:
        return None
    opts = " or ".join(
        f"{p.get('label_text') or ''} ({p['concentration_mg_ml']:g} mg/mL)".strip()
        for p in signed)
    return f"Which {generic_name} do you have — {opts}?"


def match_confirmation(generic_name: str, text: str) -> Optional[float]:
    """A declared presentation this answer names, or None.

    Matching is against DECLARED presentations only. There is deliberately no
    path here that parses a concentration out of free text and believes it.
    """
    import re
    t = (text or "").lower()
    if not t.strip():
        return None
    best = None
    for p in signed_presentations(generic_name):
        conc = p["concentration_mg_ml"]
        mass, vol = p.get("mass_mg"), p.get("volume_ml")
        pats = [rf"\b{conc:g}\s*mg\s*/?\s*m\s*l\b", rf"\b{conc:g}\s*mg\s*per\s*ml\b"]
        if mass and vol:
            pats.append(rf"\b{mass:g}\s*mg\b.{{0,12}}?\b{vol:g}\s*m\s*l\b")
            # "500 / 10", "500 in 10", "500 per 10" — the separator is
            # required. Without it, "500 mg over 10 minutes" would read as a
            # vial declaration, and a rate is not a concentration.
            pats.append(rf"\b{mass:g}\s*(?:mg)?\s*(?:/|in|per)\s*{vol:g}\s*(?:m\s*l)?\b")
        for pat in pats:
            if re.search(pat, t):
                # longest/most specific wins; a bare mass match is weakest
                best = conc
                break
        if best is not None:
            break
    if best is None:
        # A bare number that equals exactly one signed strength, e.g. "50".
        nums = {float(n) for n in re.findall(r"\b(\d+(?:\.\d+)?)\b", t)}
        hits = [p["concentration_mg_ml"] for p in signed_presentations(generic_name)
                if p["concentration_mg_ml"] in nums]
        mass_hits = [p["concentration_mg_ml"] for p in signed_presentations(generic_name)
                     if p.get("mass_mg") in nums]
        if len(set(hits)) == 1:
            best = hits[0]
        elif len(set(mass_hits)) == 1:
            best = mass_hits[0]
    return best


def draw_precision(true_volume_ml: float) -> int:
    """Decimal places a syringe can actually be read to for this volume.

    Two places by default: 2.842 mL is arithmetic, 2.84 mL is a thing a person
    can draw. Falls back to three only when two would misstate the dose by more
    than 5%, which happens on the small pushes where the volume is a fraction
    of a millilitre and the precision genuinely matters.
    """
    for places in (2, 3, 4):
        rounded = round(true_volume_ml, places)
        if rounded > 0 and abs(rounded - true_volume_ml) <= true_volume_ml * 0.05:
            return places
    return 4


def volume_ml(generic_name: str, dose_mg: float,
              confirmed: Optional[dict] = None) -> tuple:
    """(volume_ml, concentration_mg_ml) or (None, None). The ONLY mL source."""
    status, conc, _ = resolve(generic_name, confirmed)
    if status != RESOLVED or not conc:
        return None, None
    true_vol = dose_mg / conc
    return round(true_vol, draw_precision(true_vol)), conc


def declared_concentration(generic_name: str) -> Optional[float]:
    """The single signed strength, for the gate's cross-check. None if the drug
    has none, or more than one and no confirmation to pick between them."""
    signed = signed_presentations(generic_name)
    if len(signed) == 1:
        return signed[0]["concentration_mg_ml"]
    return None


def all_signed_strengths(generic_name: str) -> list:
    return sorted(p["concentration_mg_ml"] for p in signed_presentations(generic_name))


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE LOG
# ─────────────────────────────────────────────────────────────────────────────

def _snapshot() -> dict:
    """{drug: {label: (conc, signed)}} — what the file currently declares."""
    out = {}
    for name, entry in ENTRIES.items():
        out[name] = {
            (p.get("label_text") or f"{p['concentration_mg_ml']:g}"):
            [p["concentration_mg_ml"], bool(presentation_is_signed(p))]
            for p in entry.get("presentations", [])
        }
    return out


def _config_hash() -> str:
    try:
        return hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    except OSError:
        return ""


def append_log(record: dict) -> None:
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "kit_id": kit_id(), **record}
    try:
        CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHANGE_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as e:
        # A log we cannot write is a fact worth printing, not a reason to fail
        # a clinical request.
        print(f"⚠️  could not write {CHANGE_LOG.name} ({e}): {record}")


def _last_logged_state() -> tuple:
    """(hash, snapshot) from the most recent log record that carried one."""
    try:
        lines = CHANGE_LOG.read_text().strip().split("\n")
    except OSError:
        return None, None
    for line in reversed([l for l in lines if l.strip()]):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "config_hash" in rec:
            return rec.get("config_hash"), rec.get("snapshot")
    return None, None


def detect_external_edit() -> list:
    """Log any change made by editing the file directly. Returns the diffs.

    set_concentration.py logs its own changes. This exists because the most
    likely way to edit a JSON file is to open it in an editor, and a change log
    that the most likely editing method bypasses is not a change log.
    """
    now_hash, now_snap = _config_hash(), _snapshot()
    last_hash, last_snap = _last_logged_state()

    if last_hash is None:
        append_log({"event": "BASELINE", "config_hash": now_hash,
                    "snapshot": now_snap})
        return []
    if last_hash == now_hash:
        return []

    diffs = []
    for drug in sorted(set(now_snap) | set(last_snap or {})):
        old = (last_snap or {}).get(drug, {})
        new = now_snap.get(drug, {})
        for label in sorted(set(old) | set(new)):
            if old.get(label) != new.get(label):
                diffs.append({"drug": drug, "label": label,
                              "old": old.get(label), "new": new.get(label)})
    append_log({"event": "DETECTED_EXTERNAL_EDIT", "config_hash": now_hash,
                "snapshot": now_snap, "changes": diffs})
    for d in diffs:
        print(f"📝 concentration changed outside the tool — {d['drug']} "
              f"{d['label']}: {d['old']} -> {d['new']}")
    return diffs


if os.getenv("CDSS_CONCENTRATION_LOG_ON_IMPORT", "1") == "1":
    try:
        detect_external_edit()
    except Exception as _e:                                  # pragma: no cover
        print(f"⚠️  concentration change-log check failed ({_e})")
