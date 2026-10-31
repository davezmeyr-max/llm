"""HTTP API: token-authenticated JSON endpoints plus the browser portal (see web.py)."""

from __future__ import annotations

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import __version__
from .chat import router as chat_router
from .config import settings
from .state import build_csv, llm_online, store
from .web import router as web_router

# No /docs, /redoc or /openapi.json: the API can be published on the internet behind Caddy.
app = FastAPI(title="LeadScout", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(web_router)
app.include_router(chat_router)


def require_token(authorization: str = Header(default="")) -> None:
    if not settings.api_token:
        raise HTTPException(503, "API_TOKEN is not set on the server")
    expected = f"Bearer {settings.api_token}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401, "invalid token")


class LeadIn(BaseModel):
    company: str = Field(min_length=2, max_length=200)
    hints: str = Field("", max_length=500, description="City/state, website, industry, anything that disambiguates")


class BulkIn(BaseModel):
    leads: list[LeadIn] = Field(min_length=1, max_length=500)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/status", dependencies=[Depends(require_token)])
def status() -> dict:
    return {"queue": store.counts(), "llm_online": llm_online()}


@app.post("/leads", dependencies=[Depends(require_token)], status_code=201)
def add_lead(lead: LeadIn) -> dict:
    return {"id": store.add(lead.company, lead.hints)}


@app.post("/leads/bulk", dependencies=[Depends(require_token)], status_code=201)
def add_bulk(body: BulkIn) -> dict:
    return {"ids": [store.add(lead.company, lead.hints) for lead in body.leads]}


@app.get("/leads", dependencies=[Depends(require_token)])
def list_leads(status: str | None = Query(None, pattern="^(queued|running|done|failed)$"), limit: int = 100) -> list[dict]:
    rows = store.list(status, min(max(limit, 1), 1000))
    for r in rows:
        r.pop("trace", None)
    return rows


@app.get("/leads/{lead_id}", dependencies=[Depends(require_token)])
def get_lead(lead_id: int) -> dict:
    row = store.get(lead_id)
    if not row:
        raise HTTPException(404, "not found")
    return row


@app.post("/leads/{lead_id}/retry", dependencies=[Depends(require_token)])
def retry_lead(lead_id: int) -> dict:
    if not store.retry(lead_id):
        raise HTTPException(409, "lead is not in a retryable state")
    return {"id": lead_id, "status": "queued"}


@app.get("/export.csv", dependencies=[Depends(require_token)], response_class=PlainTextResponse)
def export_csv(batch: str | None = None) -> str:
    """Finished leads only; optionally one import batch."""
    return build_csv(batch)
