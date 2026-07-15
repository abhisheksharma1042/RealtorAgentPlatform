"""
DFW Realtor Agent Platform - Backend API
FastAPI application with AI agent integration
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv

# Import routers
import sys
from pathlib import Path

# Add backend directory + repo root to Python path so imports work both
# as `agent.foo` (legacy) and `backend.agent.foo` (new ingestion code).
backend_dir = Path(__file__).parent
repo_root = backend_dir.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(backend_dir))

from api.chat import router as chat_router

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="DFW Realtor Agent API",
    description="AI-powered real estate research platform for Dallas-Fort Worth",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative frontend port
        "https://*.vercel.app",   # Vercel deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "DFW Realtor Agent API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "supabase_url_set": bool(os.getenv("SUPABASE_URL")),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
