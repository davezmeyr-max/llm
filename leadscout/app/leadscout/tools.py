"""Read-only research tools the agent can call.

Every tool returns a JSON-serialisable dict. Tools never raise to the agent:
failures come back as {"error": "..."} so the model can try something else.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import dns.resolver
import httpx
import trafilatura

from .config import settings

# Sites the agent must not fetch. LinkedIn/Facebook/Instagram prohibit scraping;
# people-search brokers are personal-data aggregators and out of scope for B2B leads.
BLOCKED_DOMAINS = {
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "whitepages.com",
    "spokeo.com",
    "beenverified.com",
    "truepeoplesearch.com",
    "fastpeoplesearch.com",
    "radaris.com",
    "peoplefinders.com",
    "intelius.com",
    "mylife.com",
}

ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
MAX_DOWNLOAD_BYTES = 3_000_000
MAX_REDIRECTS = 5


class FetchBlocked(Exception):
    pass


def _domain_blocked(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def check_url_safe(url: str) -> None:
    """Reject anything that is not a public http(s) URL.

    Guards against SSRF: the agent follows URLs found on the open web, and this
    box also runs SearXNG and the API on loopback.
    Note: resolution and connection are separate steps, so a DNS-rebinding host
    could still race this check. Acceptable for a read-only tool; run the worker
    on a box with nothing sensitive on its private network.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchBlocked(f"scheme not allowed: {parsed.scheme or '(none)'}")
    host = parsed.hostname
    if not host:
        raise FetchBlocked("no host in URL")
    if _domain_blocked(host):
        raise FetchBlocked(f"domain is on the do-not-fetch list: {host}")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise FetchBlocked(f"cannot resolve {host}: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchBlocked(f"{host} resolves to non-public address {ip}")


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": settings.user_agent, "Accept-Language": "en-US,en;q=0.8"},
        follow_redirects=False,
    )


# ---------------------------------------------------------------- web search


