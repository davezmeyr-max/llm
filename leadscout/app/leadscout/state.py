"""Shared process state and helpers used by both the token API and the web portal."""

from __future__ import annotations

import csv
import io

import httpx

from .config import settings
from .db import LeadStore

store = LeadStore(settings.db_path)


def llm_online() -> bool:
    try:
        r = httpx.get(
            f"{settings.llm_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=5.0,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def build_csv() -> str:
    """Flat export of finished leads, one row per lead, for CRM import."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "input_name", "company_name", "website", "industry", "employee_estimate", "business_address",
         "business_phone", "email_provider", "registration", "people", "confidence", "summary", "sources",
         "submitted_by"]
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
             p.get("summary"), " ".join(p.get("sources", [])), row.get("submitted_by", "")]
        )
    return buf.getvalue()
