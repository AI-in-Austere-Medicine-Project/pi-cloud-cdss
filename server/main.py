#!/usr/bin/env python3
"""
CDSS Cloud API Server
Version: 2.0.0
- Rate limiting: 10 queries per IP per 24hrs
- CORS for GitHub Pages
- Feedback/flag endpoint
- Access token authentication
"""

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import time
from collections import defaultdict
from dotenv import load_dotenv
from embeddings import ChromaDBClient
from openai_client import query_with_rag

load_dotenv()

app = FastAPI(title="CDSS Cloud API", version="2.0.0")

# CORS — allow GitHub Pages and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ai-in-austere-medicine-project.github.io",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ChromaDB
try:
    chromadb_client = ChromaDBClient()
    print("✅ ChromaDB and OpenAI clients initialized")
except Exception as e:
    print(f"❌ Error initializing clients: {e}")
    raise

# ─────────────────────────────────────────
# Rate limiting — 10 queries per IP per 24hrs
# ─────────────────────────────────────────
RATE_LIMIT = 10
RATE_WINDOW = 86400  # 24 hours in seconds

rate_store = defaultdict(list)  # {ip: [timestamps]}

def check_rate_limit(ip: str) -> dict:
    now = time.time()
    cutoff = now - RATE_WINDOW
    # Clean old entries
    rate_store[ip] = [t for t in rate_store[ip] if t > cutoff]
    count = len(rate_store[ip])
    remaining = RATE_LIMIT - count
    reset_time = None
    if rate_store[ip]:
        reset_time = int(rate_store[ip][0] + RATE_WINDOW - now)
    return {
        "allowed": count < RATE_LIMIT,
        "count": count,
        "remaining": remaining,
        "reset_seconds": reset_time
    }

# ─────────────────────────────────────────
# Access token check
# ─────────────────────────────────────────
ACCESS_TOKEN = os.getenv("CDSS_ACCESS_TOKEN", "edgecdss-demo-2026")

def verify_token(request: Request):
    token = request.headers.get("X-Access-Token", "")
    if token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")

# ─────────────────────────────────────────
# Models
# ─────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    device_id: str
    timestamp: str
    voice_mode: str = "brief"

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
    feedback_type: str  # "helpful", "incorrect", "dangerous", "unclear", "other"
    comment: str = ""
    device_id: str = "web"

# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "message": "CDSS Cloud API",
        "status": "running",
        "version": "2.0.0",
        "voice_support": True
    }

@app.get("/health")
async def health_check():
    try:
        doc_count = chromadb_client.get_collection_count()
        return {
            "status": "healthy",
            "chromadb": "connected",
            "openai": "connected",
            "documents": doc_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest, http_request: Request):
    """Main query endpoint with rate limiting and token auth"""

    # Token check
    token = http_request.headers.get("X-Access-Token", "")
    if token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid access token")

    # Rate limit check
    ip = http_request.client.host
    rate = check_rate_limit(ip)
    if not rate["allowed"]:
        hours = round(rate["reset_seconds"] / 3600, 1)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached. 10 queries per 24 hours. Resets in {hours} hours."
        )

    # Record this request
    rate_store[ip].append(time.time())

    start_time = datetime.now()
    try:
        response_data = query_with_rag(
            request.query,
            chromadb_client,
            voice_mode=(request.voice_mode == "brief")
        )
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        return QueryResponse(
            response=response_data["response"],
            sources=response_data["sources"],
            query_type="chromadb",
            processing_time_ms=processing_time,
            voice_mode=request.voice_mode,
            rate_limit_remaining=rate["remaining"] - 1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def feedback_endpoint(feedback: FeedbackRequest, http_request: Request):
    """Collect user feedback on responses"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "ip": http_request.client.host,
        "device_id": feedback.device_id,
        "feedback_type": feedback.feedback_type,
        "query": feedback.query,
        "response_preview": feedback.response[:200],
        "comment": feedback.comment
    }
    # Append to feedback log
    with open("/home/akaclinicalco/cdss-cloud/feedback.log", "a") as f:
        f.write(str(log_entry) + "\n")

    return {"status": "received", "message": "Feedback recorded. Thank you."}

@app.get("/feedback/summary")
async def feedback_summary(http_request: Request):
    """View feedback summary — token protected"""
    token = http_request.headers.get("X-Access-Token", "")
    if token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        with open("/home/akaclinicalco/cdss-cloud/feedback.log", "r") as f:
            lines = f.readlines()
        return {"total_feedback": len(lines), "entries": lines[-20:]}
    except FileNotFoundError:
        return {"total_feedback": 0, "entries": []}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)