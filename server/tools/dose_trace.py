"""Dose trace (scope rulings PR 0, owner 2026-11-20). Report only; nothing in
the serving path imports this.

Every dose number a served answer states must come from code's own rendering
of the signed entries offered for that question: the GIVE line of each dose
candidate (render_give_line) and the range line of each rate
(render_range_line). A number with a dose unit that is not in those renderings
is "untraced". Vital-sign and lab units (mmHg, mg/dL, kg, cmH2O, %) are not
dose units and are never read.

Under ruling 1 a code-written medication answer is those renderings, so every
replayed row must trace. For today's model-written answers it is a baseline.
"""
import re
from typing import Iterable, List, Tuple

# Longest unit first. A unit must not run on into a lab unit: "mg/dL" is not
# "mg", "mL/hr" is a rate and is read whole.
_UNITS = (r"mcg/kg/min|mcg/kg/hr|mg/kg/hr|mcg/kg|mg/kg|g/kg|units/kg|mL/kg|"
          r"mL/hr|mg/hr|mcg/hr|mcg/min|mg/min|units/hr|mg/mL|mcg/mL|units/mL|"
          r"micrograms?|mcg|µg|mg|mEq|mmol|units?|mL|g")
_DOSE_RE = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(" + _UNITS + r")(?![A-Za-z/])", re.IGNORECASE)


def _unit(u: str) -> str:
    u = u.lower()
    if u in ("micrograms", "microgram", "µg"):
        return "mcg"
    if u == "unit":
        return "units"
    return u


def _num(n: str) -> str:
    return f"{float(n):g}"


def dose_numbers(text: str) -> List[Tuple[str, str]]:
    """(number, unit) for every number with a dose unit, in order."""
    return [(_num(m.group(1)), _unit(m.group(2))) for m in _DOSE_RE.finditer(text or "")]


def offered_text(doses: Iterable, rates: Iterable) -> str:
    """Code's own rendering of what was offered: the trace's source of truth."""
    import openai_client as oc
    return "\n".join([oc.render_give_line(d) for d in doses or []]
                     + [oc.render_range_line(r) for r in rates or []])


def untraced(text: str, doses: Iterable, rates: Iterable) -> List[Tuple[str, str]]:
    """Dose numbers in `text` that code's rendering of the offered entries
    does not state (same number, same unit)."""
    offered = set(dose_numbers(offered_text(doses, rates)))
    return [x for x in dose_numbers(text) if x not in offered]
