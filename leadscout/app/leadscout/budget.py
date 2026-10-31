"""Spending limit. Spend = GPU time while the model is online x GPU_COST_PER_HOUR.

When spend reaches the approved limit, the worker stops starting leads and chat is refused until an
approver adds another BUDGET_STEP. The GPU instance itself keeps billing while it exists; the portal
and the notification say so.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .db import LeadStore

GPU_SECONDS = "gpu_seconds_total"
APPROVED = "budget_approved"
LOG = "budget_log"
MAX_TICK_S = 3600  # ignore gaps longer than an hour (e.g. the worker was stopped)


def is_approver(email: str | None) -> bool:
    email = (email or "").strip().lower()
    return email == "admin" or email in settings.budget_approvers


def add_gpu_time(store: LeadStore, seconds: float) -> None:
    if seconds <= 0:
        return
    total = float(store.get_meta(GPU_SECONDS) or 0) + min(seconds, MAX_TICK_S)
    store.set_meta(GPU_SECONDS, f"{total:.1f}")


def spent(store: LeadStore) -> float:
    return float(store.get_meta(GPU_SECONDS) or 0) / 3600 * settings.gpu_cost_per_hour


def limit(store: LeadStore) -> float:
    return float(store.get_meta(APPROVED) or settings.budget_step)


def paused(store: LeadStore) -> bool:
    return settings.budget_step > 0 and spent(store) >= limit(store)


def status(store: LeadStore, email: str | None = None) -> dict[str, Any]:
    s, lim = spent(store), limit(store)
    return {
        "enabled": settings.budget_step > 0,
        "spent": round(s, 2),
        "limit": round(lim, 2),
        "step": settings.budget_step,
        "pct": round(min(s / lim, 1.0) * 100, 1) if lim else 0.0,
        "paused": paused(store),
        "can_approve": is_approver(email),
        "currency": settings.cost_currency,
    }


def approve(store: LeadStore, email: str) -> float:
    """Raise the limit by one step above whichever is higher: the current limit or what is already spent."""
    new_limit = max(limit(store), spent(store)) + settings.budget_step
    store.set_meta(APPROVED, f"{new_limit:.2f}")
    log = json.loads(store.get_meta(LOG) or "[]")
    log.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "by": email,
                "spent": round(spent(store), 2), "new_limit": round(new_limit, 2)})
    store.set_meta(LOG, json.dumps(log[-100:]))
    return new_limit
