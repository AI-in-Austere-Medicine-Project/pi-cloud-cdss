from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel
from datetime import datetime
import os
from dotenv import load_dotenv
from embeddings import ChromaDBClient
from openai_client import query_with_rag
import tts

load_dotenv()
app = FastAPI(title="CDSS Cloud API", version="4.1.0")
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

class QueryResponse(BaseModel):
    response: str
    sources: list
    query_type: str
    processing_time_ms: int
    voice_mode: str
    rate_limit_remaining: int
    validator_result: str = ""
    validator_issues: list = []

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

@app.get("/")
async def root():
    if _WEB_CLIENT.exists():
        return FileResponse(_WEB_CLIENT)
    return {"message": "CDSS Cloud API", "status": "running", "version": "4.1.0", "voice_support": tts.voice_available(), "voice_detail": tts.config_problem() or ""}

@app.get("/status")
async def status():
    return {"message": "CDSS Cloud API", "status": "running", "version": "4.1.0", "voice_support": tts.voice_available(), "voice_detail": tts.config_problem() or ""}

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
        result = query_with_rag(request.query, chromadb_client, voice_mode=(request.voice_mode == "brief"), conversation_history=request.conversation_history, synthetic=synthetic)
        ms = int((datetime.now() - start).total_seconds() * 1000)
        return QueryResponse(
            response=result["response"],
            sources=result["sources"],
            query_type="chromadb",
            processing_time_ms=ms,
            voice_mode=request.voice_mode,
            rate_limit_remaining=999,
            validator_result=result.get("validator_result", ""),
            validator_issues=result.get("validator_issues", [])
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
    try:
        audio = await tts.synthesize(tts.normalize_for_speech(body.get("text", "")))
    except tts.VoiceUnavailable as e:
        # Say why, in the log and to the caller. The generic 500 this replaces
        # is what let a pasted key ID sit unnoticed behind a dead button.
        print(f"⚠️  /speak {e.status}: {e.detail}")
        raise HTTPException(status_code=e.status, detail=e.detail)
    return Response(content=audio, media_type="audio/mpeg")
