from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    message: str = Field(min_length=0, max_length=8000)
