"""
EdgeCDSS — Protocol Index Builder
Version: 1.0.0

Queries existing ChromaDB chunks, extracts structured clinical metadata
per JTS protocol using GPT-4o-mini, validates with Pydantic, and writes:
  - protocol_index.json    (routing map)
  - safety_rules.json      (hard stops)
  - query_aliases.json     (field slang)

Run once on arcaneone:
  cd ~/cdss-cloud/app
  source ~/cdss-cloud/venv/bin/activate
  python3 build_protocol_index.py

Requirements: chromadb, openai, pydantic, python-dotenv already installed in venv.
"""

import os
import json
import time
import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── Pydantic schema ───────────────────────────────────────────────────────────

try:
    from pydantic import BaseModel, field_validator
    PYDANTIC_V2 = True
except ImportError:
    from pydantic import BaseModel, validator
    PYDANTIC_V2 = False

from openai import OpenAI
import chromadb

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class ProtocolMetadata(BaseModel):
    protocol_id: str
    title: str
    clinical_domain: str
    aliases: list = []
    primary_conditions: list = []
    medications: list = []
    blood_products: list = []
    procedures: list = []
    required_context: list = []
    contraindications: list = []
    red_flags: list = []
    evacuation_triggers: list = []
    safety_gates: list = []
    search_terms: list = []
    source_file: str = ""


class SafetyRule(BaseModel):
    drug_or_intervention: str
    indications: list = []
    contraindications: list = []
    dose_limits: list = []
    timing_constraints: list = []


# ── Extraction prompt ─────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are extracting structured clinical routing metadata from a JTS (Joint Trauma System) Clinical Practice Guideline.

Extract ONLY what is explicitly stated in the provided text. Do not invent or infer beyond what is written.

Return ONLY valid JSON matching this exact schema:

{
  "protocol_id": "snake_case_identifier",
  "title": "Full protocol title",
  "clinical_domain": "one of: trauma_resuscitation | airway | analgesia_sedation | infection_sepsis | cardiac | neurologic | environmental | triage | burns | toxicology | other",
  "aliases": ["common abbreviations and field names for this protocol"],
  "primary_conditions": ["conditions this protocol addresses"],
  "medications": ["medications mentioned by name"],
  "blood_products": ["blood products mentioned: whole blood, LTOWB, plasma, RBC, platelets"],
  "procedures": ["procedures described"],
  "required_context": ["clinical facts needed before acting: mechanism, weight, access, time since injury, etc"],
  "contraindications": ["explicit contraindications stated in the protocol"],
  "red_flags": ["clinical signs that escalate urgency"],
  "evacuation_triggers": ["criteria for immediate evacuation"],
  "safety_gates": ["hard safety rules: never give X for Y, always do Z first"],
  "search_terms": ["additional terms that should retrieve this protocol"]
}

Return JSON only. No markdown. No explanation."""


# ── ChromaDB connection ───────────────────────────────────────────────────────

def get_chroma_collection():
    chroma_client = chromadb.PersistentClient(
        path=os.getenv("CHROMADB_PATH", "./cache/chromadb")
    )
    return chroma_client.get_collection("jts_protocols")


def get_unique_sources(collection) -> list:
    """Get all unique source files in the collection."""
    results = collection.get(include=["metadatas"])
    sources = set()
    for meta in results["metadatas"]:
        if meta and meta.get("source"):
            sources.add(meta["source"])
    return sorted(list(sources))


def get_chunks_for_source(collection, source: str, max_chunks: int = 20) -> str:
    """Retrieve chunks for a specific source file."""
    results = collection.get(
        where={"source": source},
        include=["documents", "metadatas"]
    )
    docs = results.get("documents", [])
    # Take first max_chunks to stay within token limits
    combined = "\n\n---\n\n".join(docs[:max_chunks])
    # Truncate to ~8000 chars to fit in context
    if len(combined) > 8000:
        combined = combined[:8000] + "\n...[truncated]"
    return combined


# ── LLM extraction ────────────────────────────────────────────────────────────

def extract_protocol_metadata(source_file: str, text: str) -> Optional[ProtocolMetadata]:
    """Call GPT-4o-mini to extract structured metadata from protocol text."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": f"SOURCE FILE: {source_file}\n\nPROTOCOL TEXT:\n{text}"}
            ],
            temperature=0,
            max_tokens=1200
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        data["source_file"] = source_file

        # Ensure protocol_id is clean snake_case
        if not data.get("protocol_id"):
            data["protocol_id"] = re.sub(r"[^a-z0-9_]", "_",
                                          source_file.lower().replace(".pdf", ""))

        return ProtocolMetadata(**data)

    except json.JSONDecodeError as e:
        print(f"    ⚠️  JSON parse error for {source_file}: {e}")
        return None
    except Exception as e:
        print(f"    ⚠️  Error for {source_file}: {e}")
        return None


