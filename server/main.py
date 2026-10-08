from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator
from datetime import datetime
from typing import Annotated, List, Optional
from collections import deque
import asyncio
import json
import os
from dotenv import load_dotenv
from embeddings import ChromaDBClient
from version import __version__
from openai_client import INPUT_MODES, query_with_rag
import general_reference
import providers
import tts

load_dotenv()
app = FastAPI(title="CDSS Cloud API", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

try:
    chromadb_client = ChromaDBClient()
    print("✅ ChromaDB and OpenAI clients initialized")
except Exception as e:
    print(f"❌ Error: {e}")
    raise

ACCESS_TOKEN = os.getenv("CDSS_ACCESS_TOKEN", "edgecdss-demo-2026")
FEEDBACK_LOG = os.getenv("FEEDBACK_LOG", "feedback.log")

# ── Request ceilings (AE-1, AE-4) ────────────────────────────────────────
# Every one of these is a REFUSAL limit, not a truncation. A real session is
# orders of magnitude below all of them, and silently dropping the tail of a
# conversation would lose a weight stated in turn 1 rather than fail where
# someone can see it — the F-1 lesson applied to transport.
MAX_QUERY_CHARS = 8_000            # longest question anyone has ever asked
MAX_ID_CHARS = 64                  # C1: session/query ids, provider, verdict, source_mode
MAX_RESPONSE_CHARS = 20_000        # feedback echoes an answer back at us
MAX_FEEDBACK_TEXT = 4_000          # suggestion / comment
MAX_FEEDBACK_ISSUES = 32           # the client offers a fixed tag list
MAX_ISSUE_CHARS = 200
MAX_HISTORY_TURNS = 100
# Turn COUNT is not the whole story: 100 turns each carrying a megabyte is
# the same attack with fewer items. openai_client's context rebuild walks
# EVERY turn through the vitals and context regexes, so the work tracks
# total text, not list length.
MAX_HISTORY_BYTES = 256_000

def require_token(x_access_token: str = Header(default="")) -> None:
    """The access-token gate, as a dependency rather than a line in each handler.

    FastAPI solves a route's dependencies BEFORE it validates the request body,
    so an anonymous caller gets 401 whatever they sent. Checked INSIDE the
    handler — where these checks used to live — pydantic ran first, so an
    unauthenticated request carrying a malformed body got 422: it told an
    anonymous caller the shape of the schema, and it made the server do the
    validation work for someone who had not authenticated. That is the bug a
    naive fix leaves behind, and it is the reason this is a dependency and not
    four copies of an if-statement.

    test_auth_runs_before_body_validation pins the ordering, because nothing in
    the signature of this function reveals it.
    """
    if x_access_token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")


class QueryRequest(BaseModel):
    query: str = Field(..., max_length=MAX_QUERY_CHARS)
    device_id: str = Field(..., max_length=200)
    timestamp: str = Field(..., max_length=64)
    voice_mode: str = Field("brief", max_length=32)
    conversation_history: list = Field(default_factory=list,
                                       max_length=MAX_HISTORY_TURNS)
    model: str = Field("", max_length=128)  # "" = server default; unknown values fall back to it
    # How the query was entered: typed, voice, or a brief-first follow-up chip.
    # Logged, never branched on — a chip's query goes down exactly the path the
    # same words typed would.
    input_mode: str = Field("typed", max_length=16)
    # C1: the client's per-tab session id (sessionStorage). Logged, never
    # branched on, like input_mode.
    session_id: str = Field("", max_length=MAX_ID_CHARS)

    @field_validator("input_mode")
    @classmethod
    def _known_input_mode(cls, v):
        if v not in INPUT_MODES:
            raise ValueError(f"input_mode must be one of {', '.join(INPUT_MODES)}")
        return v

    @field_validator("conversation_history")
    @classmethod
    def _history_within_budget(cls, v):
        """Bound the TEXT, not just the turn count. See MAX_HISTORY_BYTES."""
        if len(json.dumps(v, default=str)) > MAX_HISTORY_BYTES:
            raise ValueError(
                f"conversation_history exceeds {MAX_HISTORY_BYTES} bytes")
        return v

class QueryResponse(BaseModel):
    response: str
    # Everything the client renders from except `response` itself has a default,
    # and is read with .get below. A pipeline path that sets no sources is a
    # response with no citations; it is not a 500, and it is not a client that
    # cannot find a field it renders. `response` stays required — a response
    # with no text is not a response to degrade to.
    sources: list = []
    query_type: str
    processing_time_ms: int
    voice_mode: str
    rate_limit_remaining: int
    validator_result: str = ""
    validator_issues: list = []
    model: str = ""            # provider/model that produced the text, "" if deterministic
    # Which service answered: "openai", "local", "local-fallback", … "" if deterministic.
    provider: str = ""
    # On a local fallback, the model the medic asked for ("anthropic/claude-opus-5").
    fallback_from: str = ""
    source: str = ""           # "jts" | "general"
    # What the system believes about the patient, returned on EVERY response so
    # the client can render it. S-1 was stale context nobody could see; the fix
    # is not only clearing it at a boundary but showing it the rest of the time.
    patient_context: dict = {}
    vitals_cautions: list = []
    # Answer first. At most three lines projected from `response` — never new
    # content, see brief.py — and the section names the client must not fold.
    brief: str = ""
    critical_sections: list = []
    # C1: the id of this answer (on its log line too) and the pipeline's own
    # source_mode, both sent back with a feedback report about it.
    query_id: str = ""
    source_mode: str = ""

class FeedbackRequest(BaseModel):
    query: str = Field(..., max_length=MAX_QUERY_CHARS)
    response: str = Field(..., max_length=MAX_RESPONSE_CHARS)
    feedback_type: str = Field(..., max_length=32)   # "appropriate" | "flagged" (legacy: positive/negative)
    severity: str = Field("", max_length=32)         # "" | "minor" | "significant" | "dangerous"
    # Typed as strings, not a bare list: the client posts its fixed tag set,
    # and an untyped list was a place to put arbitrary nested JSON.
    issues: List[Annotated[str, StringConstraints(max_length=MAX_ISSUE_CHARS)]] = \
        Field(default_factory=list, max_length=MAX_FEEDBACK_ISSUES)
    suggestion: str = Field("", max_length=MAX_FEEDBACK_TEXT)  # what it should have said
    comment: str = Field("", max_length=MAX_FEEDBACK_TEXT)
    device_id: str = Field("web", max_length=200)
    # C1 (feedback review §0, §7): enough to reproduce the answer reported on.
    # All optional, so a client that sends none of them is still accepted.
    session_id: str = Field("", max_length=MAX_ID_CHARS)
    query_id: str = Field("", max_length=MAX_ID_CHARS)
    conversation_history: list = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)
    model: str = Field("", max_length=128)
    provider: str = Field("", max_length=MAX_ID_CHARS)
    validator_result: str = Field("", max_length=MAX_ID_CHARS)
    source_mode: str = Field("", max_length=MAX_ID_CHARS)

    @field_validator("conversation_history")
    @classmethod
    def _history_within_budget(cls, v):
        """The same byte bound /query applies (MAX_HISTORY_BYTES)."""
        if len(json.dumps(v, default=str)) > MAX_HISTORY_BYTES:
            raise ValueError(
                f"conversation_history exceeds {MAX_HISTORY_BYTES} bytes")
        return v

