"""A26 (owner, 2026-10-11): the canonical GIVE line's dose figure is checked
the same as any other stated dose; fentanyl "(0.5mg)" holds.

The canonical GIVE line, "Draw X mL of Y mg/mL drug IV (Z mg)", was checked
against ALLOWED_DOSES with a tolerance of max(0.5 mg, 5%). For any signed dose
under 10 mg the 0.5 mg floor is wider than the dose: fentanyl "(0.5mg)",
tenfold the signed 0.05 mg, passed. The free-text check skips the canonical
line, so nothing else read it, and the volume audit in _finalise then found no
signed fentanyl concentration and rewrote the line to "fentanyl 0.5 mg. NO
VOLUME", served with the review banner (found in A25, main fc256eb).

The owner's rule: the parenthetical figure is held to the free-text check's
tolerance, within 5% of a signed value, with no absolute floor.
"""
import openai_client as oc

B1_QUERY = "80 kg adult, severe pain from a femur fracture, fentanyl IV"
EPI_QUERY = "70kg, anaphylaxis, epinephrine IM"
RSI_QUERY = "80kg adult, RSI, ketamine and rocuronium"


def _check(query, weight, give):
    ctx = oc.PatientContext(confirmed_weight_kg=weight)
    allowed = oc.build_allowed_doses(query, ctx)
    det = oc.run_deterministic_checks(query, f"**GIVE**\n- {give}", ctx, allowed, current_query=query)
    return [i for i in det.issues if i.startswith("GIVE line states")]


# ── the gap ──────────────────────────────────────────────────────────────────

def test_fentanyl_tenfold_in_the_give_line_holds():
    issues = _check(B1_QUERY, 80.0, "Draw 10 mL of 0.05mg/mL fentanyl IV (0.5mg).")
    assert issues and "fentanyl 0.5mg" in issues[0], issues


def test_epinephrine_im_above_the_signed_dose_holds():
    assert _check(EPI_QUERY, 70.0, "Draw 0.8 mL of 1mg/mL epinephrine IM (0.8mg).")


def test_epinephrine_half_a_milligram_matches_no_signed_dose():
    # Signed: IM 0.3 mg, arrest 1 mg, push dose 10 mcg. 0.5 mg is none of them.
    assert _check(EPI_QUERY, 70.0, "Draw 5 mL of 0.1mg/mL epinephrine IV (0.5mg).")


def test_the_tenfold_line_is_held_end_to_end(monkeypatch):
    gen = ("**BRIEF**\n- Fentanyl for femur fracture pain.\n\n**GIVE**\n"
           "- Draw 10 mL of 0.05mg/mL fentanyl IV (0.5mg).\n\n**TLDR**\n- Fentanyl IV.\n\n"
           "**SOURCE**: JTS CPG ID61")

    def fake_chat(system, messages, model=None, **k):
        if system == oc.VALIDATOR_PROMPT:
            return '{"result": "SAFE", "issues": [], "rationale": "ok"}'
        return gen

    class Hit:
        def query(self, *a, **k):
            return {"documents": [["fentanyl 50 mcg IV"]],
                    "metadatas": [[{"source": "JTS", "page": 8, "title": "PFC Analgesia"}]],
                    "distances": [[0.3]]}

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    r = oc._query_with_rag_internal(B1_QUERY, Hit())
    assert r["validator_result"] == "UNSAFE", r["validator_result"]
    assert "fentanyl 0.5 mg" not in r["response"], r["response"]


# ── guards ───────────────────────────────────────────────────────────────────

def test_the_signed_value_passes():
    assert _check(B1_QUERY, 80.0, "Draw 1 mL of 0.05mg/mL fentanyl IV (0.05mg).") == []
    assert _check(EPI_QUERY, 70.0, "Draw 0.3 mL of 1mg/mL epinephrine IM (0.3mg).") == []
    assert _check(RSI_QUERY, 80.0, "Draw 1.6 mL of 50mg/mL ketamine IV (80mg).") == []


def test_within_five_percent_passes_and_beyond_holds():
    assert _check(RSI_QUERY, 80.0, "Draw 1.68 mL of 50mg/mL ketamine IV (84mg).") == []
    assert _check(RSI_QUERY, 80.0, "Draw 1.72 mL of 50mg/mL ketamine IV (86mg).")
