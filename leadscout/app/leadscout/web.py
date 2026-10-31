"""Browser portal: sign-in handoff from Base44 (or an admin password), session cookie, UI JSON API.

Sign-in handoff (SSO): the Base44 backend, for a user who is already signed in there, builds

    https://<host>/sso?email=<email>&name=<name>&exp=<unix seconds>&sig=<hex>

where sig = HMAC-SHA256(SSO_SECRET, f"{email}|{name}|{exp}") and exp is at most 5 minutes ahead.
Each link works once. The portal then keeps its own signed session cookie.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from . import budget
from .config import settings
from .importer import ImportError_, parse_upload
from .metrics import dashboard
from .state import build_csv, build_xlsx, llm_online, store
from .web_page import LOGIN_PAGE, PORTAL_PAGE

router = APIRouter()

COOKIE = "ls_session"
SSO_MAX_AHEAD_S = 300
LOGIN_WINDOW_S = 900
LOGIN_MAX_FAILURES = 10

_used_sso: dict[str, float] = {}
_login_failures: dict[str, deque] = {}
_lock = threading.Lock()


# ------------------------------------------------------------------ signing helpers


def _hmac_hex(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_session(email: str, name: str) -> str:
    payload = {"e": email, "n": name, "x": int(time.time()) + settings.session_hours * 3600}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{_hmac_hex(settings.session_secret, body)}"


def read_session(cookie: str | None) -> dict[str, Any] | None:
    if not cookie or not settings.session_secret or "." not in cookie:
        return None
    body, sig = cookie.rsplit(".", 1)
    if not hmac.compare_digest(sig, _hmac_hex(settings.session_secret, body)):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("x", 0)) < time.time():
        return None
    return {"email": payload.get("e", ""), "name": payload.get("n", "")}


def verify_sso(email: str, name: str, exp: str, sig: str) -> bool:
    if not settings.sso_secret or not email or "@" not in email:
        return False
    try:
        exp_i = int(exp)
    except ValueError:
        return False
    now = time.time()
    if not (now <= exp_i <= now + SSO_MAX_AHEAD_S):
        return False
    expected = _hmac_hex(settings.sso_secret, f"{email}|{name}|{exp_i}")
    if not hmac.compare_digest(sig.lower(), expected):
        return False
    with _lock:  # single use
        for k, t in list(_used_sso.items()):
            if t < now:
                del _used_sso[k]
        if sig in _used_sso:
            return False
        _used_sso[sig] = exp_i
    return True


def _is_https(request: Request) -> bool:
    # Caddy sets X-Forwarded-Proto; plain-HTTP access (e.g. by IP address) must not get a Secure cookie.
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https"


def _set_session(resp, request: Request, email: str, name: str) -> None:
    resp.set_cookie(
        COOKIE,
        make_session(email, name),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )


def _portal_enabled() -> None:
    if not settings.session_secret:
        raise HTTPException(503, "SESSION_SECRET is not set on the server")


def require_session(request: Request) -> dict[str, Any]:
    _portal_enabled()
    user = read_session(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "sign in required")
    return user


def require_csrf(x_requested_with: str = Header(default="")) -> None:
    # Cross-site forms cannot set custom headers, and we send no CORS headers.
    if x_requested_with != "leadscout":
        raise HTTPException(403, "missing request header")


# ------------------------------------------------------------------ pages


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def portal(request: Request):
    _portal_enabled()
    if not read_session(request.cookies.get(COOKIE)):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(PORTAL_PAGE, headers={"Cache-Control": "no-store"})


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@router.get("/sso", include_in_schema=False)
def sso(request: Request, email: str = "", name: str = "", exp: str = "", sig: str = ""):
    _portal_enabled()
    email = email.strip().lower()
    if not verify_sso(email, name, exp, sig):
        return HTMLResponse(
            "<p>This sign-in link is invalid or expired. Go back to the portal and open Lead Research again.</p>",
            status_code=401,
        )
    resp = RedirectResponse("/", status_code=303)
    _set_session(resp, request, email, name[:80])
    return resp


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page():
    _portal_enabled()
    return HTMLResponse(LOGIN_PAGE, headers={"Cache-Control": "no-store"})


class LoginIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/login", dependencies=[Depends(require_csrf)], include_in_schema=False)
def login(body: LoginIn, request: Request):
    _portal_enabled()
    if not settings.admin_password:
        raise HTTPException(403, "admin password sign-in is disabled")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    with _lock:
        q = _login_failures.setdefault(ip, deque())
        while q and q[0] < now - LOGIN_WINDOW_S:
            q.popleft()
        if len(q) >= LOGIN_MAX_FAILURES:
            raise HTTPException(429, "too many attempts, try again later")
    if not hmac.compare_digest(body.password.encode(), settings.admin_password.encode()):
        with _lock:
            _login_failures[ip].append(now)
        raise HTTPException(401, "wrong password")
    resp = PlainTextResponse("ok")
    _set_session(resp, request, "admin", "Admin")
    return resp


@router.get("/logout", include_in_schema=False)
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


# ------------------------------------------------------------------ UI JSON API (cookie auth)


class UILead(BaseModel):
    company: str = Field(min_length=2, max_length=200)
    hints: str = Field("", max_length=500)


class UIBulk(BaseModel):
    leads: list[UILead] = Field(min_length=1, max_length=500)


@router.get("/ui/api/me", include_in_schema=False)
def me(user: dict = Depends(require_session)) -> dict:
    return user


@router.get("/ui/api/status", include_in_schema=False)
def ui_status(user: dict = Depends(require_session)) -> dict:  # noqa: ARG001
    return {"queue": store.counts(), "llm_online": llm_online()}


def _batch_label(prefix: str) -> str:
    return f"{prefix} {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}"


@router.get("/ui/api/dashboard", include_in_schema=False)
def ui_dashboard(batch: str | None = None, user: dict = Depends(require_session)) -> dict:
    data = dashboard(store, batch or None)
    data["budget"] = budget.status(store, user.get("email"))
    return data


@router.post("/ui/api/budget/approve", dependencies=[Depends(require_csrf)], include_in_schema=False)
def ui_budget_approve(user: dict = Depends(require_session)) -> dict:
    if not budget.is_approver(user.get("email")):
        raise HTTPException(403, "you are not allowed to approve more spending")
    budget.approve(store, user.get("email", ""))
    return budget.status(store, user.get("email"))


@router.get("/ui/api/leads", include_in_schema=False)
def ui_leads(
    status: str | None = Query(None, pattern="^(queued|running|done|failed)$"),
    batch: str | None = None,
    user: dict = Depends(require_session),  # noqa: ARG001
) -> list[dict]:
    rows = store.list(status, 1000, batch=batch or None)
    out = []
    for r in rows:
        p = r.get("profile") or {}
        out.append(
            {
                "id": r["id"], "company": r["company"], "hints": r["hints"], "status": r["status"],
                "batch": r.get("batch", ""), "step": r.get("current_step", ""),
                "submitted_by": r.get("submitted_by", ""), "updated_at": r["updated_at"],
                "company_name": p.get("company_name"), "confidence": p.get("confidence"), "error": r.get("error"),
            }
        )
    return out


@router.get("/ui/api/leads/{lead_id}", include_in_schema=False)
def ui_lead(lead_id: int, user: dict = Depends(require_session)) -> dict:  # noqa: ARG001
    row = store.get(lead_id)
    if not row:
        raise HTTPException(404, "not found")
    row.pop("trace", None)
    return row


@router.post("/ui/api/leads", status_code=201, dependencies=[Depends(require_csrf)], include_in_schema=False)
def ui_add(body: UIBulk, user: dict = Depends(require_session)) -> dict:
    batch = _batch_label("Manual")
    return {"batch": batch, "ids": [store.add(x.company, x.hints, user["email"], batch) for x in body.leads]}


class UIImport(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    data_b64: str = Field(min_length=4, max_length=7_000_000)
    batch: str = Field("", max_length=100)


@router.post("/ui/api/import", status_code=201, dependencies=[Depends(require_csrf)], include_in_schema=False)
def ui_import(body: UIImport, user: dict = Depends(require_session)) -> dict:
    try:
        data = base64.b64decode(body.data_b64, validate=True)
    except ValueError as exc:
        raise HTTPException(400, "file data was not valid base64") from exc
    try:
        result = parse_upload(body.filename, data)
    except ImportError_ as exc:
        raise HTTPException(400, str(exc)) from exc
    if not result.rows:
        raise HTTPException(400, f"no usable rows found (skipped {result.skipped} without a company name)")
    stem = body.filename.rsplit(".", 1)[0][:60]
    batch = body.batch.strip() or _batch_label(stem)
    for company, hints in result.rows:
        store.add(company, hints, user["email"], batch)
    return {
        "batch": batch, "added": len(result.rows), "skipped": result.skipped, "duplicates": result.duplicates,
        "truncated": result.truncated, "company_column": result.company_column, "hint_columns": result.hint_columns,
    }


@router.post("/ui/api/leads/{lead_id}/retry", dependencies=[Depends(require_csrf)], include_in_schema=False)
def ui_retry(lead_id: int, user: dict = Depends(require_session)) -> dict:  # noqa: ARG001
    if not store.retry(lead_id):
        raise HTTPException(409, "lead is not in a retryable state")
    return {"id": lead_id, "status": "queued"}


def _export_name(batch: str | None, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", batch).strip("_") if batch else "all"
    return f"leads_{base or 'all'}.{ext}"


@router.get("/ui/api/export.csv", include_in_schema=False)
def ui_export(batch: str | None = None, user: dict = Depends(require_session)):  # noqa: ARG001
    return PlainTextResponse(
        build_csv(batch or None), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_export_name(batch, "csv")}"'},
    )


@router.get("/ui/api/export.xlsx", include_in_schema=False)
def ui_export_xlsx(batch: str | None = None, user: dict = Depends(require_session)):  # noqa: ARG001
    return Response(
        build_xlsx(batch or None),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_export_name(batch, "xlsx")}"'},
    )
