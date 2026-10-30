"""Writer contracts: spoken text is always separate from performance instructions."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, model_validator

from war_research.models import Claim, Model


class WritingRequest(Model):
    target_seconds: int | None = Field(default=None, ge=60, le=150)
    notes: str = Field(default="", max_length=5000)
    scene_id: str | None = None
    max_model_calls: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def check_edit(self):
        if self.scene_id and not self.notes:
            raise ValueError("A scene edit requires revision notes.")
        return self


class Phrase(Model):
    text: str = Field(min_length=3, max_length=450)
    pace: Literal["measured", "normal", "brisk"]
    emphasis: list[str] = Field(default_factory=list)
    pause_after_ms: int = Field(default=200, ge=0, le=2000)


class Scene(Model):
    id: str = Field(pattern=r"^s[1-9][0-9]*$")
    role: Literal["hook", "context", "maneuver", "turning_point", "outcome"]
    claim_ids: list[str] = Field(min_length=1)
    visual_intent: str = Field(min_length=8, max_length=500)
    tone: str = Field(min_length=3, max_length=100)
    delivery_notes: str = Field(min_length=8, max_length=500)
    phrases: list[Phrase] = Field(min_length=1, max_length=6)


class Pronunciation(Model):
    term: str = Field(min_length=2, max_length=100)
    say_as: str = Field(min_length=2, max_length=150)


class Draft(Model):
    title: str = Field(min_length=5, max_length=90)
    caption: str = Field(max_length=400)
    narrator_style: str = Field(min_length=10, max_length=600)
    scenes: list[Scene] = Field(min_length=4, max_length=10)
    pronunciations: list[Pronunciation] = Field(default_factory=list, max_length=20)


class SceneEdit(Model):
    scene: Scene


class Review(Model):
    issues: list[str] = Field(max_length=12)


class Script(Model):
    schema_version: Literal["1.0"] = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    topic: str
    scope: Literal["war", "battle"]
    dossier_sha256: str
    parent_script_sha256: str | None = None
    request: WritingRequest
    draft: Draft
    claims: list[Claim]
    target_seconds: int
    estimated_seconds: float
    word_count: int
    status: Literal["ready", "needs_revision"]
    issues: list[str]
    warnings: list[str]
    changed_scene_ids: list[str]
    model_calls: int
    models_used: list[str]
