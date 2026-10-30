import json
import re
from pathlib import Path
from uuid import uuid4
from .models import Plan


def markdown(plan: Plan) -> str:
    b = plan.blueprint
    lines = [f"# Director plan: {plan.topic}", "", f"Status: **{plan.status}** | Scale: {b.scale}",
             f"Timing: **{plan.timing_basis}**, {plan.duration_seconds}s", "", b.layout_note,
             "", "## Terrain (schematic)", ""]
    lines += [f"- **{t.id} / {t.label}:** {t.kind}, {t.passability}. {t.tactical_effect} Claims: {', '.join(t.claim_ids)}." for t in b.terrain]
    lines += ["", "## Forces", ""]
    lines += [f"- **{f.id} / {f.name}:** {f.side}, {f.kind}, {f.subgroups} symbolic subgroups; start ({f.position.x}, {f.position.y}); introduced at {f.introduced_at.phrase_id}@{f.introduced_at.fraction}. {f.introduction_reason}" for f in b.forces]
    for scene in b.scenes:
        lines += ["", f"## {scene.scene_id}", "", f"Focus: {scene.focus_reason}", f"Labels: {', '.join(scene.labels)}", ""]
        for action in scene.actions:
            lines += [f"- **{action.id}:** {action.kind} {action.unit_id}; {action.start.phrase_id}@{action.start.fraction} -> {action.end.phrase_id}@{action.end.fraction}.",
                      f"  Why: {action.reason} Result: {action.consequence} Claims: {', '.join(action.claim_ids)}."]
            if action.route:
                lines += ["  Route: " + " -> ".join(f"({p.x}, {p.y})" for p in action.route)]
    lines += ["", "## Issues", ""] + [f"- {i}" for i in plan.issues]
    lines += ["", "## Uncertainties", ""] + [f"- {gap}" for gap in b.gaps]
    lines += ["", "## Provenance", "", f"Research: `{plan.dossier_sha256}`", f"Script: `{plan.script_sha256}`",
              f"Changed scenes: {', '.join(plan.changed_scene_ids)}", f"Model attempts: {plan.model_calls}",
              "", "This is a storyboard, not a rendered video. Layout is schematic, not surveyed geography.",
              "Subgroup following, terrain shading, label placement, and camera interpolation belong to the PixiJS renderer."]
    return "\n".join(lines) + "\n"


def save(plan: Plan, root: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", plan.topic).strip("-").lower()[:70] or "topic"
    directory = root / f"{slug}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    (directory/"storyboard.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (directory/"storyboard.md").write_text(markdown(plan), encoding="utf-8")
    if plan.review:
        (directory/"review.json").write_text(plan.review.model_dump_json(indent=2), encoding="utf-8")
    (directory/"render_plan.json").write_text(json.dumps({"schema_version": "1.0", "renderer": "pixijs",
        "status": plan.status, "timing_basis": plan.timing_basis, "world_aspect": "9:16",
        "coordinate_space": "normalized_schematic", "origin": "top-left", "y_direction": "down",
        "motion_policy": "continuous_polyline_followers", "subgroup_counts": "symbolic_not_troop_numbers",
        "collision_checks": "centerlines_only", "script_sha256": plan.script_sha256,
        "blueprint": plan.blueprint.model_dump(), "timeline": plan.timeline}, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory
