"""
EdgeCDSS — one version, one place.

/status reported "4.1.0" through four merged PRs. Nothing failed: main.py held
two independent "4.1.0" literals, and a bump meant remembering both. A version
that is a fact in one place cannot half-land.

    cd server && ./run_unit_tests.sh
"""

import os
import pathlib
import re
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import version  # noqa: E402

HERE = pathlib.Path(__file__).parent
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# A version-shaped literal. Bare "4.2" is not one: it appears in prose and in
# protocol text, and a test that fails on it stops being run.
_LITERAL = re.compile(r"""["']\d+\.\d+\.\d+["']""")


def test_the_version_is_a_semver_string():
    assert _SEMVER.match(version.__version__), version.__version__
    assert version.VERSION == version.__version__


def test_the_version_is_the_one_being_shipped():
    """Bump here and in CHANGELOG.md together, or the release notes describe a
    build nobody is running."""
    assert version.__version__ == "4.2.0"
    changelog = (HERE.parent / "CHANGELOG.md").read_text()
    assert "## [4.2.0]" in changelog, "CHANGELOG has no section for this version"


def test_status_reports_the_shipped_version():
    """The endpoint the operator actually reads."""
    main = (HERE / "main.py").read_text()
    assert 'from version import __version__' in main
    assert '"version": __version__' in main
    assert 'FastAPI(title="CDSS Cloud API", version=__version__)' in main


def test_no_version_literal_survives_in_the_server():
    """The actual failure mode: a second copy that a bump forgets.

    version.py itself is the one place a literal belongs.
    """
    offenders = []
    for path in sorted(HERE.glob("*.py")):
        # Shipped modules only. A version-shaped string inside a test fixture is
        # a fixture, and widening this to catch those makes it fail on data.
        if path.name == "version.py" or path.name.startswith("test_"):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if _LITERAL.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "version literals outside version.py:\n" + "\n".join(offenders)
