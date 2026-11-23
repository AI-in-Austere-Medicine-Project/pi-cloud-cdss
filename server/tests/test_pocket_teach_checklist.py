"""The teach page as one page laid out like the printed checklist (owner, 2026-11-23).

Owner: "Every word on one page, built from the bank (not typed by hand), grouped like
the checklist: "Record first" (the starred words), drug names with their common names
under each generic, then routes, procedures and commands. Each word is a button. Tap it,
say the word, and it stops by itself after a short silence or a second tap. Then it
shows what Pocket heard and adds one take. Each word shows its takes for this speaker (0
to 3) and changes colour when it reaches 3. A bar at the top shows words done out of the
total. No stepping through and no skip button ... A line at the top says so. Ask for the
microphone once and keep it ready ... Works on a phone: one column, buttons big enough
for a thumb. Keep everything else as it is ... Keep the prototype notice and the 'your
recording is deleted' line on the page."
"""
import json
import re
import shutil
import subprocess

import pytest

from tests.test_pocket_teach import (OWNER, SERVER, _clip, _words, client, hearing, owner,  # noqa: F401
                                     runtime)
import pocket_teach as pt  # noqa: E402

HTML = pt.PAGE.read_text()
HARNESS = SERVER / "tests" / "teach_page_harness.js"


# ── the word list, as the checklist groups it ───────────────────────────────

def test_the_groups_come_in_the_checklists_order(client):
    d = client.get("/pocket/teach/words", headers=OWNER).json()
    assert d["groups"] == ["drugs", "routes", "procedures", "commands"]
    order = [w["group"] for w in d["words"]]
    assert order == sorted(order, key=d["groups"].index)


def test_each_generic_comes_first_with_its_common_names_under_it(client):
    words = [w for w in _words(client) if w["group"] == "drugs"]
    seen = []
    for w in words:
        if w["primary"]:
            assert w["drug"] not in seen
            seen.append(w["drug"])
        else:
            assert w["drug"] == seen[-1], w["say"]             # under its own generic
    narcan = next(w for w in words if w["say"] == "narcan")
    assert narcan["drug"] == "naloxone" and not narcan["primary"]
    assert seen == sorted(seen)


def test_recorded_words_keep_their_ids(client):
    """The owner's takes are stored by word id: the new list keeps every old id."""
    ids = {w["id"] for w in _words(client)}
    assert {"drug-acetaminophen", "drug-ketamine", "medic-narcan", "medic-t-x-a", "medic-epi",
            "medic-levophed", "medic-versed", "route-i-v", "control-confirm"} <= ids


def test_record_first_is_what_pocket_does_not_yet_hear_every_time(client):
    words = {w["say"]: w for w in _words(client)}
    assert words["amio"]["record_first"] and words["amio"]["why_first"] == "missed in Pocket's dry run"
    assert not words["ketamine"]["record_first"]


def test_a_take_heard_as_something_else_puts_the_word_first(client, hearing):
    assert not next(w for w in _words(client) if w["say"] == "confirm")["record_first"]
    hearing.open = hearing.next = "cancel"
    assert _clip(client, "control-confirm").json()["as_itself"] is False
    w = next(w for w in _words(client) if w["say"] == "confirm")
    assert w["record_first"] and w["why_first"] == "a take was heard as something else"


def test_a_word_with_its_three_takes_is_no_longer_first(client, hearing):
    hearing.open = hearing.next = "amiel"
    for take in (1, 2, 3):
        assert _clip(client, "drug-amio", take).status_code == 200
    w = next(w for w in _words(client) if w["say"] == "amio")
    assert w["recorded"] == [1, 2, 3] and not w["record_first"]


# ── the page ─────────────────────────────────────────────────────────────────

def test_the_page_keeps_the_notice_and_the_recording_line():
    assert "Research prototype, not for patient care." in HTML
    assert pt.CONSENT in HTML


def test_a_line_at_the_top_says_tap_what_you_know_and_there_is_no_skip():
    assert "tap the words you know and ignore the rest" in HTML
    for gone in ('id="skip"', 'id="prev"', 'id="redo"', 'id="talk"', "HOLD TO TALK", "/pocket/teach/skip"):
        assert gone not in HTML, gone


def test_a_bar_at_the_top_shows_words_done_out_of_the_total():
    assert 'id="bar"' in HTML and "words done" in HTML
    assert HTML.index('id="bar"') < HTML.index('id="list"')


def test_each_word_is_a_button_with_its_takes_and_a_done_colour():
    assert 'class="${cls.join(\' \')}" data-i=' in HTML
    assert ".word.done" in HTML and "${n}/${takes}" in HTML
    assert '★ Record first' in HTML


def test_it_works_on_a_phone_one_column_and_thumb_sized_buttons():
    assert 'name="viewport" content="width=device-width' in HTML
    css = HTML[HTML.index("<style>"):HTML.index("</style>")]
    word = re.search(r"\.word \{([^}]*)\}", css).group(1)
    assert "width: 100%" in word and int(re.search(r"min-height: (\d+)px", word).group(1)) >= 48
    assert "grid-template-columns: minmax(0, 1fr)" in css and "column-count" not in css   # one column, no sideways scroll


def test_the_microphone_is_asked_for_in_one_place_only():
    assert HTML.count("getUserMedia(") == 1


# ── the recorder, run in node with a stub microphone ─────────────────────────

def _run(scenario):
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(pt.PAGE), scenario], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_tap_records_and_a_short_silence_stops_it_and_sends_one_take():
    r = _run("silence")
    assert r["sent"] == [{"word_id": "drug-ketamine", "take": 1, "seconds": r["sent"][0]["seconds"]}]
    assert 1.0 < r["sent"][0]["seconds"] < 2.0                  # pre-roll, the word, the silence
    assert r["micAsks"] == 1
    assert r["note"] == "Take 1 of “ketamine”: Pocket heard “heard it”."


def test_a_second_tap_stops_it():
    r = _run("second_tap")
    assert [(s["word_id"], s["take"]) for s in r["sent"]] == [("drug-ketamine", 1)]


def test_the_microphone_stays_open_across_taps_and_takes_count_up():
    r = _run("two_words")
    assert r["micAsks"] == 1
    assert [(s["word_id"], s["take"]) for s in r["sent"]] == [
        ("drug-ketamine", 1), ("control-no", 1), ("drug-ketamine", 2)]


def test_silence_alone_sends_nothing():
    r = _run("nothing")
    assert r["sent"] == [] and r["note"] == "Nothing heard. Tap the word and say it."


def test_a_word_with_three_takes_records_no_more():
    r = _run("done")
    assert r["sent"] == [] and "has its 3 takes" in r["note"]


def test_a_tap_on_another_word_while_recording_does_not_cut_the_take():
    r = _run("busy_other")
    assert [(s["word_id"], s["take"]) for s in r["sent"]] == [("drug-ketamine", 1)]
