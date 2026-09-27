"""
A6: the signed table of contraindicated procedures (procedure_contracts.json).

A row names advice ("a nasal airway"), the condition that makes it dangerous
("mid-face trauma", read by a named detector in openai_client) and its
sources. It holds an answer only when it is signed, in the same sense as a
dose contract: signoff true, a named reviewer, a date, and at least one
source. An unsigned row is inert, and the lint below lists it at load.

Signing is the owner's act (docs/authoring/SIGNING.md). Design and rulings:
docs/A6_CONTRAINDICATED_PROCEDURES_DESIGN.md.
"""
import json
import pathlib

TABLE = pathlib.Path(__file__).parent / "procedure_contracts.json"


def _load() -> list:
    try:
        return json.loads(TABLE.read_text()).get("rows") or []
    except (OSError, ValueError) as e:
        # Same degradation rule as the dose contracts: a missing table holds
        # nothing, it does not stop the server.
        print(f"⚠️  {TABLE.name} unreadable ({e}) — no procedure contraindications.")
        return []


ROWS = _load()


def row_is_active(row: dict) -> bool:
    """Signed, reviewed, dated and sourced. Anything less is inert."""
    return (row.get("signoff") is True and bool(row.get("reviewed_by"))
            and bool(row.get("review_date")) and bool(row.get("sources"))
            and bool(row.get("advice_terms")) and bool(row.get("detector")))


def active_rows() -> list:
    return [r for r in ROWS if row_is_active(r)]


def inert_rows() -> list:
    """The ids of every row that holds nothing, for the load-time lint."""
    return [r.get("id") for r in ROWS if not row_is_active(r)]


_INERT = inert_rows()
if _INERT:
    print(f"⚠️  procedure_contracts lint: {len(_INERT)} of {len(ROWS)} rows are "
          f"unsigned and hold nothing ({', '.join(_INERT)}).")