# ── Safety rules builder ──────────────────────────────────────────────────────

def build_safety_rules(protocols: list) -> dict:
    """
    Aggregate safety rules from all extracted protocols.
    Also includes hard-coded known rules as baseline.
    """
    rules = {
        "txa_tranexamic_acid": {
            "drug": "TXA / Tranexamic Acid",
            "indications": [
                "Traumatic hemorrhagic shock",
                "Within 3 hours of injury",
                "Active hemorrhage with hemodynamic instability"
            ],
            "contraindications": [
                "Sepsis without confirmed hemorrhage",
                "Hypothermia alone without hemorrhage",
                "Burns alone without hemorrhage",
                "Isolated TBI without hemorrhage",
                "More than 3 hours after injury"
            ],
            "timing_constraints": ["Must be given within 3 hours of injury for benefit"]
        },
        "ketamine": {
            "drug": "Ketamine",
            "indications": [
                "Subdissociative analgesia (IV 0.3mg/kg)",
                "Dissociative analgesia IM (2mg/kg)",
                "RSI induction (IV 1.5mg/kg)",
                "Post-intubation sedation (IV 0.5mg/kg q20-30min)"
            ],
            "contraindications": [],
            "dose_limits": {
                "iv_analgesic": "0.3 mg/kg IV",
                "im_analgesic": "2.0 mg/kg IM",
                "rsi_induction": "1.5 mg/kg IV (max 2.0 mg/kg)",
                "post_intubation": "0.5 mg/kg IV q20-30min"
            },
            "notes": "IV and IM doses differ 7x — do not cross-compare"
        },
        "rocuronium": {
            "drug": "Rocuronium",
            "indications": ["RSI paralytic"],
            "contraindications": [],
            "dose_limits": {"rsi": "1.0 mg/kg IV (max 1.2 mg/kg)"},
            "sequencing": "Give AFTER induction agent only"
        },
        "succinylcholine": {
            "drug": "Succinylcholine",
            "indications": ["RSI paralytic (alternative to rocuronium)"],
            "contraindications": [
                "Hyperkalemia or risk of hyperkalemia",
                "Burns greater than 24 hours old",
                "Crush injury",
                "Denervation injuries",
                "Known personal or family history of malignant hyperthermia"
            ],
            "dose_limits": {"rsi_adult": "1.5 mg/kg IV", "rsi_pediatric": "2.0 mg/kg IV"}
        },
        "wpw_contraindicated_drugs": {
            "condition": "WPW / Wolf-Parkinson-White / Pre-excitation",
            "never_give": ["adenosine", "metoprolol", "atenolol", "diltiazem",
                           "verapamil", "digoxin", "any beta-blocker",
                           "any calcium channel blocker"],
            "reason": "Risk of VF via accessory pathway",
            "treatment": "Synchronized cardioversion if unstable"
        },
        "steroids_in_tbi": {
            "condition": "Traumatic Brain Injury",
            "never_give": ["dexamethasone", "methylprednisolone", "solu-medrol",
                           "decadron", "any corticosteroid"],
            "reason": "Increases mortality per CRASH trial",
            "also_avoid": ["albumin", "routine hyperventilation unless herniation signs"]
        },
        "paralytic_sequencing": {
            "rule": "Never give paralytic before induction agent in patient with pulse",
            "required_sequence": ["induction agent first", "paralytic second",
                                   "post-intubation sedation after tube confirmed"],
            "exception": "Cardiac arrest — paralytic alone may be acceptable per local protocol"
        }
    }

    # Augment with extracted protocol contraindications
    for protocol in protocols:
        for c in protocol.contraindications:
            for med in protocol.medications:
                med_key = med.lower().replace(" ", "_")
                if med_key not in rules:
                    rules[med_key] = {
                        "drug": med,
                        "indications": [],
                        "contraindications": [],
                        "source_protocol": protocol.protocol_id
                    }
                if c not in rules[med_key].get("contraindications", []):
                    if "contraindications" not in rules[med_key]:
                        rules[med_key]["contraindications"] = []
                    rules[med_key]["contraindications"].append(c)

    return rules


