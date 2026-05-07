cat > ~/cdss-cloud/app/main.py << 'EOF'
#!/usr/bin/env python3
"""
CDSS Cloud API Server
Version: 2.5.0
- Rate limiting disabled — server on/off controlled manually
- CORS for GitHub Pages
- Feedback endpoint
- Access token authentication
- Server-side ElevenLabs TTS
- Conversation history support
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from datetime import datetime
import os
import time
import httpx
from collections import defaultdict
from dotenv import load_dotenv
from embeddings import ChromaDBClient
from openai_client import query_with_rag

load_dotenv()

app = FastAPI(title="CDSS Cloud API", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    chromadb_client = ChromaDBClient()
    print("✅ ChromaDB and OpenAI clients initialized")
except Exception as e:
    print(f"❌ Error initializing clients: {e}")
    raise

# Rate limiting disabled — server on/off controlled manually
def check_rate_limit(ip: str) -> dict:
    return {"allowed": True, "count": 0, "remaining": 999, "reset_seconds": None}

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
        doc_count = chromadb_client.get_collection_count()
        return {"status": "healthy", "chromadb": "connected", "openai": "connected", "documents": doc_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest, http_request: Request):
    token = http_request.headers.get("X-Access-Token", "")
    if token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")

    ip = http_request.client.host
    rate = check_rate_limit(ip)

    start_time = datetime.now()
    try:
        response_data = query_with_rag(
            request.query,
            chromadb_client,
            voice_mode=(request.voice_mode == "brief"),
            conversation_history=request.conversation_history
        )
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        return QueryResponse(
            response=response_data["response"],
            sources=response_data["sources"],
            query_type="chromadb",
            processing_time_ms=processing_time,
            voice_mode=request.voice_mode,
            rate_limit_remaining=999
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def feedback_endpoint(feedback: FeedbackRequest, http_request: Request):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "ip": http_request.client.host,
        "device_id": feedback.device_id,
        "feedback_type": feedback.feedback_type,
        "query": feedback.query,
        "response_preview": feedback.response[:200],
        "comment": feedback.comment
    }
    with open("/home/akaclinicalco/cdss-cloud/feedback.log", "a") as f:
        f.write(str(log_entry) + "\n")
    return {"status": "received", "message": "Feedback recorded. Thank you."}

@app.get("/feedback/summary")
async def feedback_summary(http_request: Request):
    token = http_request.headers.get("X-Access-Token", "")
    if token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        with open("/home/akaclinicalco/cdss-cloud/feedback.log", "r") as f:
            lines = f.readlines()
        return {"total_feedback": len(lines), "entries": lines[-20:]}
    except FileNotFoundError:
        return {"total_feedback": 0, "entries": []}

@app.post("/speak")
async def speak_endpoint(http_request: Request):
    token = http_request.headers.get("X-Access-Token", "")
    if token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")

    body = await http_request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 0.85}
            },
            timeout=30
        )

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="ElevenLabs error")

    return Response(content=response.content, media_type="audio/mpeg")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
EOF