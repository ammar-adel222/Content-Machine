"""Small, data-only visual language shared by units and terrain motifs."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import Field, model_validator
from war_research.models import Model

Coordinate = Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]
Size = Annotated[float, Field(gt=0, le=2, allow_inf_nan=False)]
Role = Literal["team", "ink", "paper", "accent", "muted", "none"]


class Vertex(Model):
    x: Coordinate
    y: Coordinate


class Primitive(Model):
    kind: Literal["rect", "ellipse", "polygon", "line"]
    x: Coordinate = 0
    y: Coordinate = 0
    width: Size = 1
    height: Size = 1
    points: list[Vertex] = Field(default_factory=list, max_length=20)
    fill: Role = "team"
    stroke: Role = "ink"
    stroke_width: float = Field(default=0.05, ge=0, le=0.15, allow_inf_nan=False)

    @model_validator(mode="after")
    def geometry(self):
        if self.kind in ("polygon", "line"):
            minimum = 3 if self.kind == "polygon" else 2
            if len(self.points) < minimum or len({(p.x,p.y) for p in self.points}) < minimum:
                raise ValueError("Path needs distinct vertices.")
            if self.kind == "polygon":
                area = sum(a.x*b.y-b.x*a.y for a,b in zip(self.points,self.points[1:]+self.points[:1]))
                if abs(area) < 0.01:
                    raise ValueError("Polygon must enclose an area.")
        elif self.points or abs(self.x)+self.width/2 > 1.000001 or abs(self.y)+self.height/2 > 1.000001:
            raise ValueError("Centered shape must fit the design square; no path points.")
        if self.kind == "line" and (self.fill != "none" or self.stroke == "none" or not self.stroke_width):
            raise ValueError("Lines need a visible stroke and no fill.")
        if self.fill == "none" and (self.stroke == "none" or not self.stroke_width):
            raise ValueError("Primitive must be visible.")
        return self


class Brief(Model):
    category: Literal["unit", "terrain"]
    concept: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,59}$")
    description: str = Field(min_length=12, max_length=400)


class Binding(Model):
    presentation: Literal['heading','upright'] = 'heading'
    object_id: str
    brief: Brief
    claim_id: str
    evidence_quote: str = Field(min_length=8, max_length=600)


class Manifest(Model):
    bindings: list[Binding] = Field(min_length=1, max_length=28)


class ManifestReview(Model):
    issues: list[str] = Field(default_factory=list, max_length=20)


class Design(Model):
    label: str = Field(min_length=2, max_length=50)
    explanation: str = Field(min_length=12, max_length=500)
    primitives: list[Primitive] = Field(min_length=1, max_length=32)


class DesignReview(Model):
    recognizable: bool
    consistent_style: bool
    supported_by_brief: bool
    issues: list[str] = Field(default_factory=list, max_length=12)

    @property
    def passed(self):
        return self.recognizable and self.consistent_style and self.supported_by_brief and not self.issues


class Asset(Model):
    schema_version: Literal["1.0"] = "1.0"
    style: Literal["atlas-ink-v1"] = "atlas-ink-v1"
    brief: Brief
    design: Design
    design_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review: DesignReview
    review_basis: Literal["vector_data", "rendered_image"] = "vector_data"
    review_version: Literal[1, 2] = 1
    models_used: list[str]


class Build(Model):
    schema_version: Literal["1.0"] = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    topic: str
    plan_sha256: str
    script_sha256: str
    geography_sha256: str | None = None
    status: Literal["ready", "needs_revision"]
    manifest: Manifest
    assets: dict[str, Asset]
    draft_designs: dict[str, Design] = Field(default_factory=dict)
    reused: list[str]
    issues: list[str]
    model_calls: int
    models_used: list[str]
