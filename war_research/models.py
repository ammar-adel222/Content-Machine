"""Small, versioned contracts shared with future writing and directing agents."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchRequest(Model):
    mode: Literal["specific", "direction", "auto"] = "auto"
    topic: str = ""
    scope: Literal["auto", "battle", "war"] = "auto"
    target_seconds: int = Field(default=105, ge=60, le=150)
    excluded_topics: list[str] = Field(default_factory=list)
    as_of: date = Field(default_factory=lambda: datetime.now(timezone.utc).date())
    max_searches: int = Field(default=10, ge=1, le=30)
    max_extract_urls: int = Field(default=5, ge=0, le=10)
    max_model_calls: int = Field(default=5, ge=2, le=12)

    @model_validator(mode="after")
    def check_topic(self):
        if self.mode != "auto" and not self.topic:
            raise ValueError("Specific and direction modes require a topic.")
        return self


class Source(Model):
    id: str
    url: HttpUrl
    title: str
    text: str
    kind: Literal["article", "map_reference", "wikipedia"] = "article"
    published_date: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    full_text: bool = False


class Scores(Model):
    story: int = Field(ge=0, le=5)
    visual: int = Field(ge=0, le=5)
    evidence: int = Field(ge=0, le=5)
    format_fit: int = Field(ge=0, le=5)
    novelty: int = Field(ge=0, le=5)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class Candidate(Model):
    topic: str = Field(min_length=3)
    scope: Literal["battle", "war"]
    angle: str = Field(min_length=8)
    reason: str = Field(min_length=8)
    source_ids: list[str] = Field(min_length=1)
    scores: Scores


class Selection(Model):
    candidates: list[Candidate] = Field(min_length=1, max_length=3)


class Evidence(Model):
    passage_id: str
    source_id: str = ""
    quote: str = Field(default="", max_length=1600)


Section = Literal["context", "dates", "duration", "location", "forces", "terrain", "events", "outcome"]
REQUIRED_SECTIONS = ("context", "dates", "duration", "location", "forces", "terrain", "events", "outcome")


class Claim(Model):
    id: str
    section: Section
    statement: str = Field(min_length=8)
    status: Literal["documented", "estimate", "disputed", "inferred"]
    evidence: list[Evidence] = Field(min_length=1)


class TerrainFeature(Model):
    name: str
    description: str
    tactical_effect: str
    spatial_relation: str
    claim_ids: list[str] = Field(min_length=1)


class Event(Model):
    order: int = Field(ge=1)
    title: str
    time: str | None = None
    actors: list[str]
    location: str
    action: str
    reason: str
    consequence: str
    claim_ids: list[str] = Field(min_length=1)


class Findings(Model):
    """LLM-authored content. Sources, readiness and run metadata are code-owned."""

    era: Literal["ancient", "medieval", "early_modern", "modern", "mixed"]
    ongoing: bool
    recommended_seconds: int = Field(ge=60, le=150)
    summary: str = Field(min_length=20)
    claims: list[Claim]
    terrain: list[TerrainFeature]
    events: list[Event]
    essential_claim_ids: list[str]
    optional_claim_ids: list[str]
    gaps: list[str]
    blocking_gaps: list[str] = Field(default_factory=list)


class Usage(Model):
    searches: int = 0
    extracted_urls: int = 0
    model_calls: int = 0


class Dossier(Model):
    schema_version: Literal["1.0"] = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request: ResearchRequest
    selected: Candidate
    alternatives: list[Candidate]
    findings: Findings
    sources: list[Source]
    selection_sources: list[Source]
    readiness: Literal["ready", "incomplete"]
    warnings: list[str]
    usage: Usage
    models_used: list[str]


class Discovery(Model):
    request: ResearchRequest
    selection: Selection
    sources: list[Source]
    warnings: list[str]
    usage: Usage
    models_used: list[str]