# ── Query aliases builder ─────────────────────────────────────────────────────

def build_query_aliases() -> dict:
    """
    Field slang and abbreviation mapping.
    Manually curated — this is the most reliable approach for field language.
    """
    return {
        # Medications
        "ket": "ketamine",
        "vitamin k": "ketamine",
        "k": "ketamine (context-dependent)",
        "roc": "rocuronium",
        "rocky onium": "rocuronium",
        "sux": "succinylcholine",
        "succs": "succinylcholine",
        "vec": "vecuronium",
        "versed": "midazolam",
        "ativan": "lorazepam",
        "keppra": "levetiracetam",
        "dilt": "diltiazem",
        "del tim": "diltiazem",
        "levo": "norepinephrine",
        "levophed": "norepinephrine",
        "vaso": "vasopressin",
        "mag": "magnesium sulfate",
        "bicarb": "sodium bicarbonate",
        "epi": "epinephrine",
        "push dose epi": "epinephrine 10mcg/mL bolus preparation",
        "dirty epi": "epinephrine infusion",
        "epi drip": "epinephrine infusion",
        "norepi drip": "norepinephrine infusion",
        "pressors": "vasopressors (norepinephrine, vasopressin, epinephrine)",

        # Blood products
        "blood": "blood products",
        "whole blood": "LTOWB or whole blood",
        "buddy transfusion": "field whole blood transfusion",
        "donor blood": "field whole blood transfusion",
        "ltowb": "low-titer O whole blood",
        "ffp": "fresh frozen plasma",
        "prbc": "packed red blood cells",
        "plt": "platelets",

        # Procedures
        "cric": "cricothyrotomy",
        "front of neck": "cricothyrotomy",
        "fona": "cricothyrotomy",
        "cico": "cannot intubate cannot oxygenate",
        "venting the chest": "needle decompression",
        "needle chest": "needle decompression",
        "ntd": "needle thoracostomy decompression",
        "finger thoracostomy": "thoracostomy",
        "tq": "tourniquet",
        "tourney": "tourniquet",
        "cat": "combat application tourniquet",
        "softt": "special operations forces tactical tourniquet",
        "march": "massive hemorrhage airway respiration circulation hypothermia",
        "tccc": "tactical combat casualty care",

        # Clinical conditions
        "bleeding out": "hemorrhagic shock",
        "hemorrhaging": "hemorrhagic shock",
        "dcr": "damage control resuscitation",
        "damage control": "damage control resuscitation",
        "hs": "hemorrhagic shock",
        "septic": "sepsis",
        "infection": "sepsis (context-dependent)",
        "pus": "infection / sepsis indicator",
        "excited delirium": "agitation / excited delirium syndrome",
        "exds": "excited delirium syndrome",
        "cold": "hypothermia",
        "frozen": "hypothermia",
        "snake bite": "envenomation",
        "snake bike": "envenomation",
        "hypothermic arrest": "cardiac arrest from hypothermia",

        # Monitoring
        "sats": "oxygen saturation SpO2",
        "sat": "oxygen saturation SpO2",
        "o2 sat": "oxygen saturation SpO2",
        "etco2": "end-tidal CO2",
        "waveform capnography": "end-tidal CO2 monitoring",
        "sbp": "systolic blood pressure",
        "map": "mean arterial pressure",
        "gcs": "Glasgow Coma Scale",
        "pupils": "pupillary response",

        # Airway
        "ett": "endotracheal tube",
        "tube": "endotracheal intubation (context-dependent)",
        "lma": "laryngeal mask airway",
        "igel": "i-gel supraglottic airway",
        "king": "King LT supraglottic airway",
        "bvm": "bag-valve-mask",
        "npa": "nasopharyngeal airway",
        "opa": "oropharyngeal airway",

        # RSI
        "rapid sequence": "rapid sequence intubation",
        "rsi": "rapid sequence intubation",
        "post intubation": "post-intubation sedation",
        "post-intubation": "post-intubation sedation",

        # Scopes
        "medic": "paramedic",
        "doc": "physician",
        "pa": "physician assistant",
        "crna": "certified registered nurse anesthetist",
        "18d": "special forces medical sergeant",
        "68w": "combat medic specialist"
    }


# ── Main extraction loop ──────────────────────────────────────────────────────

