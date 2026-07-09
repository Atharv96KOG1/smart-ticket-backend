"""FastAPI server. The LLM key is read from the environment here and never sent
to any client — the client only ever sees the validated JSON result.
"""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.guardrails import BlankTicketError
from app.llm import LLMAuthError, LLMConnectionError, LLMRateLimitError
from app.router import route_ticket
from app.schema import TicketRoute

app = FastAPI(
    title="Smart Ticket Router",
    description="Reads a raw support message and returns a validated routing decision.",
    version="1.0.0",
)


class RouteRequest(BaseModel):
    message: str = Field(min_length=0, max_length=8000)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/route", response_model=TicketRoute)
def route(payload: RouteRequest) -> TicketRoute:
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