def web_search(query: str, max_results: int = 8) -> dict[str, Any]:
    """Search the web through the self-hosted SearXNG instance."""
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{settings.searxng_url.rstrip('/')}/search",
                params={"q": query, "format": "json", "categories": "general", "language": "en-US"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"search failed: {exc}"}
    results = []
    for r in data.get("results", [])[: max(1, min(max_results, 15))]:
        results.append({"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:400]})
    return {"query": query, "results": results}


# ---------------------------------------------------------------- page fetch


def fetch_page(url: str) -> dict[str, Any]:
    """Fetch a public web page and return its main text."""
    try:
        current = url
        with _client() as client:
            for _ in range(MAX_REDIRECTS + 1):
                check_url_safe(current)
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return {"error": "redirect without location", "url": current}
                        current = urljoin(current, location)
                        continue
                    if resp.status_code >= 400:
                        return {"error": f"HTTP {resp.status_code}", "url": current}
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and not ctype.startswith(ALLOWED_CONTENT_TYPES):
                        return {"error": f"unsupported content type {ctype}", "url": current}
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_DOWNLOAD_BYTES:
                            break
                    html = body.decode(resp.encoding or "utf-8", errors="replace")
                    break
            else:
                return {"error": "too many redirects", "url": url}
    except FetchBlocked as exc:
        return {"error": f"blocked: {exc}", "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"fetch failed: {exc}", "url": url}

    text = trafilatura.extract(html, include_links=False, include_tables=True, favor_recall=True) or ""
    if not text.strip():
        return {"error": "no readable text on page", "url": current}
    limit = settings.page_char_limit
    return {"url": current, "truncated": len(text) > limit, "text": text[:limit]}


# ---------------------------------------------------------------- business registries


OC_BASE = "https://api.opencorporates.com/v0.4"


def _oc_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    if not settings.opencorporates_token:
        return {"error": "OpenCorporates is not configured (no OPENCORPORATES_API_TOKEN). Use web_search instead."}
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": settings.user_agent}) as client:
            resp = client.get(f"{OC_BASE}{path}", params={**params, "api_token": settings.opencorporates_token})
            if resp.status_code == 404:
                return {"error": "not found"}
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"opencorporates request failed: {exc}"}


def registry_search(name: str, jurisdiction_code: str | None = None) -> dict[str, Any]:
    """Search state business registrations (Secretary of State data via OpenCorporates)."""
    params: dict[str, Any] = {"q": name, "per_page": 10}
    if jurisdiction_code:
        params["jurisdiction_code"] = jurisdiction_code.lower()
    data = _oc_get("/companies/search", params)
    if "error" in data:
        return data
    out = []
    for item in data.get("results", {}).get("companies", []):
        c = item.get("company", {})
        out.append(
            {
                "name": c.get("name"),
                "jurisdiction_code": c.get("jurisdiction_code"),
                "company_number": c.get("company_number"),
                "status": c.get("current_status"),
                "incorporation_date": c.get("incorporation_date"),
                "company_type": c.get("company_type"),
                "registered_address": c.get("registered_address_in_full"),
                "opencorporates_url": c.get("opencorporates_url"),
            }
        )
    return {"query": name, "companies": out}


def registry_company(jurisdiction_code: str, company_number: str) -> dict[str, Any]:
    """Full registration record for one company, including listed officers and agent."""
    data = _oc_get(f"/companies/{jurisdiction_code.lower()}/{company_number}", {})
    if "error" in data:
        return data
    c = data.get("results", {}).get("company", {})
    officers = []
    for o in c.get("officers", []) or []:
        off = o.get("officer", {})
        officers.append(
            {
                "name": off.get("name"),
                "position": off.get("position"),
                "start_date": off.get("start_date"),
                "end_date": off.get("end_date"),
            }
        )
    return {
        "name": c.get("name"),
        "jurisdiction_code": c.get("jurisdiction_code"),
        "company_number": c.get("company_number"),
        "status": c.get("current_status"),
        "incorporation_date": c.get("incorporation_date"),
        "dissolution_date": c.get("dissolution_date"),
        "company_type": c.get("company_type"),
        "registered_address": c.get("registered_address_in_full"),
        "agent_name": c.get("agent_name"),
        "agent_address": c.get("agent_address"),
        "officers": officers,
        "source_url": c.get("registry_url") or c.get("opencorporates_url"),
    }


# ---------------------------------------------------------------- DNS


MX_PROVIDERS = [
    ("mail.protection.outlook.com", "Microsoft 365"),
    ("outlook.com", "Microsoft 365"),
    ("google.com", "Google Workspace"),
    ("googlemail.com", "Google Workspace"),
    ("pphosted.com", "Proofpoint gateway (mailbox host unknown)"),
    ("mimecast.com", "Mimecast gateway (mailbox host unknown)"),
    ("barracudanetworks.com", "Barracuda gateway (mailbox host unknown)"),
    ("secureserver.net", "GoDaddy email"),
    ("zoho.com", "Zoho Mail"),
]


def dns_lookup(domain: str) -> dict[str, Any]:
    """MX and SPF records for a company domain; reveals the email platform."""
    domain = domain.lower().strip().removeprefix("http://").removeprefix("https://").split("/")[0]
    domain = domain.removeprefix("www.")
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 8.0
    out: dict[str, Any] = {"domain": domain, "mx": [], "spf": None, "email_provider": None}
    try:
        answers = resolver.resolve(domain, "MX")
        out["mx"] = sorted(str(r.exchange).rstrip(".").lower() for r in answers)
    except Exception as exc:  # noqa: BLE001
        out["mx_error"] = str(exc)
    try:
        for r in resolver.resolve(domain, "TXT"):
            txt = b"".join(r.strings).decode(errors="replace")
            if txt.lower().startswith("v=spf1"):
                out["spf"] = txt
    except Exception:  # noqa: BLE001
        pass
    for mx in out["mx"]:
        for suffix, name in MX_PROVIDERS:
            if mx.endswith(suffix):
                out["email_provider"] = name
                break
        if out["email_provider"]:
            break
    if out["email_provider"] and "gateway" in out["email_provider"] and out["spf"]:
        spf = out["spf"].lower()
        if "spf.protection.outlook.com" in spf:
            out["email_provider"] += "; SPF includes Microsoft 365"
        elif "_spf.google.com" in spf:
            out["email_provider"] += "; SPF includes Google Workspace"
    return out


# ---------------------------------------------------------------- registry for the agent


TOOL_FUNCS: dict[str, Callable[..., dict[str, Any]]] = {
    "web_search": web_search,
    "fetch_page": fetch_page,
    "registry_search": registry_search,
    "registry_company": registry_company,
    "dns_lookup": dns_lookup,
}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns titles, URLs and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 15},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch a public web page and return its main text. LinkedIn, social networks and "
            "people-search sites are blocked.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registry_search",
            "description": "Search Secretary of State business registrations. jurisdiction_code like 'us_il', "
            "'us_de', 'us_tx'. Omit it to search all jurisdictions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "jurisdiction_code": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registry_company",
            "description": "Get one registration record with officers and registered agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jurisdiction_code": {"type": "string"},
                    "company_number": {"type": "string"},
                },
                "required": ["jurisdiction_code", "company_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dns_lookup",
            "description": "MX and SPF records for the company's domain, to identify their email platform.",
            "parameters": {
                "type": "object",
                "properties": {"domain": {"type": "string"}},
                "required": ["domain"],
            },
        },
    },
]
