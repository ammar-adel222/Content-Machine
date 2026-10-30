"""Review findings are advisory evidence, not proof of historical correctness."""
from typing import Literal
from pydantic import Field
from war_research.models import Model


class Issue(Model):
    severity: Literal["blocking", "advisory"]
    message: str = Field(min_length=8)
    scene_id: str | None = None


class Scores(Model):
    accuracy: int = Field(ge=0, le=5)
    clarity: int = Field(ge=0, le=5)
    visual_logic: int = Field(ge=0, le=5)
    voice: int = Field(ge=0, le=5)
    readability: int = Field(ge=0, le=5)


class Findings(Model):
    scores: Scores
    issues: list[Issue]


class QualityReview(Model):
    schema_version: Literal["1.0"] = "1.0"
    artifact_sha256: str
    status: Literal["pass", "revise"]
    findings: Findings
    local_issues: list[str]
    models_used: list[str]
