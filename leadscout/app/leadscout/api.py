"""Small HTTP API: submit leads, check status, pull results (JSON or CSV)."""

from __future__ import annotations

import csv
import hmac
import io

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .config import settings
from .db import LeadStore

# No /docs, /redoc or /openapi.json: the API can be published on the internet behind Caddy.
app = FastAPI(title="LeadScout", version="0.1.2", docs_url=None, redoc_url=None, openapi_url=None)
store = LeadStore(settings.db_path)


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
    return {"ok": True}


@app.get("/status", dependencies=[Depends(require_token)])
def status() -> dict:
    llm_up = False
    try:
        r = httpx.get(
            f"{settings.llm_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=5.0,
        )
        llm_up = r.status_code == 200
    except httpx.HTTPError:
        pass
    return {"queue": store.counts(), "llm_online": llm_up}


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
def export_csv() -> str:
    """Flat export of finished leads, one row per lead, for CRM import."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "input_name", "company_name", "website", "industry", "employee_estimate", "business_address",
         "business_phone", "email_provider", "registration", "people", "confidence", "summary", "sources"]
    )
    for row in store.list("done", 10000):
        p = row.get("profile") or {}
        regs = "; ".join(
            f"{r.get('jurisdiction')} {r.get('entity_number') or ''} {r.get('status') or ''}".strip()
            for r in p.get("registrations", [])
        )
        people = "; ".join(f"{x.get('name')} ({x.get('role')})" for x in p.get("people", []))
        w.writerow(
            [row["id"], p.get("input_name"), p.get("company_name"), p.get("website"), p.get("industry"),
             p.get("employee_estimate"), p.get("business_address"), p.get("business_phone"),
             (p.get("it_signals") or {}).get("email_provider"), regs, people, p.get("confidence"),
             p.get("summary"), " ".join(p.get("sources", []))]
        )
    return buf.getvalue()
