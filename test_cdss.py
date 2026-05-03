"""
EdgeCDSS Automated Test Suite
Version: 1.2.0
- Fixed test strings matching actual response language
- Added lbs preprocessing to match cdss_client.py behavior
- Fixed forbidden string false positives
"""

import requests
import json
import datetime
import time
import os
import re
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = os.getenv('CDSS_SERVER_URL', 'http://35.223.131.104:8000')
DEVICE_ID = "test-runner"


def preprocess_query(query: str) -> str:
    """Mirror cdss_client.py lbs to kg conversion"""
    def convert_weight(match):
        lbs_val = float(match.group(1))
        kg_val = round(lbs_val / 2.2, 1)
        return f"{lbs_val} lbs ({kg_val} kg)"
    processed = re.sub(
        r'(\d+\.?\d*)\s*(?:lbs?|pounds?)',
        convert_weight,
        query,
        flags=re.IGNORECASE
    )
    return processed


TEST_CASES = [

    # ── DCR / HEMORRHAGE ──────────────────
    {
        "id": "DCR-001",
        "category": "DCR",
        "query": "TXA dosing for hemorrhagic shock 80kg patient",
        "must_contain": ["20 mL", "100mg/mL", "3 hour"],
        "must_not_contain": ["mg/kg", "divide", "calculate", "formula"],
        "must_be_jts": True,
        "description": "TXA dose — should return 20mL, time window, no math"
    },
    {
        "id": "DCR-002",
        "category": "DCR",
        "query": "calcium dosing after blood transfusion",
        "must_contain": ["10 mL", "calcium", "CENTRAL LINE"],
        "must_not_contain": ["mg/kg", "calculate"],
        "must_be_jts": True,
        "description": "Calcium dosing — should return 10mL, central line warning"
    },
    {
        "id": "DCR-003",
        "category": "DCR",
        "query": "patient has SBP 88, HR 118, HCT 30, pH 7.22. Do they need massive transfusion?",
        "must_contain": ["LTOWB", "blood"],
        "must_not_contain": ["crystalloid", "normal saline first", "give saline"],
        "must_be_jts": True,
        "description": "MT recognition — 4/4 criteria met, should trigger MT with LTOWB"
    },
    {
        "id": "DCR-004",
        "category": "DCR",
        "query": "TXA dosing for 220lb patient with penetrating chest wound 2 hours ago",
        "must_contain": ["20 mL", "100mg/mL"],
        "must_not_contain": ["lbs/2.2", "divide by", "calculate"],
        "must_be_jts": True,
        "description": "lbs to kg conversion — should convert silently, return correct dose"
    },
    {
        "id": "DCR-005",
        "category": "DCR",
        "query": "patient bleeding out, what fluid do I give",
        "must_contain": ["blood", "LTOWB"],
        "must_not_contain": ["normal saline first", "start with saline", "give saline first"],
        "must_be_jts": True,
        "description": "No crystalloid rule — should recommend blood not saline"
    },

    # ── ARDS / RESPIRATORY ────────────────
    {
        "id": "ARDS-001",
        "category": "ARDS",
        "query": "vent settings for 5 foot 10 inch male with ARDS, weight 80kg",
        "must_contain": ["mL", "PEEP", "FiO2"],
        "must_not_contain": ["6-8 mL/kg", "PBW =", "formula"],
        "must_be_jts": True,
        "description": "Vent settings — height and weight provided, should return actual mL"
    },
    {
        "id": "ARDS-002",
        "category": "ARDS",
        "query": "patient P:F ratio is 85, what ARDS severity and management",
        "must_contain": ["severe", "lung protective"],
        "must_not_contain": ["mild", "moderate"],
        "must_be_jts": True,
        "description": "ARDS severity — P:F 85 = severe"
    },
    {
        "id": "ARDS-003",
        "category": "ARDS",
        "query": "PPLAT is 34 on my ARDS patient what do I do",
        "must_contain": ["reduce", "tidal"],
        "must_not_contain": ["increase tidal", "raise tidal"],
        "must_be_jts": True,
        "description": "High PPLAT — should reduce VT not increase"
    },

    # ── TBI ───────────────────────────────
    {
        "id": "TBI-001",
        "category": "TBI",
        "query": "severe TBI patient GCS 6, what do I do first",
        "must_contain": ["3%", "Keppra", "TXA"],
        "must_not_contain": ["give steroids", "administer steroids", "give albumin"],
        "must_be_jts": True,
        "description": "Severe TBI immediate actions — 3 key interventions"
    },
    {
        "id": "TBI-002",
        "category": "TBI",
        "query": "TBI patient SBP is 88 what is my goal",
        "must_contain": ["110"],
        "must_not_contain": [],
        "must_be_jts": True,
        "description": "TBI SBP goal — must be >110"
    },
    {
        "id": "TBI-003",
        "category": "TBI",
        "query": "ICP is 28, what do I give",
        "must_contain": ["3%", "250"],
        "must_not_contain": ["steroids"],
        "must_be_jts": True,
        "description": "ICP management — hypertonic saline first line"
    },
    {
        "id": "TBI-004",
        "category": "TBI",
        "query": "keppra loading dose for TBI",
        "must_contain": ["15 mL", "100mg/mL", "1500mg"],
        "must_not_contain": ["mg/kg", "calculate", "formula"],
        "must_be_jts": True,
        "description": "Keppra dosing — exact mL with no math"
    },

    # ── SEDATION / PAIN ───────────────────
    {
        "id": "SED-001",
        "category": "Sedation",
        "query": "ketamine for pain management 80kg patient IV",
        "must_contain": ["mL", "mg/mL", "IV"],
        "must_not_contain": ["mg/kg", "calculate"],
        "must_be_jts": False,
        "description": "Ketamine pain dose — final mL only, no math shown"
    },
    {
        "id": "SED-002",
        "category": "Sedation",
        "query": "ketamine drip for sedation 70kg patient",
        "must_contain": ["mL/hr", "Mix", "Start"],
        "must_not_contain": ["mg/kg/hr", "calculate", "formula"],
        "must_be_jts": False,
        "description": "Ketamine drip — mL/hr with mix instructions"
    },
    {
        "id": "SED-003",
        "category": "Sedation",
        "query": "RSI medications for 90kg patient penetrating chest trauma",
        "must_contain": ["mL", "mg/mL"],
        "must_not_contain": ["mg/kg", "calculate"],
        "must_be_jts": False,
        "description": "RSI dosing — induction and paralytic in final mL"
    },

    # ── WEIGHT CONVERSION ─────────────────
    {
        "id": "WT-001",
        "category": "Weight Conversion",
        "query": "morphine for pain 154lb patient",
        "must_contain": ["mL"],
        "must_not_contain": ["154/2.2", "divide", "lbs/2.2"],
        "must_be_jts": False,
        "preprocess": True,
        "description": "lbs conversion — silent, final mL only"
    },
    {
        "id": "WT-002",
        "category": "Weight Conversion",
        "query": "rocuronium for 220 pound patient RSI",
        "must_contain": ["mL"],
        "must_not_contain": ["220/2.2", "divide"],
        "must_be_jts": False,
        "preprocess": True,
        "description": "lbs to kg — 220lbs=100kg, no math shown"
    },

    # ── NON-JTS QUERIES ───────────────────
    {
        "id": "NJTS-001",
        "category": "Non-JTS",
        "query": "patient bitten by black mamba snake 70kg male",
        "must_contain": ["antivenom"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "Snake envenomation — antivenom guidance"
    },
    {
        "id": "NJTS-002",
        "category": "Non-JTS",
        "query": "steven johnson syndrome identification and treatment",
        "must_contain": ["drug", "outside JTS scope"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "SJS — non-JTS format, stop causative drug"
    },
    {
        "id": "NJTS-003",
        "category": "Non-JTS",
        "query": "patient has signs of malaria, fever, chills, sweating in remote area",
        "must_contain": ["outside JTS scope"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "Malaria — non-JTS format, treatment guidance"
    },
    {
        "id": "NJTS-004",
        "category": "Non-JTS",
        "query": "cholera management austere environment",
        "must_contain": ["rehydration", "outside JTS scope"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "Cholera — non-JTS, ORS and rehydration focus"
    },

    # ── EDGE CASES ────────────────────────
    {
        "id": "EDGE-001",
        "category": "Edge Case",
        "query": "TXA at 4 hours post injury",
        "must_contain": ["DO NOT", "3 hour"],
        "must_not_contain": [],
        "must_be_jts": True,
        "description": "TXA time window — must say DO NOT GIVE after 3 hrs"
    },
    {
        "id": "EDGE-002",
        "category": "Edge Case",
        "query": "steroids for TBI",
        "must_contain": ["DO NOT", "avoid"],
        "must_not_contain": [],
        "must_be_jts": True,
        "description": "Steroids in TBI — must refuse, increases mortality"
    },
    {
        "id": "EDGE-003",
        "category": "Edge Case",
        "query": "what is the weather today",
        "must_contain": ["medical queries only"],
        "must_not_contain": ["sunny", "temperature", "forecast", "weather report"],
        "must_be_jts": False,
        "description": "Non-medical query — should redirect to medical queries only"
    },
    {
        "id": "EDGE-004",
        "category": "Edge Case",
        "query": "give something for pain",
        "must_contain": ["weight", "kg"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "No weight given — should ask for weight before dosing"
    },
    {
        "id": "EDGE-005",
        "category": "Edge Case",
        "query": "albumin for TBI patient",
        "must_contain": ["avoid", "not"],
        "must_not_contain": ["administer albumin", "give albumin freely"],
        "must_be_jts": True,
        "description": "Albumin in TBI — must say avoid"
    },

    # ── FORMAT COMPLIANCE ─────────────────
    {
        "id": "FMT-001",
        "category": "Format",
        "query": "TXA for hemorrhagic shock",
        "must_contain": ["DO THIS", "GIVE", "TLDR", "SOURCE"],
        "must_not_contain": [],
        "must_be_jts": True,
        "description": "JTS format — must have all required sections"
    },
    {
        "id": "FMT-002",
        "category": "Format",
        "query": "tell me about dengue fever",
        "must_contain": ["TREAT", "TLDR", "SOURCE", "outside JTS scope"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "Non-JTS format — must use non-JTS template"
    },
    {
        "id": "FMT-003",
        "category": "Format",
        "query": "fentanyl for pain 80kg patient",
        "must_contain": ["Guideline-based support only"],
        "must_not_contain": [],
        "must_be_jts": False,
        "description": "Disclaimer — every response must end with disclaimer"
    },
]


def run_query(query: str) -> dict:
    """Send query to CDSS backend and return result"""
    try:
        start_time = time.time()
        payload = {
            "query": query,
            "device_id": DEVICE_ID,
            "timestamp": datetime.datetime.now().isoformat(),
            "voice_mode": "brief"
        }
        response = requests.post(
            f"{SERVER_URL}/query",
            json=payload,
            timeout=60
        )
        elapsed = round((time.time() - start_time) * 1000)
        data = response.json()
        return {
            "response": data.get('response', ''),
            "sources": data.get('sources', []),
            "response_time_ms": elapsed,
            "status": "ok"
        }
    except requests.exceptions.ConnectionError:
        return {"response": "", "sources": [], "response_time_ms": 0, "status": "connection_error"}
    except requests.exceptions.Timeout:
        return {"response": "", "sources": [], "response_time_ms": 60000, "status": "timeout"}
    except Exception as e:
        return {"response": "", "sources": [], "response_time_ms": 0, "status": f"error: {str(e)}"}


def evaluate_response(test_case: dict, result: dict) -> dict:
    """Score a response against test criteria"""
    response_lower = result["response"].lower()
    response_original = result["response"]
    passed = True
    failures = []

    for term in test_case.get("must_contain", []):
        if term.lower() not in response_lower and term not in response_original:
            passed = False
            failures.append(f"MISSING: '{term}'")

    for term in test_case.get("must_not_contain", []):
        if term.lower() in response_lower:
            passed = False
            failures.append(f"FOUND FORBIDDEN: '{term}'")

    time_warning = ""
    if result["response_time_ms"] > 15000:
        time_warning = f"SLOW ({result['response_time_ms']}ms)"
    elif result["response_time_ms"] > 8000:
        time_warning = f"MODERATE ({result['response_time_ms']}ms)"

    return {
        "passed": passed,
        "failures": failures,
        "time_warning": time_warning,
        "response_time_ms": result["response_time_ms"]
    }


def run_test_suite(repeat: int = 1, delay_seconds: int = 2):
    """Run full test suite"""
    all_results = []
    total_passed = 0
    total_failed = 0
    total_errors = 0
    category_scores = {}

    print("=" * 70)
    print("EdgeCDSS Automated Test Suite v1.2.0")
    print(f"Server: {SERVER_URL}")
    print(f"Test cases: {len(TEST_CASES)}")
    print(f"Repeat cycles: {repeat}")
    print(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    for cycle in range(repeat):
        if repeat > 1:
            print(f"\n{'─' * 70}")
            print(f"CYCLE {cycle + 1} of {repeat}")
            print(f"{'─' * 70}")

        for test in TEST_CASES:
            print(f"\n[{test['id']}] {test['description']}")

            # Apply preprocessing if needed
            query = test['query']
            if test.get('preprocess', False):
                query = preprocess_query(query)

            print(f"Query: {query}")

            result = run_query(query)

            if result['status'] != 'ok':
                print(f"❌ ERROR: {result['status']}")
                total_errors += 1
                all_results.append({
                    "cycle": cycle + 1,
                    "test_id": test['id'],
                    "category": test['category'],
                    "query": query,
                    "status": "error",
                    "error": result['status'],
                    "response": "",
                    "response_time_ms": 0,
                    "passed": False,
                    "failures": [result['status']]
                })
                continue

            evaluation = evaluate_response(test, result)

            cat = test['category']
            if cat not in category_scores:
                category_scores[cat] = {"passed": 0, "failed": 0}

            if evaluation['passed']:
                total_passed += 1
                category_scores[cat]["passed"] += 1
                status_icon = "✅"
            else:
                total_failed += 1
                category_scores[cat]["failed"] += 1
                status_icon = "❌"

            print(f"{status_icon} {'PASS' if evaluation['passed'] else 'FAIL'} | {result['response_time_ms']}ms {evaluation['time_warning']}")
            if evaluation['failures']:
                for f in evaluation['failures']:
                    print(f"   ⚠️  {f}")

            all_results.append({
                "cycle": cycle + 1,
                "test_id": test['id'],
                "category": test['category'],
                "query": query,
                "status": "ok",
                "response": result['response'],
                "response_time_ms": result['response_time_ms'],
                "passed": evaluation['passed'],
                "failures": evaluation['failures'],
                "time_warning": evaluation['time_warning'],
                "sources": result['sources']
            })

            if delay_seconds > 0:
                time.sleep(delay_seconds)

    total_tests = total_passed + total_failed + total_errors
    pass_rate = round((total_passed / total_tests) * 100, 1) if total_tests > 0 else 0
    avg_response_time = round(
        sum(r['response_time_ms'] for r in all_results if r['status'] == 'ok') /
        max(len([r for r in all_results if r['status'] == 'ok']), 1)
    )

    report_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    report_filename = f"cdss_test_report_{report_time}.txt"

    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("EdgeCDSS TEST REPORT v1.2.0")
    report_lines.append(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Server: {SERVER_URL}")
    report_lines.append("=" * 70)
    report_lines.append("")
    report_lines.append("SUMMARY")
    report_lines.append(f"  Total Tests:    {total_tests}")
    report_lines.append(f"  Passed:         {total_passed}")
    report_lines.append(f"  Failed:         {total_failed}")
    report_lines.append(f"  Errors:         {total_errors}")
    report_lines.append(f"  Pass Rate:      {pass_rate}%")
    report_lines.append(f"  Avg Response:   {avg_response_time}ms")
    report_lines.append(f"  Cycles Run:     {repeat}")
    report_lines.append("")
    report_lines.append("RESULTS BY CATEGORY")
    report_lines.append("─" * 40)
    for cat, scores in sorted(category_scores.items()):
        total_cat = scores['passed'] + scores['failed']
        cat_rate = round((scores['passed'] / total_cat) * 100, 1) if total_cat > 0 else 0
        icon = "✅" if cat_rate == 100 else "⚠️" if cat_rate >= 70 else "❌"
        report_lines.append(f"  {icon} {cat}: {scores['passed']}/{total_cat} ({cat_rate}%)")
    report_lines.append("")
    report_lines.append("FAILED TESTS")
    report_lines.append("─" * 40)
    failed_tests = [r for r in all_results if not r['passed']]
    if failed_tests:
        for r in failed_tests:
            report_lines.append(f"  [{r['test_id']}] {r['query']}")
            for f in r['failures']:
                report_lines.append(f"    → {f}")
            report_lines.append(f"    Response: {r['response'][:300]}...")
            report_lines.append("")
    else:
        report_lines.append("  None — all tests passed!")
    report_lines.append("")
    report_lines.append("SLOW RESPONSES (>8 seconds)")
    report_lines.append("─" * 40)
    slow_tests = [r for r in all_results if r['response_time_ms'] > 8000]
    if slow_tests:
        for r in slow_tests:
            report_lines.append(f"  [{r['test_id']}] {r['response_time_ms']}ms — {r['query']}")
    else:
        report_lines.append("  None — all responses under 8 seconds")
    report_lines.append("")
    report_lines.append("FULL RESULTS")
    report_lines.append("─" * 40)
    for r in all_results:
        status = "✅ PASS" if r['passed'] else "❌ FAIL"
        report_lines.append(f"[{r['test_id']}] {status} | {r['response_time_ms']}ms | {r['query'][:60]}")
        if r['response']:
            report_lines.append(f"  Response: {r['response'][:300]}")
        report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 70)

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print(f"  Pass Rate: {pass_rate}% ({total_passed}/{total_tests})")
    print(f"  Avg Response Time: {avg_response_time}ms")
    print(f"  Report saved: {report_filename}")
    print("=" * 70)

    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    json_filename = f"cdss_test_results_{report_time}.json"
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"  JSON data saved: {json_filename}")

    return all_results


if __name__ == "__main__":
    import sys

    repeat = 1
    delay = 2

    if len(sys.argv) > 1:
        repeat = int(sys.argv[1])
    if len(sys.argv) > 2:
        delay = int(sys.argv[2])

    run_test_suite(repeat=repeat, delay_seconds=delay)