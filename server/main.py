from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
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
from openai_client import query_with_rag
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

class QueryRequest(BaseModel):
    query: str = Field(..., max_length=MAX_QUERY_CHARS)
    device_id: str = Field(..., max_length=200)
    timestamp: str = Field(..., max_length=64)
    voice_mode: str = Field("brief", max_length=32)
    conversation_history: list = Field(default_factory=list,
                                       max_length=MAX_HISTORY_TURNS)
    model: str = Field("", max_length=128)  # "" = server default; unknown values fall back to it

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
    source: str = ""           # "jts" | "general"
    # What the system believes about the patient, returned on EVERY response so
    # the client can render it. S-1 was stale context nobody could see; the fix
    # is not only clearing it at a boundary but showing it the rest of the time.
    patient_context: dict = {}
    vitals_cautions: list = []

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

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest, http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")
    start = datetime.now()
    # T-2: self-declared test-suite traffic. Log hygiene only — run_tests.sh
    # fires at the live endpoint by design, and nothing may branch on this.
    synthetic = http_request.headers.get("X-Test-Run", "") == "1"
    try:
        # AE-4. query_with_rag is synchronous and does retrieval, regex
        # extraction and up to two model calls. Awaited inline it owned the
        # only event loop for its whole duration — and /health is answered by
        # that same loop, so a slow query was indistinguishable from a dead
        # server to edgecdss-watchdog.sh, which restarts at three misses and
        # REBOOTS at six. Offloaded exactly as /status already offloads
        # provider_status() above, and for the same reason.
        result = await asyncio.to_thread(
            query_with_rag, request.query, chromadb_client,
            voice_mode=(request.voice_mode == "brief"),
            conversation_history=request.conversation_history,
            synthetic=synthetic, model=request.model or None)
        ms = int((datetime.now() - start).total_seconds() * 1000)
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
            source=result.get("source", ""),
            patient_context=result.get("patient_context") or {},
            vitals_cautions=result.get("vitals_cautions", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def feedback_endpoint(feedback: FeedbackRequest, http_request: Request):
    # AE-1. The other three endpoints have carried this check since the token
    # existed; this one was simply missed. Without it every field below was an
    # anonymous, uncapped, append-only write to the root filesystem, reachable
    # from the public internet.
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")
    entry = {"timestamp": datetime.now().isoformat(), "ip": http_request.client.host, "device_id": feedback.device_id, "feedback_type": feedback.feedback_type, "query": feedback.query, "response_preview": feedback.response[:200], "severity": feedback.severity, "issues": feedback.issues, "suggestion": feedback.suggestion, "comment": feedback.comment}
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
                        "issues")
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


@app.get("/feedback/summary")
async def feedback_summary(http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
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

@app.post("/speak")
async def speak_endpoint(http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")
    try:
        body = await http_request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body must be JSON")
    # The spoken disclosure is applied server-side, not by the client. A client
    # that forgot it would produce a spoken answer with no indication it did not
    # come from JTS — the one thing general reference is not allowed to do.
    text = general_reference.for_speech(body.get("text", ""), body.get("source", ""))
    try:
        audio = await tts.synthesize(tts.normalize_for_speech(text))
    except tts.VoiceUnavailable as e:
        # Say why, in the log and to the caller. The generic 500 this replaces
        # is what let a pasted key ID sit unnoticed behind a dead button.
        print(f"⚠️  /speak {e.status}: {e.detail}")
        raise HTTPException(status_code=e.status, detail=e.detail)
    return Response(content=audio, media_type="audio/mpeg")
