from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel
from datetime import datetime
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

class QueryRequest(BaseModel):
    query: str
    device_id: str
    timestamp: str
    voice_mode: str = "brief"
    conversation_history: list = []
    model: str = ""            # "" = server default; unknown values fall back to it

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
    query: str
    response: str
    feedback_type: str          # "appropriate" | "flagged" (legacy: positive/negative)
    severity: str = ""          # "" | "minor" | "significant" | "dangerous"
    issues: list = []           # structured issue tags
    suggestion: str = ""        # what it should have said
    comment: str = ""
    device_id: str = "web"

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
        result = query_with_rag(request.query, chromadb_client, voice_mode=(request.voice_mode == "brief"), conversation_history=request.conversation_history, synthetic=synthetic, model=request.model or None)
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
    entry = {"timestamp": datetime.now().isoformat(), "ip": http_request.client.host, "device_id": feedback.device_id, "feedback_type": feedback.feedback_type, "query": feedback.query, "response_preview": feedback.response[:200], "severity": feedback.severity, "issues": feedback.issues, "suggestion": feedback.suggestion, "comment": feedback.comment}
    with open(FEEDBACK_LOG, "a") as f:
        f.write(str(entry) + "\n")
    return {"status": "received"}

@app.get("/feedback/summary")
async def feedback_summary(http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        lines = open(FEEDBACK_LOG).readlines()
        return {"total_feedback": len(lines), "entries": lines[-20:]}
    except FileNotFoundError:
        return {"total_feedback": 0, "entries": []}

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
