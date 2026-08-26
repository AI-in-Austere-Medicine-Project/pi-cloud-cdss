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
