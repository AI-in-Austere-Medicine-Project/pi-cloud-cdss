"""A21 (owner, 2026-10-04): a dose in a clause with a limit word is checked.

The free-text dose check skipped a whole clause containing "not", "max",
"avoid" or another limit word, so a dose instruction in that clause was never
read. Found in A20 with a TXA question: the teacher's "If 1 g already given
and <3 hours from injury: give 1 g more, not 2 g." held only on its history
clause (its instruction clause was skipped), and "If not already given, give
1 g." returned no issue.

The owner's rule: such a clause is not skipped; its dose is checked against
the signed value like any other. Negation exempts only the dose it directly
negates: "not 2 g" is not a recommendation; "give 1 g more" in the same
sentence is.
"""
import pytest

import openai_client as oc

TXA_QUERY = "hx: DVT + thrombosis. TXA still ok in his case?"  # signed TXA: 2 g
TEACHER_LINE = "If 1 g already given and <3 hours from injury: give 1 g more, not 2 g."


def _issues(text, query=TXA_QUERY):
    ctx = oc.rebuild_patient_context_from_history(query)
    return oc.free_text_dose_issues(text, oc.build_allowed_doses(query, ctx), ctx, query)


def _txa(issues, shown):
    return [i for i in issues if f"tranexamic acid {shown}," in i or f"tranexamic acid {shown} " in i]


def test_the_teacher_lines_instruction_clause_is_checked():
    # The clause the limit skip dropped, on its own line: 1 g is not signed.
    assert _txa(_issues("give 1 g more, not 2 g."), "1 g")


def test_the_teacher_line_still_holds_on_1_g():
    # Verbatim; held on main by its history clause, and must stay held.
    assert _txa(_issues(TEACHER_LINE), "1 g")


def test_if_not_already_given_give_1_g_is_checked():
    assert _txa(_issues("If not already given, give 1 g."), "1 g")


def test_a_negated_dose_is_not_a_recommendation():
    # 3 g is not signed, but "not 3 g" recommends nothing; the 1 g is checked.
    issues = _issues("Give 1 g more, not 3 g.")
    assert _txa(issues, "1 g"), issues
    assert not _txa(issues, "3 g"), issues


@pytest.mark.parametrize("text", [
    "Never give 3 g.",
    "Do not give 3 g.",
    "Don't push 3 g.",
    "Avoid 3 g in this patient.",
])
def test_a_directly_negated_dose_is_exempt(text):
    assert _issues(text) == [], text


@pytest.mark.parametrize("text, shown", [
    ("Max 4 g.", "4 g"),
    ("Up to 4 g IV.", "4 g"),
    ("Give 4 g; do not repeat.", "4 g"),
    ("Not in children: give 4 g over 10 minutes.", "4 g"),
])
def test_a_dose_beside_a_limit_word_is_checked(text, shown):
    assert _txa(_issues(text), shown), _issues(text)


def test_the_signed_dose_beside_a_negated_one_passes():
    assert _issues("Give 2 g, not 1 g.") == []
