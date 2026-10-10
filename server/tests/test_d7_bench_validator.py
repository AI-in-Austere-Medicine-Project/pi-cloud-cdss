"""D7 bench (owner, 2026-10-10): bench_remote.sh passes the offline validator
setting through, so a distilled tag is benched as the generator with
qwen2.5:3b as its validator.

bench_remote.sh unset CDSS_VALIDATOR_MODEL with the provider keys. It now takes
VALIDATOR (default qwen2.5:3b; `make bench VALIDATOR=`), exports it as
CDSS_VALIDATOR_MODEL for both arms, records it in meta.json, and checks after
each arm that every model turn was validated by it. cdss-eval's run_bank.py
drops CDSS_VALIDATOR_MODEL before starting its server, so the 30-set arm gets
the server default; the script refuses any other validator rather than label a
run with one it did not use. The report names the validator in Setup.
"""
import argparse
import importlib.util
import json
import pathlib
import re
import subprocess

DISTILL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "distill"
SH = (DISTILL / "jetson" / "bench_remote.sh").read_text()
spec = importlib.util.spec_from_file_location("d6", DISTILL / "d6.py")
d6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d6)


def test_the_script_takes_the_validator_default_qwen():
    assert re.search(r'VALIDATOR=\$\{VALIDATOR:-qwen2\.5:3b\}', SH)


def test_the_script_exports_it_after_clearing_the_environment():
    unset = SH.index("unset OPENAI_API_KEY")
    export = SH.index('export CDSS_VALIDATOR_MODEL="$VALIDATOR"')
    assert export > unset, "exported before the unset line, it would be cleared"


def test_the_script_refuses_a_validator_the_30_set_would_not_use():
    guard = SH[:SH.index("# ── pinned snapshot")]
    assert re.search(r'\[ "\$VALIDATOR" = qwen2\.5:3b \] \|\| die', guard)
    assert 'ollama show "$VALIDATOR"' in guard


def test_the_script_checks_each_arm_used_it():
    arm = SH[SH.index("run_arm() {"):SH.index("run_arm base")]
    assert "validator_model" in arm and "VALIDATOR" in arm


def test_the_bench_records_the_validator():
    meta = SH[SH.index("json.dump({"):SH.index("open(f\"{W}/meta.json\"")]
    assert '"validator"' in meta


def test_make_bench_passes_the_validator():
    out = subprocess.run(["make", "-n", "-C", str(DISTILL), "bench", "TAG=edgecdss-x"],
                         capture_output=True, text=True).stdout
    assert re.search(r"VALIDATOR=qwen2\.5:3b bash edgecdss-models/bench_remote\.sh", out), out


def _meta(tmp_path, **extra):
    b = tmp_path / "bench"
    b.mkdir()
    (b / "meta.json").write_text(json.dumps({
        "commit": "c", "signed": 68, "entries": 108, "ollama": "0.34.2", "power": "25W",
        "kernel": "6.8", "tag": "edgecdss-v3", "base": "qwen2.5:3b", "tag_id": "t", "base_id": "b",
        "scenarios_src": "s", "scenarios_sha256": "0" * 64, "bank_port": 8123, "rt_port": 8012,
        "started": "2026-10-10T00:00:00+00:00", **extra}))
    (b / "tokps.jsonl").write_text("")
    for lab in ("base", "tag"):
        (b / f"{lab}.results.jsonl").write_text(json.dumps(
            {"request_id": "X#r1", "scenario_id": "X", "outcome": "SERVE", "response": "a",
             "server_processing_ms": 1000}) + "\n")
        (b / f"{lab}.instrument.jsonl").write_text(json.dumps(
            {"request_id": "X#r1", "generator_calls": 1, "generation_ms": 900}) + "\n")
        (b / f"run_tests.{lab}.txt").write_text("RESULTS: 29 passed / 29 total\n")
    (b / "specifics.json").write_text(json.dumps({}))
    return b


def _setup(tmp_path, monkeypatch, **extra):
    monkeypatch.setattr(d6, "token_counter", lambda path: lambda text: len(text.split()))
    out = tmp_path / "doc.md"
    d6.cmd_report(argparse.Namespace(bench=str(_meta(tmp_path, **extra)), out=str(out), stages=None,
                                     note=None, rt_base=None, specifics=None, tokenizer="unused"))
    return out.read_text()


def test_the_report_names_the_validator(tmp_path, monkeypatch):
    doc = _setup(tmp_path, monkeypatch, validator="qwen2.5:3b")
    assert "| Validator | `qwen2.5:3b` in both arms (`CDSS_VALIDATOR_MODEL`) |" in doc


def test_a_bench_from_before_d7_says_the_validator_was_the_generator(tmp_path, monkeypatch):
    doc = _setup(tmp_path, monkeypatch)
    assert "| Validator | each arm's own generator model (before D7) |" in doc
