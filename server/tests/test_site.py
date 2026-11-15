"""The project site, web/ (owner, 2026-11-15: website tidy-up).

Owner: "Replace web/index.html with /home/andrew/site-draft/index.html. Check every link on
it resolves, and correct any stale fact (version, test count). Restyle the pages that stay
on the site (ethics-governance.html and the release-notes pages) to match the new index:
same colours, fonts, width and light/dark behaviour, with a "← AI-AMP" link back to the
index at the top. Move the shared styles into one CSS file. Do not change any wording on
those pages. Old links must keep working."

The wording pin: each restyled page's visible text (the back link aside, which the owner
asked to read "← AI-AMP") hashes to what it was on main before the restyle.
"""
import hashlib
import html.parser
import pathlib
import re
import sys

import pytest

SERVER = pathlib.Path(__file__).resolve().parents[1]
WEB = SERVER.parent / "web"
sys.path.insert(0, str(SERVER))

RESTYLED = {   # visible text sha256 on main (36ec28c), before the restyle
    "ethics-governance.html": "829ea0cbdef57bd74ebeb2af47d225486005178f5aed46fcd21a20dcf78253a1",
    "release-notes-4.0.html": "561520de4c06bcffac1375de386e07e14042d7e7c702496479f3cd465162faf4",
    "release-notes-4.1.html": "f4ce6a4148e7214b84c00102e6557d1f2adbd664a1da2ac313ab3ee6646d6c6c",
    "release-notes-4.3.html": "3295e67b46cd205b66b1a91f01535297bc70c1c80b4e251d14c3d9d5cd3fb2e1",
}
# Every page and file a link may point at today: they keep working.
OLD_PATHS = ("index.html", "ethics-governance.html", "release-notes-4.0.html",
             "release-notes-4.1.html", "release-notes-4.3.html", "v4.3-showcase.html",
             "papers.json")


class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip, self.back = [], 0, 0
        self.hrefs, self.srcs, self.stylesheets, self.styles, self.first_link = [], [], [], 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script", "title"):
            self.skip += 1
        if tag == "style":
            self.styles += 1
        if tag == "link" and a.get("rel") == "stylesheet":
            self.stylesheets.append(a.get("href"))
        if tag == "a":
            if self.first_link is None:
                self.first_link = (a.get("href"), a.get("class") or "")
            if "back" in (a.get("class") or "").split():
                self.back += 1
            if a.get("href"):
                self.hrefs.append(a["href"])
        if tag in ("img", "iframe", "script") and a.get("src"):
            self.srcs.append(a["src"])
        if tag == "img" and a.get("alt"):
            self.out.append(a["alt"])

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title"):
            self.skip -= 1
        if tag == "a" and self.back:
            self.back -= 1

    def handle_data(self, d):
        if not self.skip and not self.back:
            self.out.append(d)
        if self.back:
            self.back_text = getattr(self, "back_text", "") + d

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.out)).strip()


def _page(name):
    p = _Text()
    p.feed((WEB / name).read_text(encoding="utf-8"))
    return p


def test_old_links_keep_working():
    for name in OLD_PATHS:
        assert (WEB / name).exists(), name


def test_every_page_uses_the_one_shared_stylesheet():
    assert (WEB / "site.css").exists()
    for name in ("index.html", *RESTYLED):
        p = _page(name)
        assert p.stylesheets == ["site.css"], (name, p.stylesheets)
        assert p.styles == 0, f"{name} still carries its own <style>"


@pytest.mark.parametrize("name", sorted(RESTYLED))
def test_the_wording_of_a_restyled_page_is_unchanged(name):
    assert hashlib.sha256(_page(name).text().encode()).hexdigest() == RESTYLED[name]


@pytest.mark.parametrize("name", sorted(RESTYLED))
def test_a_restyled_page_starts_with_the_link_back_to_ai_amp(name):
    p = _page(name)
    assert p.first_link == ("index.html", "back"), p.first_link
    assert p.back_text.strip() == "← AI-AMP"


def test_the_shared_stylesheet_follows_light_and_dark():
    css = (WEB / "site.css").read_text()
    assert "@media (prefers-color-scheme: dark)" in css
    assert "fonts.googleapis" not in css
    for name in RESTYLED:
        assert "fonts.googleapis" not in (WEB / name).read_text(), name


@pytest.mark.parametrize("name", ["index.html", *sorted(RESTYLED)])
def test_every_local_link_resolves(name):
    p = _page(name)
    for ref in p.hrefs + p.srcs + p.stylesheets:
        if re.match(r"^(https?:|mailto:|#)", ref):
            continue
        target = ref.split("#")[0]
        assert (WEB / target).exists(), (name, ref)


def test_the_index_states_the_current_version():
    from version import __version__
    html = (WEB / "index.html").read_text()
    assert f"v{__version__}" in html
    assert "aiamp.substack.com" in html and "cdss.arcanekg.com/pocket" in html


def test_the_index_carries_the_research_prototype_notice():
    assert "Research prototype." in _page("index.html").text()


def test_each_project_card_links_its_published_release():
    """Owner, 2026-11-15: EdgeCDSS v5.1.0 and Pocket v1.1 are published releases."""
    html = (WEB / "index.html").read_text()
    org = "https://github.com/AI-in-Austere-Medicine-Project"
    assert f'href="{org}/pi-cloud-cdss/releases/tag/v5.1.0">v5.1.0</a>' in html
    assert f'href="{org}/edgecdss-pocket/releases/tag/v1.1">v1.1</a>' in html
    assert "about $95 in parts · spoken answer in about two seconds on the device" in html  # Pocket README, re-costed 2026-11-16
