"""Declarative storyboard for a future PixiJS renderer; all positions are schematic."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import Field, model_validator
from war_research.models import Model
from war_reviewer.models import QualityReview

Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Duration = Annotated[float, Field(gt=0, le=120, allow_inf_nan=False)]


class DirectionRequest(Model):
    notes: str = Field(default="", max_length=5000)
    scene_id: str | None = None
    max_model_calls: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def edit_notes(self):
        if self.scene_id and not self.notes:
            raise ValueError("Scene edits require notes.")
        return self


class Point(Model):
    """Normalized schematic world: origin top-left, x right, y down."""
    x: Fraction
    y: Fraction


class Cue(Model):
    phrase_id: str
    fraction: Fraction = 0


class AudioTiming(Model):
    script_sha256: str
    # Measured spoken audio duration only; requested silence is added by the compiler.
    durations: dict[str, Duration]


class Terrain(Model):
    id: str
    label: str = Field(min_length=2, max_length=45)
    # Appearance is extensible; movement rules still use explicit passability.
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    shape: Literal["polygon", "polyline"]
    points: list[Point] = Field(min_length=2, max_length=20)
    passability: Literal["open", "slow", "blocked"]
    crossings: list[Point] = Field(default_factory=list)
    tactical_effect: str
    claim_ids: list[str] = Field(min_length=1)


class Force(Model):
    id: str
    name: str = Field(min_length=2, max_length=35)
    side: str
    kind: Literal["infantry", "cavalry", "artillery", "fleet", "air", "army"]
    position: Point
    introduced_at: Cue
    introduction_reason: str = Field(min_length=8)
    subgroups: int = Field(ge=1, le=12)
    claim_ids: list[str] = Field(min_length=1)


class Action(Model):
    id: str
    kind: Literal["move", "withdraw", "engage", "highlight", "fade"]
    unit_id: str
    target_id: str | None = None
    start: Cue
    end: Cue
    route: list[Point] = Field(default_factory=list, max_length=16)
    formation: Literal["line", "column", "wedge", "dispersed", "campaign"]
    stagger: float = Field(default=0.15, ge=0, le=0.3, allow_inf_nan=False)
    reason: str = Field(min_length=8)
    consequence: str = Field(min_length=8)
    claim_ids: list[str] = Field(min_length=1)


class ScenePlan(Model):
    scene_id: str
    focus: Point
    # Width of a 9:16 camera viewport in normalized world coordinates.
    view_width: float = Field(ge=0.1, le=1, allow_inf_nan=False)
    focus_reason: str = Field(min_length=8)
    labels: list[Annotated[str, Field(min_length=1, max_length=35)]] = Field(max_length=3)
    actions: list[Action] = Field(max_length=12)


class Blueprint(Model):
    scale: Literal["tactical", "campaign"]
    layout_kind: Literal["schematic"] = "schematic"
    layout_note: str = Field(min_length=15)
    terrain: list[Terrain] = Field(min_length=1, max_length=12)
    forces: list[Force] = Field(min_length=1, max_length=16)
    scenes: list[ScenePlan] = Field(min_length=1, max_length=10)
    gaps: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)


class Plan(Model):
    schema_version: Literal["1.0"] = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    topic: str
    dossier_sha256: str
    script_sha256: str
    parent_plan_sha256: str | None = None
    request: DirectionRequest
    blueprint: Blueprint
    status: Literal["ready", "needs_revision"]
    issues: list[str]
    review: QualityReview | None
    timing_basis: Literal["estimated", "measured"]
    duration_seconds: float
    timeline: list[dict]
    changed_scene_ids: list[str]
    model_calls: int
    models_used: list[str]