from pathlib import Path as _Path
_WEB_CLIENT = _Path(__file__).parent / "static" / "index.html"

async def _status_payload():
    # provider_status() makes a real authenticated call per provider (cached for
    # five minutes), so it goes off the event loop. /status is polled once a
    # minute by every open client.
    import asyncio
    provider_detail = await asyncio.to_thread(providers.provider_status)
    models = await asyncio.to_thread(providers.available_models)
    return {"message": "CDSS Cloud API", "status": "running", "version": __version__,
            "voice_support": tts.voice_available(),
            "voice_detail": tts.config_problem() or "",
            "provider_detail": provider_detail,
            "models": models,
            "default_model": providers.default_model()}

@app.get("/")
async def root():
    if _WEB_CLIENT.exists():
        return FileResponse(_WEB_CLIENT)
    return await _status_payload()

@app.get("/status")
async def status():
    return await _status_payload()

# The flag panel's issue tags (owner, 2026-10-05). A data file, so changing the
# list is one line there and one in tests/test_issue_tags.py. Read per request:
# it is a few hundred bytes, and an edited file needs no restart. Ungated like
# /models: a fixed list, nothing about any patient or report.
_ISSUE_TAGS_FILE = _Path(__file__).parent / "issue_tags.json"


@app.get("/issue_tags")
async def issue_tags():
    return {"tags": json.loads(_ISSUE_TAGS_FILE.read_text(encoding="utf-8"))["tags"]}


