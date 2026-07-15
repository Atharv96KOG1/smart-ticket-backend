from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from smart_ticket_router.config import ROUTE_RATE_LIMIT
from smart_ticket_router.core.guardrails import BlankTicketError
from smart_ticket_router.core.router import route_ticket
from smart_ticket_router.llm.exceptions import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
)
from smart_ticket_router.schemas.requests import RouteRequest
from smart_ticket_router.schemas.ticket import TicketRoute

router = APIRouter()

# Standalone limiter bound to the router decorator; shares the same
# per-IP key function as the one registered on app.state in main.py.
limiter = Limiter(key_func=get_remote_address)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/route", response_model=TicketRoute)
@limiter.limit(ROUTE_RATE_LIMIT)
def route(request: Request, payload: RouteRequest) -> TicketRoute:
    try:
        return route_ticket(payload.message)
    except BlankTicketError:
        raise HTTPException(status_code=400, detail="Ticket message must not be blank.")
    except LLMAuthError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except LLMRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except LLMConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
