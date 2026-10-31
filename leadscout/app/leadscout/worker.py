"""Queue worker. Runs on the always-on CPU box.

Processes queued leads whenever the GPU-hosted LLM is reachable. Sends a
notification when leads are waiting but the GPU is down ("deploy it"), and when
the queue drains after a batch ("destroy it, billing is hourly").
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

import httpx

from . import budget
from .agent import LeadAgent
from .config import settings
from .db import LeadStore

log = logging.getLogger("leadscout.worker")

WAITING_NOTICE_AFTER_S = 15 * 60

_stop = False


def _handle_stop(signum, frame) -> None:  # noqa: ARG001
    global _stop
    _stop = True
    log.info("stop requested; finishing current lead")


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


def notify(text: str) -> None:
    log.info("NOTICE: %s", text)
    url = settings.notify_webhook
    if not url:
        return
    try:
        if "ntfy" in url:
            httpx.post(url, content=text.encode(), timeout=10.0)
        else:  # Slack / Teams / generic incoming webhook
            httpx.post(url, json={"text": text}, timeout=10.0)
    except httpx.HTTPError as exc:
        log.warning("notify failed: %s", exc)


def track_engine(store: LeadStore, online: bool) -> None:
    """Remember when the model came online, for the cost meter's 'GPU session' figure."""
    since = store.get_meta("engine_online_since")
    if online and not since:
        store.set_meta("engine_online_since", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    elif not online and since:
        store.set_meta("engine_online_since", None)


def run_forever(store: LeadStore | None = None) -> None:
    store = store or LeadStore(settings.db_path)
    requeued = store.requeue_running()
    if requeued:
        log.info("requeued %d interrupted lead(s)", requeued)

    processed_in_batch = 0
    waiting_since: float | None = None
    waiting_notified = False
    last_tick = time.monotonic()
    budget_notified = False

    while not _stop:
        queued = store.counts().get("queued", 0)
        online = llm_online()
        track_engine(store, online)
        now = time.monotonic()
        if online:
            budget.add_gpu_time(store, now - last_tick)
        last_tick = now

        if budget.paused(store):
            if not budget_notified:
                b = budget.status(store)
                notify(f"LeadScout: spending limit reached ({b['currency']}{b['spent']:.2f} of "
                       f"{b['currency']}{b['limit']:.2f} approved). Research and chat are paused. Approve another "
                       f"{b['currency']}{b['step']:.0f} in the portal, or destroy the GPU instance: it keeps "
                       "billing while it exists.")
                budget_notified = True
            time.sleep(settings.poll_interval_s)
            continue
        budget_notified = False

        if queued == 0:
            if processed_in_batch:
                notify(f"LeadScout: batch done, {processed_in_batch} lead(s) processed. Queue empty. "
                       "Destroy the GPU instance now to stop billing.")
                processed_in_batch = 0
            waiting_since, waiting_notified = None, False
            time.sleep(settings.poll_interval_s)
            continue

        if not online:
            waiting_since = waiting_since or time.monotonic()
            if not waiting_notified and time.monotonic() - waiting_since > WAITING_NOTICE_AFTER_S:
                notify(f"LeadScout: {queued} lead(s) waiting and the LLM is offline. Deploy the GPU instance.")
                waiting_notified = True
            time.sleep(settings.poll_interval_s)
            continue
        waiting_since, waiting_notified = None, False

        lead = store.claim_next()
        if lead is None:
            continue
        log.info("lead %s: researching %r (attempt %s)", lead["id"], lead["company"], lead["attempts"])
        lead_id = lead["id"]
        agent = LeadAgent(on_step=lambda text, _id=lead_id: store.set_step(_id, text))
        started = time.monotonic()
        try:
            profile = agent.run(lead["company"], lead["hints"])
        except Exception as exc:  # noqa: BLE001
            log.exception("lead %s failed", lead["id"])
            store.fail(lead["id"], f"{type(exc).__name__}: {exc}", lead["attempts"])
            continue
        store.complete(lead["id"], profile.model_dump(), agent.trace)
        processed_in_batch += 1
        log.info("lead %s: done in %.0fs, confidence=%s", lead["id"], time.monotonic() - started, profile.confidence)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    run_forever()


if __name__ == "__main__":
    main()
