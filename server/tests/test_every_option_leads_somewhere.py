"""Every option of every clarifying question leads somewhere (owner, 2026-11-19).

Owner: "General test to add: for every question in both sets, every option leads to a
signed dose, a further question, or is labelled as giving no dose."

Each signed drug of the set is asked for ("<drug> dose") with six patients (adult or
child, with or without a weight, none at all), and the drugless pain question with
four. Every question that comes back (indication, vial, route, weight, the estimated
weight, adult, severity, calcium salt) is answered with each of its options, and so on
down every further question. An option passes when its answer is:
  - a signed dose: a deterministic card naming the drug, or the generator called with
    that drug in ALLOWED_DOSES / ALLOWED_RATES;
  - a further question;
  - or the option's own line says it gives no dose ("mild ... → no dose offered").
Anything else (a hold, or the generator with nothing offered) is a dead option.

The model is stubbed out; the suite's pinned test kit decides the vial questions.
"""
import io
import contextlib
import json
import os
import re
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

dc = oc.drug_contracts

PATIENTS = [("80 kg adult", "80 kg"), ("6 year old 20 kg", "20 kg"), ("adult", "80 kg"),
            ("6 year old", "20 kg"), ("", "80 kg"), ("2 year old", "12 kg")]
PAIN_PATIENTS = [("80 kg adult", "80 kg"), ("6 year old 20 kg", "20 kg"), ("adult", "80 kg"),
                 ("6 year old", "20 kg")]


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


ASK_KINDS = [("indication", oc.INDICATION_QUESTION_PREFIX), ("route", "IV or IM?"),
             ("weight", "Need weight in kg"), ("weight-confirm", oc.WEIGHT_CONFIRM_ASK),
             ("adult", oc.ADULT_CONFIRM_ASK), ("severity", oc.PAIN_SEVERITY_QUESTION_PREFIX),
             ("calcium", oc.CALCIUM_SALT_ASK)]


def kind_of(resp: str):
    s = (resp or "").strip()
    if re.match(r"Which .+? do you have", s):
        return "vial"
    for k, p in ASK_KINDS:
        if s.startswith(p):
            return k
    return None


def options(kind, resp, weight):
    if kind == "indication":
        return re.split(r", | or ", resp.split(" — ", 1)[1].rstrip("?"))
    if kind == "vial":
        return re.findall(r"\(([\d.]+ mg/mL)\)", resp)
    return {"route": ["IV", "IM"], "adult": ["adult"], "severity": ["mild", "moderate", "severe"],
            "calcium": ["chloride", "gluconate"]}.get(kind, [weight])


def labelled_no_dose(kind, resp, option):
    if kind != "severity":
        return False
    line = next((l for l in resp.splitlines() if l.startswith(f"- {option} ")), "")
    return "→ no dose offered" in line and "weight" not in line


class _Driver:
    def __init__(self):
        self.prompt = None
        self.dead = []
        self.seen = set()

    def chat(self, system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return '{"result":"SAFE","issues":[],"rationale":"stub"}'
        self.prompt = f"{system}\n{json.dumps(messages, ensure_ascii=False)}"
        return "Reassess."

    def run(self, q, hist):
        self.prompt = None
        with contextlib.redirect_stdout(io.StringIO()):
            r = oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=hist)
        return r, self.prompt

    @staticmethod
    def offered(prompt, drug):
        m = re.search(r"ALLOWED_DOSES — use EXACTLY.*?(?:\\n\\n|ALLOWED_RATES|$)", prompt, re.S)
        rates = re.search(r"ALLOWED_RATES — .*", prompt, re.S)
        blob = ((m.group(0) if m else "") + (rates.group(0) if rates else "")).lower()
        return bool(blob.strip()) and (drug.lower() in blob if drug else "- " in blob)

    def leads_somewhere(self, r, prompt, drug):
        if kind_of(r["response"]):
            return True
        if prompt is not None:
            return self.offered(prompt, drug)
        if r.get("validator_result") == "UNSAFE":
            return False
        return (drug or "").split()[0].lower() in r["response"].lower() if drug else "**GIVE**" in r["response"]

    def walk(self, hist, drug, weight, depth=1):
        resp = hist[-1]["response"]
        kind = kind_of(resp)
        if not kind or depth > 5:
            return
        for option in options(kind, resp, weight):
            key = (drug, kind, option, tuple(h["query"] for h in hist))
            if key in self.seen:
                continue
            self.seen.add(key)
            r, prompt = self.run(option, hist)
            if not self.leads_somewhere(r, prompt, drug) and not labelled_no_dose(kind, resp, option):
                self.dead.append({"drug": drug or "(pain)", "asked": [h["query"] for h in hist],
                                  "question": resp[:200], "option": option,
                                  "answer": r["response"][:200]})
            elif kind_of(r["response"]):
                self.walk(hist + [{"query": option, "response": r["response"]}], drug, weight, depth + 1)


@pytest.mark.parametrize("served_set", ["PFC", "EMS"])
def test_every_option_leads_to_a_dose_a_question_or_says_no_dose(served_set, monkeypatch):
    monkeypatch.setattr(dc, "SERVED_SET", served_set)
    d = _Driver()
    monkeypatch.setattr(providers, "chat", d.chat)
    asked = 0
    for drug in sorted(dc.servable_entries()):
        for patient, weight in PATIENTS:
            q = f"{drug} dose{', ' + patient if patient else ''}"
            r, _ = d.run(q, [])
            if kind_of(r["response"]):
                asked += 1
                d.walk([{"query": q, "response": r["response"]}], drug, weight)
    for patient, weight in PAIN_PATIENTS:
        q = f"{patient}, broken femur, pain, what can I give"
        r, _ = d.run(q, [])
        if kind_of(r["response"]):
            asked += 1
            d.walk([{"query": q, "response": r["response"]}], "", weight)
    assert asked, "no question was asked at all"
    assert d.dead == [], json.dumps(d.dead, indent=1)
