"""Independent, open-ended unit design using the production asset library."""
from pathlib import Path
from pydantic import Field
from war_research.models import Model
from war_research.providers import ProviderError
from .agent import ContentAgent, ContentError
from .models import Asset, Brief, Design
from war_writer.agent import fingerprint


class UnitResult(Model):
    brief: Brief
    asset: Asset | None = None
    draft: Design | None = None
    reused: bool = False
    model_calls: int = Field(ge=0)
    issues: list[str] = Field(default_factory=list)


class UnitDesigner(ContentAgent):
    def create(self, brief: Brief, *, max_model_calls=4):
        if brief.category != "unit":
            raise ValueError("Unit designer requires a unit brief.")
        if not 1 <= max_model_calls <= 12:
            raise ValueError("Unit budget must be 1–12 model attempts.")
        calls, drafts = 0, {}
        self.model.used.clear()
        self.reviewer.used.clear()

        def consume():
            nonlocal calls
            if calls >= max_model_calls:
                raise ContentError("Unit design model budget exhausted.")
            calls += 1

        try:
            asset, reused = self.design_asset(brief, consume, drafts)
            return UnitResult(brief=brief, asset=asset, reused=reused, model_calls=calls)
        except (ContentError, ProviderError) as error:
            return UnitResult(brief=brief, draft=next(iter(drafts.values()), None),
                              model_calls=calls, issues=[str(error)])


def save_unit(result, directory, preview):
    """Keep rejected drafts inspectable without admitting them into the library."""
    if result.asset and (result.asset.brief != result.brief or not result.asset.review.passed
                         or result.asset.design_sha256 != fingerprint(result.asset.design)):
        raise ContentError("Unit asset identity, review or design hash changed before saving.")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    (root / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    design = result.asset.design if result.asset else result.draft
    if design:
        (root / "design.json").write_text(design.model_dump_json(indent=2), encoding="utf-8")
        (root / "preview.png").write_bytes(preview(design))
    lines = ["# Unit design", "", f"Concept: {result.brief.concept}",
             f"Brief: {result.brief.description}",
             f"Status: {'ready' if result.asset else 'needs_revision'}",
             f"Reused: {result.reused}; model attempts: {result.model_calls}", "",
             "## Review", ""]
    if result.asset:
        lines += [f"Basis: {result.asset.review_basis}; version: {result.asset.review_version}",
                  result.asset.design.explanation]
    lines += result.issues
    lines += ["", "Preview uses the map's PixiJS interpreter: large inspection, 24/32/40px",
              "symbols in both team colors, rotation, and grouped units on terrain colors.",
              "Sizes are screen pixels. At a 360px-wide display a 32px symbol in a",
              "1080px export occupies about 11px; camera framing must allow for this.",
              "This validates appearance only. Historical placement requires the researched manifest."]
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root
