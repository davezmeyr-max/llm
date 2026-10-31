"""Shared process state and helpers used by both the token API and the web portal."""

from __future__ import annotations

import csv
import io

import httpx

from .config import settings
from .db import LeadStore

store = LeadStore(settings.db_path)

EXPORT_HEADER = [
    "id", "batch", "input_name", "input_hints", "company_name", "website", "industry", "employee_estimate",
    "business_address", "business_phone", "email_provider", "registration_status", "registration",
    "registered_agent", "people", "confidence", "summary", "open_questions", "sources", "submitted_by",
    "finished_at",
]


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


def export_rows(batch: str | None = None) -> list[list[str]]:
    """Finished leads only, one row per lead, oldest first."""
    rows = []
    for row in reversed(store.list("done", 100000, batch=batch or None)):
        p = row.get("profile") or {}
        regs = p.get("registrations") or []
        regs_txt = "; ".join(
            " ".join(x for x in (r.get("jurisdiction"), r.get("entity_number"), r.get("entity_type")) if x)
            for r in regs
        )
        people = "; ".join(f"{x.get('name')} ({x.get('role')})" for x in p.get("people", []))
        rows.append(
            [
                row["id"], row.get("batch", ""), row["company"], row.get("hints", ""), p.get("company_name") or "",
                p.get("website") or "", p.get("industry") or "", p.get("employee_estimate") or "",
                p.get("business_address") or "", p.get("business_phone") or "",
                (p.get("it_signals") or {}).get("email_provider") or "",
                regs[0].get("status") or "" if regs else "", regs_txt,
                regs[0].get("registered_agent") or "" if regs else "", people, p.get("confidence") or "",
                p.get("summary") or "", " | ".join(p.get("open_questions", [])), " ".join(p.get("sources", [])),
                row.get("submitted_by", ""), row.get("finished_at") or "",
            ]
        )
    return rows


def _safe(v):
    """Neutralise spreadsheet formula injection: scraped text could start with = + - @."""
    return f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def build_csv(batch: str | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_HEADER)
    w.writerows([[_safe(v) for v in r] for r in export_rows(batch)])
    return buf.getvalue()


def build_xlsx(batch: str | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append(EXPORT_HEADER)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in export_rows(batch):
        ws.append([_safe(v) for v in r])
    ws.freeze_panes = "A2"
    widths = {"summary": 60, "people": 45, "sources": 50, "registration": 30, "open_questions": 40}
    for i, name in enumerate(EXPORT_HEADER, start=1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(name, 18)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
