"""Make the application modules importable from tests/.

The suite used to sit beside the code it tests, so `import openai_client`
worked because pytest puts a test file's own directory on sys.path. The tests
moved into their own directory on 2026-08-26; this puts server/ back on the
path so that import means the same thing it always did.

A shim rather than a package: adding __init__.py would make the tests an
importable package and change how pytest resolves rootdir and conftest, which
is a behaviour change to the test runner in a commit that is supposed to be a
move. This is the smaller thing that does the same job.
"""
import pathlib
import sys

SERVER = pathlib.Path(__file__).resolve().parent.parent
TOOLS = SERVER / "tools"

# tools/ too: test_set_contract.py imports the signing tool as a module, and
# the tools are run as `python3 tools/set_contract.py`, which puts tools/ on
# the path the same way. Both directories, so an import here means what it
# means at the command line.
for path in (SERVER, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


# ── the concentration kit the suite runs against ────────────────────────────
# drug_concentrations.json is deployment state: gitignored, and signed for
# whatever is in THIS box's bag. The suite used to read it, so it passed on a
# deployed device and failed on a clean checkout (no file: no vials, 19
# failures and 24 errors), and would have started failing on the device the
# day the kit changed. Tests are not allowed to depend on which machine they
# run on, so they run against a pinned kit instead: the committed example
# file, with exactly the presentations below signed.
#
# Only the suite sees this. drug_concentrations.CONFIG is left pointing at the
# live file, so nothing here can be written to it or read by a server, and the
# live kit is still checked on the device by
# test_the_live_kit_on_this_device_is_signed_properly.
import json as _json
import tempfile as _tempfile

TEST_KIT_SIGNED = {
    ("ketamine", "500 mg / 10 mL vial"),
    ("succinylcholine", "100 mg / 2 mL ampoule"),
    ("rocuronium", "100 mg / 10 mL vial"),
    ("lorazepam", "4 mg / 2 mL ampoule"),
    ("tranexamic acid", "1000 mg / 10 mL ampoule"),
    ("naloxone", "0.4 mg / 1 mL ampoule"),
}


def _install_test_kit():
    import drug_concentrations as dcn

    kit = _json.loads((SERVER / "drug_concentrations.example.json").read_text())
    kit["kit_id"] = "test-kit"
    signed = set()
    for entry in kit["entries"]:
        for pres in entry["presentations"]:
            key = (entry["generic_name"], pres["label_text"])
            if key in TEST_KIT_SIGNED:
                pres.update(signoff=True, reviewed_by="clinician",
                            review_date="2026-08-25")
                signed.add(key)
    missing = TEST_KIT_SIGNED - signed
    if missing:
        raise RuntimeError(f"the test kit signs presentations the example file "
                           f"no longer declares: {sorted(missing)}")

    live = dcn.CONFIG
    with _tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "drug_concentrations.test.json"
        path.write_text(_json.dumps(kit))
        dcn.CONFIG = path
        try:
            dcn.ENTRIES, dcn.REJECTIONS, dcn._RAW = dcn._load()
        finally:
            dcn.CONFIG = live


_install_test_kit()