def main():
    print("EdgeCDSS Protocol Index Builder v1.0")
    print("=" * 50)

    # Connect to ChromaDB
    print("\nConnecting to ChromaDB...")
    try:
        collection = get_chroma_collection()
        count = collection.count()
        print(f"Connected. {count} chunks in collection.")
    except Exception as e:
        print(f"ERROR: Could not connect to ChromaDB: {e}")
        return

    # Get all unique sources
    sources = get_unique_sources(collection)
    print(f"Found {len(sources)} unique source documents.")

    # Priority protocols to extract first
    priority_keywords = [
        "damage_control", "dcr", "resuscitation",
        "airway", "cico", "cricothyrotomy",
        "analgesia", "sedation", "ketamine", "pain",
        "rsi", "intubat", "rapid_sequence",
        "sepsis", "infection",
        "hemorrhage", "hemorrhagic",
        "tbi", "brain",
        "tourniquet", "tccc",
        "burn",
    ]

    # Sort: priority sources first, then alphabetical
    def priority_score(s):
        s_lower = s.lower()
        return -sum(1 for kw in priority_keywords if kw in s_lower)

    sources_sorted = sorted(sources, key=priority_score)

    print(f"\nExtracting metadata for {len(sources_sorted)} protocols...")
    print("(Priority protocols first)")
    print("-" * 50)

    protocols = []
    failed = []

    for i, source in enumerate(sources_sorted):
        print(f"\n[{i+1}/{len(sources_sorted)}] {source}")

        # Get text chunks
        text = get_chunks_for_source(collection, source, max_chunks=15)
        if not text.strip():
            print("    ⚠️  No text found, skipping")
            failed.append(source)
            continue

        # Extract metadata
        metadata = extract_protocol_metadata(source, text)
        if metadata:
            protocols.append(metadata)
            print(f"    ✅ {metadata.title} [{metadata.clinical_domain}]")
            print(f"       Conditions: {', '.join(metadata.primary_conditions[:3])}")
            print(f"       Medications: {', '.join(metadata.medications[:4])}")
        else:
            failed.append(source)
            print(f"    ❌ Extraction failed")

        # Rate limiting — be gentle with the API
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Extracted: {len(protocols)}/{len(sources_sorted)} protocols")
    if failed:
        print(f"Failed: {len(failed)}")
        for f in failed:
            print(f"  - {f}")

    # Build output files
    print("\nBuilding output files...")

    # protocol_index.json — keyed by protocol_id
    protocol_index = {}
    for p in protocols:
        protocol_index[p.protocol_id] = {
            "title": p.title,
            "source_file": p.source_file,
            "clinical_domain": p.clinical_domain,
            "aliases": p.aliases,
            "primary_conditions": p.primary_conditions,
            "medications": p.medications,
            "blood_products": p.blood_products,
            "procedures": p.procedures,
            "required_context": p.required_context,
            "contraindications": p.contraindications,
            "red_flags": p.red_flags,
            "evacuation_triggers": p.evacuation_triggers,
            "safety_gates": p.safety_gates,
            "search_terms": p.search_terms,
        }

    # safety_rules.json
    safety_rules = build_safety_rules(protocols)

    # query_aliases.json
    query_aliases = build_query_aliases()

    # Write files
    output_dir = Path(os.getenv("CDSS_APP_DIR", Path(__file__).parent))

    with open(output_dir / "protocol_index.json", "w") as f:
        json.dump(protocol_index, f, indent=2)
    print(f"  ✅ protocol_index.json ({len(protocol_index)} protocols)")

    with open(output_dir / "safety_rules.json", "w") as f:
        json.dump(safety_rules, f, indent=2)
    print(f"  ✅ safety_rules.json ({len(safety_rules)} rules)")

    with open(output_dir / "query_aliases.json", "w") as f:
        json.dump(query_aliases, f, indent=2)
    print(f"  ✅ query_aliases.json ({len(query_aliases)} aliases)")

    # Summary stats
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")

    domains = {}
    for p in protocols:
        d = p.clinical_domain
        domains[d] = domains.get(d, 0) + 1
    for domain, count in sorted(domains.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count} protocols")

    all_meds = set()
    for p in protocols:
        all_meds.update(p.medications)
    print(f"\nUnique medications across all protocols: {len(all_meds)}")

    print("\nDone. Run clinical_router.py next to test routing.")


if __name__ == "__main__":
    main()
