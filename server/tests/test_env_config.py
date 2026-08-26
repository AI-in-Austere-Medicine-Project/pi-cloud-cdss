"""
EdgeCDSS — environment tuning knobs must not be able to brick startup.

The deploy path is manual, on a fanless edge device behind a tunnel, guarded by
a watchdog that reboots the box after repeated failed health checks. A module
scope `float(os.getenv(...))` on a typo'd tuning value raises at IMPORT: uvicorn
never starts, /health never answers, and the watchdog reboots in a loop. These
knobs exist to be tuned, so they will eventually be typo'd.

    cd server && ./run_unit_tests.sh
"""

import os
import subprocess
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_client import _env_number  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every numeric knob, with the default it must fall back to.
NUMERIC_ENV_KNOBS = {
    "CDSS_PATIENT_TIMEOUT_MIN": 30.0,   # module scope — this one bricks startup
    "CDSS_EVENT_TURNS": 12,
    "CDSS_RAG_TOP_K": 10,
}

GARBAGE = ("30m", "thirty", "", "   ", "3 0", "None", "null", "12.5.1", "-", "1e", "12,5")


def test_valid_values_are_used():
    os.environ["CDSS_TEST_KNOB"] = "45"
    try:
        assert _env_number("CDSS_TEST_KNOB", 30.0, float) == 45.0
        assert _env_number("CDSS_TEST_KNOB", 12, int) == 45
    finally:
        del os.environ["CDSS_TEST_KNOB"]


def test_surrounding_whitespace_is_tolerated():
    os.environ["CDSS_TEST_KNOB"] = "  45  "
    try:
        assert _env_number("CDSS_TEST_KNOB", 30.0, float) == 45.0
    finally:
        del os.environ["CDSS_TEST_KNOB"]


def test_unset_returns_the_default():
    os.environ.pop("CDSS_TEST_KNOB", None)
    assert _env_number("CDSS_TEST_KNOB", 30.0, float) == 30.0


def test_garbage_falls_back_instead_of_raising():
    for value in GARBAGE:
        os.environ["CDSS_TEST_KNOB"] = value
        try:
            assert _env_number("CDSS_TEST_KNOB", 30.0, float) == 30.0, value
            assert _env_number("CDSS_TEST_KNOB", 12, int) == 12, value
        finally:
            del os.environ["CDSS_TEST_KNOB"]


def import_with(env_overrides):
    """Import openai_client in a clean subprocess with these env vars set."""
    env = dict(os.environ, **env_overrides)
    return subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import openai_client; "
         "print(openai_client.PATIENT_BOUNDARY_TIMEOUT_MIN)" % HERE],
        env=env, capture_output=True, text=True,
    )


def test_module_imports_with_a_typod_timeout():
    """THE ONE THAT MATTERS. A typo here used to be an import-time ValueError.

    Import failure means the service does not start, /health never answers, and
    the watchdog reboots the device — remotely, with no way in.
    """
    for value in GARBAGE:
        proc = import_with({"CDSS_PATIENT_TIMEOUT_MIN": value})
        assert proc.returncode == 0, f"{value!r} broke import:\n{proc.stderr}"
        assert proc.stdout.strip().endswith("30.0"), (value, proc.stdout)


def test_module_imports_with_every_knob_typod_at_once():
    proc = import_with({k: "not-a-number" for k in NUMERIC_ENV_KNOBS})
    assert proc.returncode == 0, proc.stderr


def test_a_valid_timeout_still_takes_effect_at_import():
    """The knob must remain tunable — hardening must not pin it to the default."""
    proc = import_with({"CDSS_PATIENT_TIMEOUT_MIN": "45"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("45.0"), proc.stdout


def test_bad_value_is_announced_not_silent():
    """A silently ignored tuning value is its own failure: the operator thinks
    the knob is set and it is not."""
    proc = import_with({"CDSS_PATIENT_TIMEOUT_MIN": "30m"})
    assert "CDSS_PATIENT_TIMEOUT_MIN" in proc.stdout
    assert "30m" in proc.stdout


def test_no_raw_numeric_env_parse_remains():
    """Meta-test: a future int(os.getenv(...)) reintroduces the whole class."""
    import re
    source = open(os.path.join(HERE, "openai_client.py")).read()
    bad = re.findall(r'(?:int|float)\(\s*os\.(?:getenv|environ)', source)
    assert not bad, f"raw numeric env parse found ({len(bad)}) — use _env_number()"
