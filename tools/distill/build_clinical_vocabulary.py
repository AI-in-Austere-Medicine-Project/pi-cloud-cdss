#!/usr/bin/env python3
"""D5b: the junk rule's fourth signal, a committed clinical vocabulary.

  python3 tools/distill/build_clinical_vocabulary.py [--server DIR]

Built from the router's protocol keywords (server/protocol_index.json: titles,
conditions, procedures, search terms, aliases, blood products; the router's
curated ROUTING_TERM_SUPPLEMENTS; its slang table, server/query_aliases.json) and the section headings of the JTS
corpus (server/data/jts_protocols/*.pdf, read with pypdf). Words, not
phrases: a question passes if one of its normalised words is in the list.
GENERIC removes words that would let junk through ("mother", "code",
"release", "weight", ...); test_distill_d5b pins that the junk negatives and
the review fragments still fail. Written to tools/distill/clinical_vocabulary.json.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools"))
from build_distill_dataset import normalize  # noqa: E402

MIN_LEN = 4
# A heading is short, starts with a capital, does not end like a sentence, and
# recurs (in at least MIN_HEADING_DOCS documents) or is in capitals.
MAX_HEADING_WORDS = 6
MIN_HEADING_DOCS = 2

STOPWORDS = set("""
about above after again against all also although among and another any are around
because been before being below between both but can cannot could did does doing done down
during each either else enough even ever every few first following for from further get gets
given gives going good great had has have having her here hers herself him himself his how
however into its itself just last least less like likely made make makes making many may
might more most much must near need needs never next none nor not now off often once only
other others otherwise our ours out over own per please rather same seen several shall she
should since some such than that the their theirs them themselves then there these they
thing things this those though through thus too toward under until upon used uses using very
via want was way well were what when where whether which while who whom whose why will with
within without would yes yet you your yours yourself
""".split())

# Words in the sources that say nothing clinical on their own.
GENERIC = set("""
patient patients care management manage managing treatment treat treating clinical clinician
clinicians practice guideline guidelines field prolonged role roles level levels appendix
references reference table tables figure figures summary background introduction overview
recommendation recommendations recommended performance improvement section sections chapter
general standard standards update updated updates version release released notice line lines
code codes local live main move work works working feature back load loaded never review
reviewed unreviewed checkout satisfied requirement requirements available availability
normal weight weights year years male female adult adults child children person people
mother father family friend wife husband baby kids human
time times hour hours minute minutes day days week weeks month months place places point
points part parts type types case cases example examples option options issue issues
use useful important information note notes data number numbers value values goal goals
process system systems team teams unit units area areas site sites setting settings
deployed environment environments military combat austere joint trauma jts cpg cpgs
evidence based quality strategy strategies consideration considerations considered
initial early late ongoing additional specific special common basic advanced key
test tests testing give giving given
action always apply author away best better beyond change check closed coding color count date
door effort energy ensure event events extra follow form forms four full future global ground group
guide high house impact index input intent inter kits large life lift light list locks lower major
manual member minor modes motion moving name nation navy army needed news open order output outs page
peer phase plan plans plus power prior proven quick radio range record remove report rest return rule
safe safely sample saving scale score screen select self setup sheet shell shield simple single size
sized skill sleep slow soon source staff start stat status steps stop stored style supply sure target
task tasks term terms three tools topic total trans trap truck turn typing undue unique upper view
whole window world zone duty filter branch base bank banks card chart charts tape tent assets battle
basics brief bundle device follow freeze future medic medics body bodies casualty casualties
accidents addition addressing advancement advantages advised advisor analyze approach approaches
appropriate approval arrival associated assurance attacks authors automatic average batteries behavior
candidates capabilities capability capture carries cartridge caveats centers changes characteristics
circumstances civilian classes classic coalition collection combined command commanders comments
commercial commonly communication complete completion complex component components composition concerns
consider consult content contents continue continued continuous contributor contributors control controls
conventional coverage criteria current decision definitions department deployment description desirable
determine determining develop development devices direction director discussion disposal document
documentation dynamics education effects efforts electronic emerging equipment essential establishing
estimate ethical examine exchange excessive exercises expected facilities facility familiar finding
findings focused forward frequency functions guidance handling history identification importance
improvised incident incomplete increased increasing individual instructions interest internet interval
investigated involving issuing leadership literature loading locations logistical logistics machine
maintain maintenance material materiel measures members methods metrics minimum mission modified movement
multiple objective obtaining officers opening operating operation operational optimization ordering
organization organizational outcome outcomes packaging parameter parameters pattern perform persistent
personal personnel physical pitfalls planning platforms population portable position possible potential
potentially practices preferred preparation prepare prepared preparing present presentation previous
primary principles priorities priority problem problems product products proficiency properly properties
protect protection provide provider providers publication purpose readiness recognition recognizing
reduced reflective regional regulating related relative repeated replace replacement reporting require
required requiring responders response responsibilities responsibility results resupply routine running
scenario scenarios security selection sequence service shipments signature significant simulator software
solution sources specialty species stability standing starting storage strength studies suggested
supplied supplies support supportive technicians technique techniques technologies temporary terminal
thorough traditional trained training transfer transportation triggering turning typically universal
unknown updating urgently virtual walking warfare wartime weather workers acronym actions activity
""".split())


def words(text: str) -> set:
    return {w for w in normalize(text).split()
            if len(w) >= MIN_LEN and w.isalpha() and w not in STOPWORDS and w not in GENERIC}


def acronyms(text: str) -> set:
    """RSI, TBI, GSW: 3-5 capitals as written in mixed-case text (an all-caps
    line says nothing about which of its words are acronyms)."""
    if text.isupper():
        return set()
    return {t.lower() for t in re.findall(r"\b[A-Z]{3,5}\b", text)
            if t.lower() not in STOPWORDS and t.lower() not in GENERIC}


def router_terms(server: pathlib.Path) -> set:
    index = json.loads((server / "protocol_index.json").read_text())
    out = set()
    for p in index.values():
        out |= words(p.get("title") or "") | acronyms(p.get("title") or "")
        for k in ("primary_conditions", "procedures", "search_terms", "aliases", "blood_products"):
            for term in p.get(k) or []:
                out |= words(str(term)) | acronyms(str(term))
    # The router's slang table: the medic's own abbreviations ("roc", "cric",
    # "fona", "bicarb") are keys of three letters or more; their expansions count too.
    for alias, expansion in json.loads((server / "query_aliases.json").read_text()).items():
        out |= {w for w in normalize(alias).split()
                if len(w) >= 3 and w.isalpha() and w not in STOPWORDS and w not in GENERIC}
        out |= words(str(expansion))
    sys.path.insert(0, str(server))
    from clinical_router import ClinicalRouter
    for terms in ClinicalRouter.ROUTING_TERM_SUPPLEMENTS.values():
        for t in terms:
            out |= words(t) | acronyms(t)
    return out


_HEADING = re.compile(r"^[A-Z][A-Za-z0-9 ,/&()'\-]{2,60}$")
# Contributor and author lines recur across the CPGs and look like headings.
_CONTRIBUTOR = re.compile(r"\b(?:MD|DO|RN|PhD|MPH|MSN|PA-C|DVM|FACS|USA|USAF|USN|USMC|MC|AN|"
                          r"COL|LTC|MAJ|CPT|CAPT|CDR|LCDR|LT|SFC|SSG|MSG|SGT|SMSgt|Lt|Col|Maj|Capt)\b")
MIN_BODY_DOCS = 3      # a heading word must be used, lowercase, in this many CPGs' text
MIN_UNLISTED_LEN = 7   # or, if the system dictionary lacks it, be at least this long


def _dictionary() -> set:
    try:
        return {w.strip() for w in open("/usr/share/dict/words", encoding="utf-8", errors="ignore")
                if w.strip().islower()}
    except OSError:
        return set()


def corpus_heading_terms(server: pathlib.Path) -> set:
    """Heading words used in running text (names never are) that are real words
    (PDF line-break fragments like "ation" are not)."""
    from pypdf import PdfReader
    docs_with = collections.Counter()
    body_docs = collections.Counter()
    caps = set()
    for pdf in sorted((server / "data/jts_protocols").glob("*.pdf")):
        seen, body = set(), set()
        try:
            pages = PdfReader(str(pdf)).pages
        except Exception:
            continue
        for page in pages:
            text = page.extract_text() or ""
            body |= set(re.findall(r"\b[a-z]{3,}\b", text))
            for line in text.splitlines():
                line = line.strip()
                if (not _HEADING.match(line) or line.endswith((",", "-"))
                        or len(line.split()) > MAX_HEADING_WORDS or _CONTRIBUTOR.search(line)):
                    continue
                if line.isupper():
                    caps.add(line)
                seen.add(line)
        docs_with.update(seen)
        body_docs.update(body)
    headings = {h for h, n in docs_with.items() if n >= MIN_HEADING_DOCS} | caps
    dictionary = _dictionary()
    out = set()
    for h in headings:
        out |= {w for w in words(h) if body_docs[w] >= MIN_BODY_DOCS
                and (w in dictionary or len(w) >= MIN_UNLISTED_LEN)}
        out |= acronyms(h)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--server", default=str(REPO / "server"))
    a = p.parse_args(argv)
    server = pathlib.Path(a.server).resolve()
    router = router_terms(server)
    headings = corpus_heading_terms(server)
    index_sha = hashlib.sha256((server / "protocol_index.json").read_bytes()).hexdigest()
    pdfs = sorted(f.name for f in (server / "data/jts_protocols").glob("*.pdf"))
    out = {"_note": "D5b junk rule, fourth signal (owner, #114 review). Generated by "
                    "tools/distill/build_clinical_vocabulary.py; regenerate, don't hand-edit.",
           "sources": {"protocol_index_sha256": index_sha, "corpus_pdfs": len(pdfs),
                       "router_terms": len(router), "heading_terms": len(headings)},
           "terms": sorted(router | headings)}
    (HERE / "clinical_vocabulary.json").write_text(json.dumps(out, indent=0) + "\n")
    print(f"vocabulary: {len(out['terms'])} words ({len(router)} router, {len(headings)} headings, "
          f"{len(router & headings)} both) from {len(pdfs)} PDFs")


if __name__ == "__main__":
    main()
