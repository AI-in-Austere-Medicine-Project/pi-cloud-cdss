"""The thin client is retired (owner, 2026-11-18): "Thin client: retire it and its 3
tests. I use the web portal."

The web portal (server/static/index.html) and Pocket are the clients. History may
name the old client (CHANGELOG, the archive, the work order); nothing current tells a
reader to install or run it.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CURRENT = ("README.md", "CONTRIBUTING.md", "SAFETY.md", "START-HERE/FIRST_TIME_GUIDE.md",
           "docs/REFERENCE.md", "requirements-server.txt")


def test_the_thin_client_is_gone():
    assert not (ROOT / "client").exists()


def test_no_current_doc_points_at_the_thin_client():
    for rel in CURRENT:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for name in ("cdss_client", "client/requirements.txt", "client/"):
            assert name not in text, (rel, name)
