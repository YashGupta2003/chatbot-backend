"""
main.py - FastAPI Application Entry Point
==========================================
This is the root of the FastAPI application.
It sets up the app, registers middleware (CORS),
and includes all the API routes.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routes import router
from app.utils.memory import conversation_store
import logging

# ─────────────────────────────────────────────
# Configure logging for the entire application
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Lifespan context manager (startup / shutdown)
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code inside the 'try' block runs on startup.
    Code after 'yield' runs on shutdown.
    Use this to initialise / clean up resources (DB connections, caches, etc.)
    """
    logger.info("🚀 Chatbot backend is starting up...")
    yield
    logger.info("🛑 Chatbot backend is shutting down. Clearing conversation memory...")
    conversation_store.clear()


# ─────────────────────────────────────────────
# Create the FastAPI application instance
# ─────────────────────────────────────────────
app = FastAPI(
    title="Real-Time AI Chatbot API",
    description=(
        "A production-ready streaming chatbot backend powered by "
        "FastAPI + Groq (LLaMA 3). Supports multi-turn conversations "
        "with in-memory session management."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# CORS Middleware
# Allows frontend apps (React, Vue, plain HTML)
# running on any origin to call this API.
# Tighten 'allow_origins' in production!
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Replace with specific domains in production
    allow_credentials=True,
    allow_methods=["*"],          # GET, POST, PUT, DELETE, OPTIONS …
    allow_headers=["*"],          # Authorization, Content-Type …
)


# ─────────────────────────────────────────────
# Register API routes
# All routes are defined in app/routes.py and
# prefixed with /api/v1 for versioning.
# ─────────────────────────────────────────────
app.include_router(router, prefix="/api/v1")


# ─────────────────────────────────────────────
# Root health-check endpoint
# ─────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    """Simple health-check endpoint."""
    return {
        "status": "ok",
        "message": "Real-Time AI Chatbot API is running 🤖",
        "docs": "/docs",
    }
