"""The structured lead profile the agent must return."""

from __future__ import annotations

from urllib.parse import quote_plus

from pydantic import BaseModel, Field


class Registration(BaseModel):
    jurisdiction: str = Field(description="e.g. 'us_il' or 'Illinois'")
    entity_number: str | None = None
    legal_name: str | None = None
    status: str | None = Field(None, description="Active, Dissolved, etc.")
    entity_type: str | None = None
    formation_date: str | None = None
    registered_agent: str | None = None
    source_url: str | None = None


class Person(BaseModel):
    name: str
    role: str = Field(description="Business role only: officer title, owner, manager, etc.")
    source_url: str | None = Field(None, description="Where this person was found")
    linkedin_search_url: str | None = Field(
        None, description="Filled in by code, not the model: a manual search link for a human to click"
    )


class ITSignals(BaseModel):
    email_provider: str | None = Field(None, description="Microsoft 365, Google Workspace, other, from MX records")
    mx_records: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, description="Other public IT clues: website platform, compliance mentions")


class LeadProfile(BaseModel):
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
