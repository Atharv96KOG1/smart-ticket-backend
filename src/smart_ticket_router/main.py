from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from smart_ticket_router.api.routes import router
from smart_ticket_router.config import ALLOWED_ORIGINS

# backend/ repo root: src/smart_ticket_router/main.py -> src -> backend
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

app = FastAPI(
    title="Smart Ticket Router",
    description="Reads a raw support message and returns a validated routing decision.",
    version="1.0.0",
)

# The frontend is a separate app/repo served from its own origin, so it needs CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/data", StaticFiles(directory=REPO_ROOT / "data"), name="data")
