from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from smart_ticket_router.api.routes import router
from smart_ticket_router.config import ALLOWED_ORIGINS

# backend/ repo root: src/smart_ticket_router/main.py -> src -> backend
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

app = FastAPI(
    title="Smart Ticket Router",
    description="Reads a raw support message and returns a validated routing decision.",
    version="1.0.0",
)

# Per-IP limit on /route (see ROUTE_RATE_LIMIT) — keeps an open demo endpoint
# from being used to run up OpenAI spend.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# The frontend is a separate app/repo served from its own origin, so it needs CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/data", StaticFiles(directory=REPO_ROOT / "data"), name="data")
