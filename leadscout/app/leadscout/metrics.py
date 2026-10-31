"""Dashboard numbers: batch progress, LLM engine load, server load, speed versus normal."""

from __future__ import annotations

import os
import re
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import settings
from .db import LeadStore

_METRIC_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eEinfNa]+)")
_rate_lock = threading.Lock()
_last_tokens: tuple[float, float] | None = None  # (monotonic time, generation tokens total)
_last_rate: float = 0.0

NORMAL_SAMPLE = 50   # finished leads that define "normal"
RECENT_SAMPLE = 5    # finished leads that define "now"
MIN_FOR_BASELINE = 6


def _parse_prometheus(text: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = _METRIC_RE.match(line)
        if not m:
            continue
        try:
            totals[m.group(1)] = totals.get(m.group(1), 0.0) + float(m.group(3))
        except ValueError:
            continue
    return totals


def engine_metrics() -> dict[str, Any]:
    """Read vLLM's Prometheus /metrics through the tunnel. Missing values come back as None."""
    global _last_tokens, _last_rate
    base = settings.llm_base_url.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    try:
        r = httpx.get(f"{root}/metrics", headers={"Authorization": f"Bearer {settings.llm_api_key}"}, timeout=4.0)
        if r.status_code != 200:
            return {"online": False}
    except httpx.HTTPError:
        return {"online": False}
    m = _parse_prometheus(r.text)

    def first(*names: str) -> float | None:
        for n in names:
            if n in m:
                return m[n]
        return None

    kv = first("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc")
    tokens = first("vllm:generation_tokens_total", "vllm:generation_tokens")
    now = time.monotonic()
    with _rate_lock:
        if tokens is not None:
            if _last_tokens and now - _last_tokens[0] >= 2 and tokens >= _last_tokens[1]:
                _last_rate = (tokens - _last_tokens[1]) / (now - _last_tokens[0])
                _last_tokens = (now, tokens)
            elif not _last_tokens or tokens < _last_tokens[1]:
                _last_tokens = (now, tokens)
        rate = _last_rate
    return {
        "online": True,
        "running": first("vllm:num_requests_running"),
        "waiting": first("vllm:num_requests_waiting"),
        "kv_cache_pct": None if kv is None else round(kv * 100 if kv <= 1 else kv, 1),
        "tokens_per_s": round(rate, 1),
    }


def server_metrics() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        load1 = os.getloadavg()[0]
        cpus = os.cpu_count() or 1
        out.update(load1=round(load1, 2), cpus=cpus, cpu_pct=round(min(load1 / cpus, 2.0) * 100, 1))
    except OSError:
        pass
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0])
        total, avail = info.get("MemTotal"), info.get("MemAvailable")
        if total and avail is not None:
            out["mem_pct"] = round((total - avail) / total * 100, 1)
    except (OSError, ValueError):
        pass
    return out


def speed_metrics(store: LeadStore) -> dict[str, Any]:
    durs = store.durations(NORMAL_SAMPLE)
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    out: dict[str, Any] = {"samples": len(durs), "per_hour": store.finished_since(hour_ago)}
    if durs:
        out["normal_s"] = round(statistics.median(durs), 1)
    if len(durs) >= MIN_FOR_BASELINE:
        recent = statistics.mean(durs[:RECENT_SAMPLE])
        out["recent_s"] = round(recent, 1)
        out["deviation_pct"] = round((recent - out["normal_s"]) / out["normal_s"] * 100, 1)
    else:
        out["need"] = MIN_FOR_BASELINE - len(durs)
    return out


def batch_progress(store: LeadStore, batch: str | None) -> dict[str, Any]:
    batches = store.batches()
    if not batch:
        active = [b for b in batches if (b["queued"] or 0) + (b["running"] or 0) > 0]
        batch = (active or batches or [{"batch": ""}])[0]["batch"]
    counts = store.counts(batch or None)
    total = sum(counts.values())
    finished = counts.get("done", 0) + counts.get("failed", 0)
    return {
        "batch": batch or "",
        "total": total,
        "done": counts.get("done", 0),
        "failed": counts.get("failed", 0),
        "queued": counts.get("queued", 0),
        "running": counts.get("running", 0),
        "pct": round(finished / total * 100, 1) if total else 0.0,
    }


def cost_metrics(store: LeadStore, progress: dict[str, Any], speed: dict[str, Any]) -> dict[str, Any]:
    """Estimates only: GPU hourly rate x research time. Idle GPU time is not in the per-lead figure."""
    rate = settings.gpu_cost_per_hour
    out: dict[str, Any] = {"currency": settings.cost_currency, "rate_per_hour": rate}
    if speed.get("normal_s"):
        per_lead = rate * speed["normal_s"] / 3600
        finished = progress["done"] + progress["failed"]
        remaining = progress["queued"] + progress["running"]
        out.update(
            per_lead=round(per_lead, 4),
            batch_estimate=round(per_lead * progress["total"], 2),
            batch_spent=round(per_lead * finished, 2),
            batch_remaining=round(per_lead * remaining, 2),
        )
    since = store.get_meta("engine_online_since")
    if since:
        try:
            secs = (datetime.now(timezone.utc) - datetime.fromisoformat(since)).total_seconds()
            out.update(session_s=round(secs), session_cost=round(rate * secs / 3600, 2))
        except ValueError:
            pass
    return out


def dashboard(store: LeadStore, batch: str | None = None) -> dict[str, Any]:
    progress = batch_progress(store, batch)
    speed = speed_metrics(store)
    remaining = progress["queued"] + progress["running"]
    if remaining and speed.get("normal_s"):
        speed["eta_s"] = round(remaining * speed["normal_s"])
    now = datetime.now(timezone.utc)
    working = []
    for r in store.running():
        started = datetime.fromisoformat(r["started_at"]) if r.get("started_at") else None
        working.append(
            {"id": r["id"], "company": r["company"], "step": r["current_step"],
             "elapsed_s": round((now - started).total_seconds()) if started else None}
        )
    return {
        "progress": progress,
        "engine": engine_metrics(),
        "server": server_metrics(),
        "speed": speed,
        "cost": cost_metrics(store, progress, speed),
        "working": working,
        "queue": store.counts(),
        "batches": store.batches(20),
    }
