from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from datetime import datetime
import os, httpx
from dotenv import load_dotenv
from embeddings import ChromaDBClient
from openai_client import query_with_rag

load_dotenv()
app = FastAPI(title="CDSS Cloud API", version="2.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

try:
    chromadb_client = ChromaDBClient()
    print("✅ ChromaDB and OpenAI clients initialized")
except Exception as e:
    print(f"❌ Error: {e}")
    raise

ACCESS_TOKEN = os.getenv("CDSS_ACCESS_TOKEN", "edgecdss-demo-2026")

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

class FeedbackRequest(BaseModel):
    query: str
    response: str
    feedback_type: str
    comment: str = ""
    device_id: str = "web"

@app.get("/")
async def root():
    return {"message": "CDSS Cloud API", "status": "running", "version": "2.5.0", "voice_support": True}

@app.get("/health")
async def health_check():
    try:
        return {"status": "healthy", "documents": chromadb_client.get_collection_count()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest, http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")
    start = datetime.now()
    try:
        result = query_with_rag(request.query, chromadb_client, voice_mode=(request.voice_mode == "brief"), conversation_history=request.conversation_history)
        ms = int((datetime.now() - start).total_seconds() * 1000)
        return QueryResponse(response=result["response"], sources=result["sources"], query_type="chromadb", processing_time_ms=ms, voice_mode=request.voice_mode, rate_limit_remaining=999)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def feedback_endpoint(feedback: FeedbackRequest, http_request: Request):
    entry = {"timestamp": datetime.now().isoformat(), "ip": http_request.client.host, "device_id": feedback.device_id, "feedback_type": feedback.feedback_type, "query": feedback.query, "response_preview": feedback.response[:200], "comment": feedback.comment}
    with open("/home/akaclinicalco/cdss-cloud/feedback.log", "a") as f:
        f.write(str(entry) + "\n")
    return {"status": "received"}

@app.get("/feedback/summary")
async def feedback_summary(http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        lines = open("/home/akaclinicalco/cdss-cloud/feedback.log").readlines()
        return {"total_feedback": len(lines), "entries": lines[-20:]}
    except FileNotFoundError:
        return {"total_feedback": 0, "entries": []}

@app.post("/speak")
async def speak_endpoint(http_request: Request):
    if http_request.headers.get("X-Access-Token", "") != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")
    body = await http_request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb",
            headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY"), "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 0.85}},
            timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="ElevenLabs error")
    return Response(content=r.content, media_type="audio/mpeg")