@app.get("/models")
async def models():
    """The dropdown's contents: models whose provider actually authenticates.

    `provider_detail` names why an absent provider is absent — key unset, the
    wrong provider's key pasted in, or a real auth failure. Same self-diagnosing
    contract as voice_detail, and for the same reason: a menu entry that is
    silently missing costs an operator hours.
    """
    import asyncio
    return {"models": await asyncio.to_thread(providers.available_models),
            "default_model": providers.default_model(),
            "validator_model": providers.validator_model(),
            "provider_detail": await asyncio.to_thread(providers.provider_status)}

@app.get("/health")
async def health_check():
    try:
        return {"status": "healthy", "documents": chromadb_client.get_collection_count(),
                "voice_support": tts.voice_available()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _query_response(result: dict, request: "QueryRequest", ms: int) -> "QueryResponse":
    """The one shape /query answers with, as JSON or as D4's final event."""
    return QueryResponse(
        response=result["response"],
        sources=result.get("sources") or [],
        query_type="chromadb",
        processing_time_ms=ms,
        voice_mode=request.voice_mode,
        rate_limit_remaining=999,
        validator_result=result.get("validator_result", ""),
        validator_issues=result.get("validator_issues", []),
        model=result.get("model") or "",
        provider=result.get("provider") or "",
        fallback_from=result.get("fallback_from") or "",
        source=result.get("source", ""),
        patient_context=result.get("patient_context") or {},
        vitals_cautions=result.get("vitals_cautions", []),
        brief=result.get("brief") or "",
        critical_sections=result.get("critical_sections") or [],
        query_id=result.get("query_id") or "",
        source_mode=result.get("source_mode") or ""
    )


def _sse_event(name: str, payload: dict) -> str:
    """One server-sent event. json.dumps keeps every newline inside the data."""
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


def _wants_event_stream(http_request: Request) -> bool:
    return "text/event-stream" in (http_request.headers.get("accept") or "")


@app.post("/query", response_model=QueryResponse,
          dependencies=[Depends(require_token)])
async def query_endpoint(request: QueryRequest, http_request: Request):
    start = datetime.now()
    # T-2: self-declared test-suite traffic. Log hygiene only — run_tests.sh
    # fires at the live endpoint by design, and nothing may branch on this.
    synthetic = http_request.headers.get("X-Test-Run", "") == "1"
    kwargs = dict(voice_mode=(request.voice_mode == "brief"),
                  conversation_history=request.conversation_history,
                  synthetic=synthetic, model=request.model or None,
                  input_mode=request.input_mode,
                  session_id=request.session_id)

    # D4 (owner, 2026-10-08): one request, two events, for a client that asks
    # for text/event-stream. "early" carries the header and the patient strip,
    # sent as the pipeline is about to call the model (a deterministic card
    # has no early event: its whole answer is already code-built); "final"
    # carries the whole response, after every check. No model text, partial or
    # whole, and no dose is ever in "early". Any other client gets JSON, as
    # before (run_tests.sh, the cdss-eval harness, older clients).
    if _wants_event_stream(http_request):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_early(payload: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ("early", payload))

        async def run() -> None:
            try:
                result = await asyncio.to_thread(
                    query_with_rag, request.query, chromadb_client, on_early=on_early, **kwargs)
                ms = int((datetime.now() - start).total_seconds() * 1000)
                await queue.put(("final", _query_response(result, request, ms).model_dump()))
            except Exception as e:
                await queue.put(("error", {"detail": str(e)}))

        async def stream():
            task = asyncio.create_task(run())
            try:
                while True:
                    name, payload = await queue.get()
                    yield _sse_event(name, payload)
                    if name in ("final", "error"):
                        break
            finally:
                await task

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    try:
        # AE-4. query_with_rag is synchronous and does retrieval, regex
        # extraction and up to two model calls. Awaited inline it owned the
        # only event loop for its whole duration — and /health is answered by
        # that same loop, so a slow query was indistinguishable from a dead
        # server to edgecdss-watchdog.sh, which restarts at three misses and
        # REBOOTS at six. Offloaded exactly as /status already offloads
        # provider_status() above, and for the same reason.
        result = await asyncio.to_thread(query_with_rag, request.query, chromadb_client, **kwargs)
        ms = int((datetime.now() - start).total_seconds() * 1000)
        return _query_response(result, request, ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# AE-1. The other three endpoints have carried the token gate since the token
# existed; this one was simply missed. Without it every field below was an
# anonymous, uncapped, append-only write to the root filesystem, reachable
# from the public internet. The web client was already sending the header.
@app.post("/feedback", dependencies=[Depends(require_token)])
async def feedback_endpoint(feedback: FeedbackRequest, http_request: Request):
    entry = {"timestamp": datetime.now().isoformat(), "ip": http_request.client.host, "device_id": feedback.device_id, "feedback_type": feedback.feedback_type, "query": feedback.query, "response_preview": feedback.response[:200], "severity": feedback.severity, "issues": feedback.issues, "suggestion": feedback.suggestion, "comment": feedback.comment,
             # C1: the whole answer (capped at MAX_RESPONSE_CHARS by the
             # schema) and what produced it. response_preview stays for the
             # tooling that reads it.
             "response": feedback.response, "session_id": feedback.session_id,
             "query_id": feedback.query_id, "conversation_history": feedback.conversation_history,
             "model": feedback.model, "provider": feedback.provider,
             "validator_result": feedback.validator_result, "source_mode": feedback.source_mode}
    with open(FEEDBACK_LOG, "a") as f:
        # json.dumps, not str(). A dict repr passes a newline inside the
        # caller's own text straight through, so one request could forge as
        # many feedback records as it had newlines. One request, one line.
        f.write(json.dumps(entry) + "\n")
    return {"status": "received"}

# AE-3. What a token holder may read back. `ip` is deliberately absent: it is
# recorded for abuse triage and read from the file by an operator on the box,
# not served to whoever holds a token that is published by design. The free
# text is capped because a summary is a summary — `query` is exactly where a
# medic types patient detail.
_SUMMARY_PASSTHROUGH = ("timestamp", "device_id", "feedback_type", "severity",
                        "issues",
                        # C1: what produced the answer. Not the history: that
                        # is where patient detail lives, like `query`.
                        "session_id", "query_id", "model", "provider",
                        "validator_result", "source_mode")
_SUMMARY_TRUNCATED = ("query", "response_preview", "suggestion", "comment")
SUMMARY_MAX_ENTRIES = 20
SUMMARY_TEXT_CHARS = 200


def summarise_feedback_line(line: str) -> Optional[dict]:
    """One stored record projected down to what a token holder may read.

    Returns None for anything that does not parse as a JSON object, which
    includes every record written before this patch: those were dict reprs,
    and a line that cannot be parsed cannot be field-filtered either. An
    unreadable record is dropped rather than passed through unfiltered.
    """
    try:
        rec = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(rec, dict):
        return None
    out = {k: rec.get(k) for k in _SUMMARY_PASSTHROUGH}
    for k in _SUMMARY_TRUNCATED:
        v = rec.get(k)
        out[k] = "" if v is None else str(v)[:SUMMARY_TEXT_CHARS]
    return out


@app.get("/feedback/summary", dependencies=[Depends(require_token)])
async def feedback_summary():
    total = 0
    # A bounded tail. readlines() pulled a file an anonymous caller could
    # grow without limit entirely into memory — its own denial of service.
    recent = deque(maxlen=SUMMARY_MAX_ENTRIES)
    try:
        with open(FEEDBACK_LOG, encoding="utf-8", errors="replace") as f:
            for line in f:
                total += 1
                recent.append(line)
    except FileNotFoundError:
        return {"total_feedback": 0, "entries": []}
    entries = [e for e in (summarise_feedback_line(l) for l in recent)
               if e is not None]
    return {"total_feedback": total, "entries": entries}

@app.post("/speak", dependencies=[Depends(require_token)])
async def speak_endpoint(http_request: Request):
    try:
        body = await http_request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body must be JSON")
    # Brief first, in the ear as on the screen: when the caller sends the
    # brief, the brief is what is spoken — nothing else, whatever `text` holds.
    # Decided here rather than trusted to the client, for the same reason the
    # disclosure below is. There is no separate "actions" voice mode yet; this
    # is the default mode, and a caller with no brief is spoken as before.
    spoken = body.get("brief") or body.get("text", "")
    # The spoken disclosure is applied server-side, not by the client. A client
    # that forgot it would produce a spoken answer with no indication it did not
    # come from JTS — the one thing general reference is not allowed to do.
    text = general_reference.for_speech(spoken, body.get("source", ""))
    try:
        audio = await tts.synthesize(tts.normalize_for_speech(text))
    except tts.VoiceUnavailable as e:
        # Say why, in the log and to the caller. The generic 500 this replaces
        # is what let a pasted key ID sit unnoticed behind a dead button.
        print(f"⚠️  /speak {e.status}: {e.detail}")
        raise HTTPException(status_code=e.status, detail=e.detail)
    return Response(content=audio, media_type="audio/mpeg")
