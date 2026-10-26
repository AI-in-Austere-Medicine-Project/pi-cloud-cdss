"""The desktop client's ElevenLabs path is deleted (owner, 2026-10-26).

V2 removed cloud voice from the server; client/cdss_client.py still sent the
answer text to ElevenLabs with its own key. It no longer speaks at all, and
nothing in the client may reach a cloud voice service.

    cd server && ./run_unit_tests.sh
"""
import pathlib
import re

CLIENT = pathlib.Path(__file__).resolve().parents[2] / "client"


def test_the_client_has_no_elevenlabs_path():
    src = (CLIENT / "cdss_client.py").read_text()
    assert not re.search(r"elevenlabs|ELEVENLABS|xi-api-key", src, re.I)


def test_the_client_does_not_install_elevenlabs():
    reqs = (CLIENT / "requirements.txt").read_text().lower()
    assert "elevenlabs" not in reqs


def test_the_client_still_compiles():
    compile((CLIENT / "cdss_client.py").read_text(), "cdss_client.py", "exec")
