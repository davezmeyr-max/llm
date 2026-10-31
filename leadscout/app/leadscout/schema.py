"""The structured lead profile the agent must return."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, Field, model_validator


class Registration(BaseModel):
    jurisdiction: str = Field("", description="e.g. 'us_il' or 'Illinois'")
    entity_number: str | None = None
    legal_name: str | None = None
    status: str | None = Field(None, description="Active, Dissolved, etc.")
    entity_type: str | None = None
    formation_date: str | None = None
    registered_agent: str | None = None
    source_url: str | None = None


class Person(BaseModel):
    name: str
    role: str = Field("", description="Business role only: officer title, owner, manager, etc.")
    source_url: str | None = Field(None, description="Where this person was found")
    linkedin_search_url: str | None = Field(
        None, description="Filled in by code, not the model: a manual search link for a human to click"
    )


class ITSignals(BaseModel):
    email_provider: str | None = Field(None, description="Microsoft 365, Google Workspace, other, from MX records")
    mx_records: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, description="Other public IT clues: website platform, compliance mentions")


def _maybe_json(v: Any) -> Any:
    if isinstance(v, str) and v.strip()[:1] in ("{", "["):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    return v


def _as_list(v: Any) -> list:
    v = _maybe_json(v)
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _as_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v if x not in (None, ""))
    if isinstance(v, dict):
        return "; ".join(f"{k}: {x}" for k, x in v.items() if x not in (None, ""))
    return str(v)


TEXT_FIELDS = ("company_name", "website", "summary", "industry", "employee_estimate", "business_address",
               "business_phone")


class LeadProfile(BaseModel):
    """Lenient on input shape: small models often send a section as a string, a single object instead
    of a list, or numbers where text is expected. Those are normalised here instead of rejecting the
    whole profile; genuinely missing data simply stays empty."""

    input_name: str
    company_name: str | None = None
    website: str | None = None
    summary: str | None = Field(None, description="2-4 sentences: what they do, who they serve")
    industry: str | None = None
    employee_estimate: str | None = Field(None, description="Range like '10-49', only if a source supports it")
    business_address: str | None = None
    business_phone: str | None = None
    registrations: list[Registration] = Field(default_factory=list)
    people: list[Person] = Field(default_factory=list)
    it_signals: ITSignals = Field(default_factory=ITSignals)
    sources: list[str] = Field(default_factory=list)
    confidence: str = Field("low", description="high | medium | low: how sure the match is the right company")
    open_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        data = _maybe_json(data)
        if not isinstance(data, dict):
            return data
        d = dict(data)
        for f in TEXT_FIELDS:
            if f in d:
                d[f] = _as_text(d[f])

        it = _maybe_json(d.get("it_signals"))
        if it is None or it == "":
            d.pop("it_signals", None)
        elif isinstance(it, dict):
            it = dict(it)
            it["mx_records"] = [str(x) for x in _as_list(it.get("mx_records"))]
            for k in ("email_provider", "notes"):
                if k in it:
                    it[k] = _as_text(it[k])
            d["it_signals"] = it
        else:
            d["it_signals"] = {"notes": _as_text(it)}

        regs = []
        for r in _as_list(d.get("registrations")):
            r = _maybe_json(r)
            if isinstance(r, dict):
                regs.append({k: _as_text(v) if k != "jurisdiction" else (_as_text(v) or "") for k, v in r.items()})
            elif r not in (None, ""):
                regs.append({"jurisdiction": "", "legal_name": _as_text(r)})
        d["registrations"] = regs

        people = []
        for p in _as_list(d.get("people")):
            p = _maybe_json(p)
            if isinstance(p, dict) and _as_text(p.get("name")):
                people.append({k: _as_text(v) or "" for k, v in p.items()})
            elif isinstance(p, str) and p.strip():
                name, _, role = p.partition(" - ") if " - " in p else p.partition(",")
                people.append({"name": name.strip(), "role": role.strip()})
        d["people"] = people

        for f in ("sources", "open_questions"):
            d[f] = [_as_text(x) for x in _as_list(d.get(f)) if x not in (None, "")]
        if "confidence" in d:
            d["confidence"] = (_as_text(d["confidence"]) or "low").strip().lower()
        return d

    def finalize(self) -> "LeadProfile":
        """Deterministic post-processing the model should not be trusted with."""
        company = self.company_name or self.input_name
        for p in self.people:
            p.linkedin_search_url = (
                "https://www.linkedin.com/search/results/people/?keywords="
                + quote_plus(f"{p.name} {company}")
            )
        self.sources = sorted(set(self.sources))
        if self.confidence not in {"high", "medium", "low"}:
            self.confidence = "low"
        return self
