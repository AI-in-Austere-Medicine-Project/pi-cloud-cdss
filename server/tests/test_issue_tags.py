"""The flag panel's issue tags (owner, 2026-10-05, C1 review): the proposed list
from the 22 flagged reports, kept in a data file (server/issue_tags.json), so a
later edit is one line there and one line in APPROVED below.

Approved: four new tags (answered a different question; held or refused
something safe; patient details misread or re-asked; dose or calculation not
given), four kept (missing critical step; too vague / not actionable;
contradicts current CPG; dose incorrect), four dropped (medication choice
inappropriate; wrong route/access; sources wrong/irrelevant; format hard to use
in field). Non-clinical problems go to the comment box, not a tag.
"""
import asyncio
import json
import os
import pathlib
import re
import sys
import types

import pytest

HERE = pathlib.Path(__file__).parent
TAGS_FILE = HERE.parent / "issue_tags.json"
CLIENT = (HERE.parent / "static" / "index.html").read_text()

# The one list. Change it here and in issue_tags.json together.
APPROVED = [
    "Dose incorrect",
    "Answered a different question",
    "Held or refused something safe",
    "Missing critical step",
    "Dose or calculation not given",
    "Patient details misread or re-asked",
    "Too vague / not actionable",
    "Contradicts current CPG",
]
DROPPED = ["Medication choice inappropriate", "Wrong route/access",
           "Sources wrong/irrelevant", "Format hard to use in field"]


def test_the_data_file_holds_the_approved_list():
    assert json.loads(TAGS_FILE.read_text())["tags"] == APPROVED


def test_the_dropped_tags_are_gone():
    tags = json.loads(TAGS_FILE.read_text())["tags"]
    assert not set(DROPPED) & set(tags)
    assert not any(t in CLIENT for t in DROPPED)


def test_every_tag_fits_the_feedback_schema():
    pytest.importorskip("fastapi")
    os.environ.setdefault("OPENAI_API_KEY", "test-offline")
    os.environ.setdefault("CDSS_ACCESS_TOKEN", "test-token-not-the-demo-one")
    sys.path.insert(0, str(HERE.parent))
    if "embeddings" not in sys.modules:
        stub = types.ModuleType("embeddings")
        stub.ChromaDBClient = type("C", (), {"get_collection_count": lambda s: 0})
        sys.modules["embeddings"] = stub
    import main
    assert len(APPROVED) <= main.MAX_FEEDBACK_ISSUES
    assert all(len(t) <= main.MAX_ISSUE_CHARS for t in APPROVED)


def test_the_server_serves_the_list():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")
    import main

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.get("/issue_tags")
    r = asyncio.run(go())
    assert r.status_code == 200 and r.json()["tags"] == APPROVED


def test_the_client_has_no_tag_list_of_its_own():
    assert not re.search(r"const ISSUE_TAGS\s*=\s*\[", CLIENT)
    assert "fetch('/issue_tags')" in CLIENT


def test_the_flag_panel_still_opens_without_the_list():
    # A failed fetch leaves an empty list: the panel renders its two text
    # boxes and no checkboxes, so a report can always be filed.
    loader = CLIENT[CLIENT.index("async function loadIssueTags"):][:700]
    assert "catch" in loader
    assert re.search(r"let issueTags\s*=\s*\[\]", CLIENT)
