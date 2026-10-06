"""A23b (owner, 2026-10-06; found in the D2b bench): A23 missed two phrasings.

To G-MTN-04, "new casualty, adult male, blast injury, he's bleeding from the groin", local qwen2.5:3b on D2b served, in all three passes, an
answer with no haemorrhage-control step: "Confirm groin wound for bleeding
control." (with a GIVE line naming no drug), or "Assess for signs of shock /
Confirm using laboratory and/or imaging studies". A23 did not fire:
  - "bleeding from the groin" was not one of its active-bleeding phrases;
  - "for bleeding control" passed as if it were an action.

A23b: "bleeding from [an external trauma site]" is active bleeding (groin,
thigh, leg, arm, neck, axilla, buttock, stump, wound, limb …; not the nose,
gums, rectum or other medical bleeds), and "bleeding control" counts as an
action only with an action verb ("achieve bleeding control"), not "for
bleeding control".
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

G_MTN_04 = "new casualty, adult male, blast injury, he's bleeding from the groin"

# The three served local answers from the D2b bench (after tree), verbatim.
SERVED = {
    "p1": "**BRIEF**  \n- NO VOLUME  \n- Confirm concentration to compute volume. Indication: hemorrhage control\n\n**DO THIS**  \n1. Confirm groin wound for bleeding control.\n\n**GIVE**  \n- NO VOLUME \u2014 confirm concentration to compute volume. Indication: hemorrhage control\n\n**WATCH**  \n- Monitor blood pressure and pulse.\n\n**DON'T**  \n- Don't delay DCR if clinically suspected hemorrhagic shock.\n\n**EVAC**  \n- Threshold trigger: Uncontrolled bleeding.\n\n**TLDR**  \n- Confirm groin wound for immediate hemorrhage control.",
    "p2": "**BRIEF**  \n- NO VOLUME  \n- Assess for signs of shock  \n- Confirm using laboratory and/or imaging studies  \n\n**DO THIS**  \n1. Assess for signs of shock  \n2. Confirm using laboratory and/or imaging studies  \n\n**WATCH**  \n- Monitor blood pressure  \n\n**DON'T**  \n- Don't delay initiating DCR if hemorrhagic shock is clinically suspected  \n\n**EVAC**  \n- Threshold trigger: SBP <100mmHg  \n\n**TLDR**  \n- Assess for shock and confirm using labs/imaging.",
    "p3": "**BRIEF**  \n- NO VOLUME  \n- Confirm concentration to compute volume. Indication: hemorrhage control\n\n**DO THIS**  \n1. Confirm groin wound for bleeding control.\n\n**GIVE**  \n- NO VOLUME \u2014 confirm concentration to compute volume. Indication: hemorrhage control\n\n**WATCH**  \n- BP, HR, RR, SpO2\n\n**DON'T**  \n- No contraindication listed\n\n**EVAC**  \n- No evacuation threshold trigger\n\n**TLDR**  \n- Confirm groin wound for immediate hemorrhage control.",
}


def _issues(query, answer):
    ctx = oc.rebuild_patient_context_from_history(query)
    return oc.run_deterministic_checks(query, answer, ctx, oc.build_allowed_doses(query, ctx),
                                       current_query=query).issues


def _held(query, answer):
    return [i for i in _issues(query, answer) if "haemorrhage control" in i]


@pytest.mark.parametrize("name", sorted(SERVED))
def test_the_served_groin_answers_hold(name):
    assert _held(G_MTN_04, SERVED[name]), name


@pytest.mark.parametrize("query", [
    "bleeding from his thigh after a gunshot",
    "she is bleeding from the neck",
    "bleeding from the left axilla, can't get it to stop",
    "he's bleeding from his stump",
])
def test_bleeding_from_an_external_site_is_active_bleeding(query):
    assert _held(query, SERVED["p2"]), query


@pytest.mark.parametrize("query", [
    "bleeding from the nose for an hour",
    "bleeding from his gums after a tooth extraction",
    "bleeding from the rectum, dark stools",
])
def test_medical_bleeds_are_not_this_check(query):
    assert not _held(query, SERVED["p2"]), query


@pytest.mark.parametrize("answer", [
    "1. Pack the groin wound with hemostatic gauze and hold direct pressure for 3 minutes.",
    "1. Apply a junctional tourniquet.",
    "1. Achieve bleeding control at the groin before anything else.",
])
def test_a_real_control_action_passes(answer):
    assert not _held(G_MTN_04, answer), answer


def test_for_bleeding_control_alone_is_not_an_action():
    assert _held(G_MTN_04, "1. Confirm groin wound for bleeding control.")
