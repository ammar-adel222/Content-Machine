"""Narration-anchored choreography with continuity and barrier checks."""
import json
import math
import re
from datetime import datetime, timezone

from war_research.agent import validate_evidence
from war_research.models import Dossier
from war_research.providers import ProviderError
from war_reviewer import ReviewerAgent
from war_writer.agent import check_draft, fingerprint, words
from war_writer.models import Script
from .models import AudioTiming, Blueprint, DirectionRequest, Plan, Point, ScenePlan


class DirectionError(RuntimeError):
    pass


def phrase_times(script: Script, audio: AudioTiming | None = None) -> dict:
    ids = {f"{s.id}.p{i}" for s in script.draft.scenes for i in range(1, len(s.phrases) + 1)}
    if audio and (audio.script_sha256 != fingerprint(script) or set(audio.durations) != ids):
        raise DirectionError("Audio timings must match this script fingerprint and every phrase exactly.")
    clock, result = 0.0, {}
    for scene in script.draft.scenes:
        for i, phrase in enumerate(scene.phrases, 1):
            key = f"{scene.id}.p{i}"
            duration = audio.durations[key] if audio else words(phrase.text) * 60 / {"measured": 130, "normal": 150, "brisk": 170}[phrase.pace]
            end = clock + duration + phrase.pause_after_ms / 1000
            result[key] = (clock, end)
            clock = end
    return result


def cue_time(cue, clock):
    start, end = clock[cue.phrase_id]
    return start + (end - start) * cue.fraction


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def on_segment(p, a, b):
    return (abs((b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x)) < 1e-9 and
            min(a.x,b.x)-1e-9 <= p.x <= max(a.x,b.x)+1e-9 and min(a.y,b.y)-1e-9 <= p.y <= max(a.y,b.y)+1e-9)


def inside(p, polygon):
    hit = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if on_segment(p, a, b):
            return True
        if (a.y > p.y) != (b.y > p.y) and p.x < (b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x:
            hit = not hit
    return hit


def intersection(a, b, c, d):
    dx, dy, ex, ey = b.x-a.x, b.y-a.y, d.x-c.x, d.y-c.y
    denominator = dx*ey-dy*ex
    if abs(denominator) < 1e-9:
        return next((p for p in (a,b,c,d) if on_segment(p,a,b) and on_segment(p,c,d)), None)
    t = ((c.x-a.x)*ey-(c.y-a.y)*ex)/denominator
    u = ((c.x-a.x)*dy-(c.y-a.y)*dx)/denominator
    if -1e-9 <= t <= 1+1e-9 and -1e-9 <= u <= 1+1e-9:
        return Point(x=min(1,max(0,a.x+t*dx)), y=min(1,max(0,a.y+t*dy)))
    return None


def barrier_for(force, terrain):
    if force.kind == "air":
        return False
    if force.kind == "fleet":
        return terrain.kind not in ("sea", "river") and terrain.shape == "polygon"
    return terrain.passability == "blocked"


def blocked(a, b, terrain):
    polygon = terrain.points
    hits = [p for p in (a,b) if inside(p, polygon)]
    hits += [p for c,d in zip(polygon, polygon[1:] + polygon[:1]) if (p := intersection(a,b,c,d)) is not None]
    return any(not any(distance(p, gate) <= 0.05 + 1e-9 for gate in terrain.crossings) for p in hits)


def position_at(force, time, pending):
    position = force.position
    for start, end, action in sorted(pending, key=lambda row: row[0]):
        if action.unit_id != force.id or action.kind not in ("move", "withdraw") or len(action.route) < 2 or time < start or end <= start:
            continue
        lengths = [distance(a,b) for a,b in zip(action.route, action.route[1:])]
        remaining = sum(lengths) * min(1,(time-start)/(end-start))
        position = action.route[-1]
        for a,b,length in zip(action.route, action.route[1:], lengths):
            if remaining <= length and length:
                fraction = remaining/length
                position = Point(x=a.x+(b.x-a.x)*fraction, y=a.y+(b.y-a.y)*fraction)
                break
            remaining -= length
    return position


def check_plan(blueprint: Blueprint, dossier: Dossier, script: Script, audio: AudioTiming | None = None) -> tuple[list[str], list[dict]]:
    issues, timeline = [], []
    clock = phrase_times(script, audio)
    known = {c.id for c in dossier.findings.claims}
    claims = {c.id: c.statement for c in dossier.findings.claims}
    speech = " ".join(p.text for s in script.draft.scenes for p in s.phrases)
    terrain_text = " ".join(c.statement for c in dossier.findings.claims if c.section == "terrain")
    for pattern,kind in ((r"\brocky\b","rocky_ground"),(r"\brivers?\b","river"),(r"\bforests?\b","forest"),
                         (r"\broads?\b","road"),(r"\bmountains?\b","mountain"),(r"\bmarsh\b","marsh")):
        if re.search(pattern,speech,re.I) and re.search(pattern,terrain_text,re.I) and not any(t.kind == kind for t in blueprint.terrain):
            issues.append(f"Narrated and researched terrain must be represented: {kind}.")
    scene_ids = [s.id for s in script.draft.scenes]
    if [s.scene_id for s in blueprint.scenes] != scene_ids:
        issues.append("Plan scenes must match script scenes exactly and in order.")
    if blueprint.scale != ("campaign" if script.scope == "war" else "tactical"):
        issues.append("Use campaign scale for a whole war and tactical scale for a battle.")
    for collection, label in ((blueprint.terrain, "terrain"), (blueprint.forces, "force")):
        if len({x.id for x in collection}) != len(collection):
            issues.append(f"Duplicate {label} IDs.")
        for item in collection:
            if not set(item.claim_ids) <= known:
                issues.append(f"{item.id}: unknown research claims.")
    for terrain in blueprint.terrain:
        if terrain.shape == "polygon" and len(terrain.points) < 3:
            issues.append(f"{terrain.id}: polygon needs at least three points.")
        if terrain.shape == "polygon" and abs(sum(a.x*b.y-b.x*a.y for a,b in zip(terrain.points, terrain.points[1:]+terrain.points[:1]))) < 1e-6:
            issues.append(f"{terrain.id}: polygon must enclose an area.")
        if terrain.shape == "polygon":
            edges = list(zip(terrain.points, terrain.points[1:]+terrain.points[:1]))
            for i,(a,b) in enumerate(edges):
                for j,(c,d) in enumerate(edges):
                    if j > i+1 and (i,j) != (0,len(edges)-1) and intersection(a,b,c,d) is not None:
                        issues.append(f"{terrain.id}: polygon must not intersect itself.")
        if terrain.passability == "blocked" and terrain.shape != "polygon":
            issues.append(f"{terrain.id}: blocked terrain must use a polygon, not an unbounded line.")
        if terrain.kind in ("sea", "river", "mountain", "wall") and terrain.passability != "blocked":
            issues.append(f"{terrain.id}: water, walls and mountains must be explicit barriers.")
        if terrain.crossings and not re.search(r"\b(bridge|ford|crossing|pass|gate)\b", " ".join(claims.get(i, "") for i in terrain.claim_ids), re.I):
            issues.append(f"{terrain.id}: crossings require supporting evidence.")
    forces = {f.id: f for f in blueprint.forces}
    introduced = {}
    for force in forces.values():
        if force.introduced_at.phrase_id not in clock:
            issues.append(f"{force.id}: introduction references an unknown phrase.")
        else:
            introduced[force.id] = cue_time(force.introduced_at,clock)
            timeline.append({"action_id": f"intro-{force.id}", "unit_id": force.id, "kind": "introduce",
                             "start_sec": round(introduced[force.id],4), "end_sec": round(introduced[force.id],4)})
        if blueprint.scale == "tactical" and force.kind not in ("fleet", "air") and force.subgroups < 3:
            issues.append(f"{force.id}: tactical armies need at least three independently animated subgroups.")
        for terrain in blueprint.terrain:
            if barrier_for(force, terrain) and terrain.shape == "polygon" and blocked(force.position, force.position, terrain):
                issues.append(f"{force.id}: starting position is inside incompatible terrain {terrain.id}.")
    action_ids, pending = set(), []
    for scene in blueprint.scenes:
        if abs(scene.focus.x - 0.5) + scene.view_width/2 > 0.5 + 1e-6 or abs(scene.focus.y - 0.5) + scene.view_width/2 > 0.5 + 1e-6:
            issues.append(f"{scene.scene_id}: camera viewport leaves the normalized world.")
        for action in scene.actions:
            if action.id in action_ids:
                issues.append("Duplicate action IDs.")
            action_ids.add(action.id)
            if not set(action.claim_ids) <= known:
                issues.append(f"{action.id}: unknown research claims.")
            if action.unit_id not in forces or (action.target_id and action.target_id not in forces):
                issues.append(f"{action.id}: unknown force reference.")
                continue
            if any(c.phrase_id not in clock or c.phrase_id.rsplit('.p',1)[0] != scene.scene_id for c in (action.start, action.end)):
                issues.append(f"{action.id}: anchors must reference phrases in this scene.")
                continue
            start, end = cue_time(action.start, clock), cue_time(action.end, clock)
            if start < introduced.get(action.unit_id, math.inf) - 1e-6 or (action.target_id and start < introduced.get(action.target_id, math.inf) - 1e-6):
                issues.append(f"{action.id}: actor or target has not been introduced yet.")
            if end <= start:
                issues.append(f"{action.id}: action must have positive duration.")
            if action.kind == "engage" and (not action.target_id or forces[action.target_id].side == forces[action.unit_id].side):
                issues.append(f"{action.id}: engagement requires an opposing target.")
            if action.formation != "campaign" and blueprint.scale == "campaign":
                issues.append(f"{action.id}: whole-war markers must use campaign formation.")
            if action.kind in ("move", "withdraw") and len(action.route) < 2:
                issues.append(f"{action.id}: movement needs a continuous route of at least two points.")
            text = " ".join(claims.get(i,"") for i in action.claim_ids)
            if action.kind == "withdraw" and not re.search(r"retreat|withdr(?:aw|ew)|escape|fled|flee|evacuat|fell\s+back|fall\s+back",text,re.I):
                issues.append(f"{action.id}: withdrawal needs explicit movement evidence; surrender alone is not a retreat.")
            if action.kind == "move" and not re.search(r"advanc|attack|invad|cross|march|dispatch|deploy|retreat|withdr(?:aw|ew)|sail|mov|send|sent|land|flank|encircl|reinforc",text,re.I):
                issues.append(f"{action.id}: movement needs a cited movement event, not just a force count or outcome.")
            if action.kind not in ("move", "withdraw") and action.route:
                issues.append(f"{action.id}: non-movement actions cannot relocate a force.")
            pending.append((start, end, action))
    positions = {f.id: f.position for f in forces.values()}
    moving_until, removed_at = {}, {}
    for start, end, action in sorted(pending, key=lambda row: (row[0], row[2].id)):
        if start >= removed_at.get(action.unit_id, math.inf):
            issues.append(f"{action.id}: a faded force cannot silently reappear.")
        if action.kind == "fade":
            removed_at[action.unit_id] = end
        if action.target_id and start >= removed_at.get(action.target_id, math.inf):
            issues.append(f"{action.id}: target force has already faded.")
        if action.kind == "engage" and action.target_id and blueprint.scale == "tactical" and forces[action.unit_id].kind in ("infantry", "cavalry", "army"):
            if distance(position_at(forces[action.unit_id], start, pending), position_at(forces[action.target_id], start, pending)) > 0.08:
                issues.append(f"{action.id}: ground engagement starts before live positions reach contact.")
        if action.kind in ("move", "withdraw") and len(action.route) >= 2:
            if start < moving_until.get(action.unit_id, -1) - 1e-6:
                issues.append(f"{action.id}: overlapping movement orders for the same force.")
            if distance(action.route[0], positions[action.unit_id]) > 0.01:
                issues.append(f"{action.id}: route teleports from the previous position.")
            for terrain in blueprint.terrain:
                if barrier_for(forces[action.unit_id], terrain) and terrain.shape == "polygon":
                    if any(blocked(a,b,terrain) for a,b in zip(action.route, action.route[1:])):
                        issues.append(f"{action.id}: route crosses incompatible terrain {terrain.id}.")
            positions[action.unit_id], moving_until[action.unit_id] = action.route[-1], end
        timeline.append({"action_id": action.id, "unit_id": action.unit_id, "kind": action.kind,
                         "start_sec": round(start,4), "end_sec": round(end,4)})
    total = max(end for _,end in clock.values())
    if not 60 <= total <= 150:
        issues.append("Narration timing is outside the allowed 60–150 second range.")
    issues.extend(blueprint.blocking_gaps)
    return list(dict.fromkeys(issues)), sorted(timeline,key=lambda row:(row["start_sec"],row["action_id"]))


def fit_camera(scene):
    half = scene.view_width/2
    return scene.model_copy(update={"focus": Point(x=min(1-half,max(half,scene.focus.x)),
                                                  y=min(1-half,max(half,scene.focus.y)))})


def context(dossier, script):
    return {"topic": dossier.selected.topic, "scope": script.scope,
            "claims": [c.model_dump(exclude={"evidence"}) for c in dossier.findings.claims],
            "terrain": [t.model_dump() for t in dossier.findings.terrain],
            "events": [e.model_dump() for e in dossier.findings.events],
            "gaps": dossier.findings.gaps, "script": script.draft.model_dump()}


def validate_inputs(dossier, script, require_ready=True):
    if require_ready and (dossier.readiness != "ready" or dossier.findings.blocking_gaps or script.status != "ready" or script.issues):
        raise DirectionError("Research and script must be ready with no blocking issues.")
    if script.dossier_sha256 != fingerprint(dossier) or script.topic != dossier.selected.topic or script.scope != dossier.selected.scope:
        raise DirectionError("Script and research identity/version do not match.")
    validate_evidence(dossier.findings, dossier.sources)
    if require_ready and check_draft(script.draft, dossier, script.target_seconds):
        raise DirectionError("Saved script fails current writer checks; revise it before directing.")


def retime(plan, dossier, script, audio):
    validate_inputs(dossier, script)
    if plan.script_sha256 != fingerprint(script) or plan.dossier_sha256 != fingerprint(dossier):
        raise DirectionError("Plan input versions do not match for retiming.")
    issues, timeline = check_plan(plan.blueprint, dossier, script, audio)
    if not plan.review or plan.review.status != "pass" or plan.review.artifact_sha256 != fingerprint(plan.blueprint):
        issues.append("Plan needs a matching passing quality review before retiming.")
    return plan.model_copy(update={"created_at": datetime.now(timezone.utc), "parent_plan_sha256": fingerprint(plan),
        "status": "needs_revision" if issues else "ready", "issues": issues, "timing_basis": "measured",
        "duration_seconds": round(max(e for _,e in phrase_times(script,audio).values()),4),
        "timeline": [] if issues else timeline, "changed_scene_ids": [], "model_calls": 0, "models_used": []})


class DirectorAgent:
    def __init__(self, model):
        self.model = model

    def direct(self, dossier, script, request=None, previous=None, audio=None):
        validate_inputs(dossier, script)
        request = request or DirectionRequest()
        clock = phrase_times(script, audio)
        if previous and (previous.script_sha256 != fingerprint(script) or previous.dossier_sha256 != fingerprint(dossier)):
            raise DirectionError("Previous plan uses different input versions.")
        if request.scene_id and (not previous or request.scene_id not in {s.scene_id for s in previous.blueprint.scenes}):
            raise DirectionError("A scene edit requires a previous plan containing that scene.")
        calls = 0
        self.model.used.clear()
        def consume():
            nonlocal calls
            if calls >= request.max_model_calls:
                raise DirectionError("Director/reviewer model budget exhausted.")
            calls += 1
        packet = context(dossier, script)
        prompt = ("Direct a simple descriptive 9:16 military-history map video for PixiJS. Return a Blueprint. "
            "Use ONLY supplied historical facts. Distinguish schematic placement from historical evidence: "
            "layout_kind=schematic and explain limits in layout_note. World x/y are normalized 0..1; "
            "both axes represent the full 9:16 world, not real geographic units. Terrain is locked for "
            "the whole video. Terrain kind accepts new lowercase identifiers such as desert or cliff; "
            "water still uses sea/river, with a specific label and visual motif later. "
            "New land kinds keep explicit passability; no decorative invented geography. "
            "Depict narrated terrain: rocky ground as rocky_ground, roads as road lines, "
            "not just a generic island rectangle. No decorative forests or mountains without sources. "
            "Use plain for island landmass, not settlement for a whole island group. "
            "Cite actual claim IDs on terrain, forces and actions. Never invent hidden "
            "routes, combat, casualties, motives, precise formations or historical times. When research "
            "only supports a strategic overview, highlight places and dispatch routes rather than "
            "inventing battles. Use scale campaign for a war, tactical for a battle. Units are symbolic "
            "groups, never exact troop counts: 3-8 subgroups for tactical ground forces. Overlap different "
            "forces' movements where supported; don't move an army as one rigid rectangle. Routes are "
            "continuous polylines starting at the last position; renderer will handle individual "
            "followers, turning and stagger. No teleports or cross-scene position resets. Explain every "
            "force introduction with introduced_at (a real phrase cue) and introduction_reason. Forces "
            "cannot act or be targeted before introduction. Do not substitute a later task force for "
            "an earlier garrison. Withdrawal arrows require explicit retreat/evacuation evidence; "
            "surrender should be highlighted or faded, not portrayed as an undocumented retreat. "
            "action's cause and consequence. Use move/withdraw only with >=2 waypoints; engage requires "
            "an opposing target. highlight/fade have empty routes. Water/mountains/walls are blocked "
            "polygons; crossings need explicit source evidence. Ground forces cannot traverse them; "
            "Do not draw a sea polygon underneath land units: polygon holes/layer overrides are not "
            "supported. Use separate non-overlapping water/land areas. "
            "fleet markers can cross sea, never land polygons. Camera focus/view_width define a square "
            "fraction of the normalized 9:16 world; keep its entire bounds inside 0..1. Keep <=3 short "
            "labels per scene; avoid invented decorative terrain. Every script scene appears once, in "
            "order. Anchor action start/end to existing phrase IDs and fraction 0..1 within that phrase; "
            "these are presentation timings, not historical timestamps. Prefer 1-3 purposeful actions "
            "per scene. Static focus/highlight is fine when facts don't support movement. Campaign actions "
            "use formation=campaign. gaps records ordinary uncertainty; blocking_gaps contains ONLY "
            "missing evidence preventing a faithful short overview, not every omitted optional engagement. "
            f"User notes: {request.notes!r}\nPHRASES: {json.dumps(clock)}\nCONTEXT: {json.dumps(packet, ensure_ascii=False)}")
        if previous:
            prompt += "\nPREVIOUS: " + previous.blueprint.model_dump_json()
        if request.scene_id:
            prompt += f"\nReturn only ScenePlan for {request.scene_id}; terrain, forces and all other scenes are fixed."
        blueprint, review, issues, timeline = None, None, [], []
        for attempt in range(2):
            try:
                result = self.model.generate(prompt, ScenePlan if request.scene_id else Blueprint, consume)
            except (ProviderError, DirectionError):
                if blueprint is None:
                    raise
                issues.append("Plan repair unavailable; review required.")
                break
            if request.scene_id:
                blueprint = previous.blueprint.model_copy(deep=True)
                if result.scene_id != request.scene_id:
                    issues = ["Scene edit returned the wrong scene ID."]
                else:
                    index = next(i for i,s in enumerate(blueprint.scenes) if s.scene_id == request.scene_id)
                    blueprint.scenes[index] = fit_camera(result)
                    issues, timeline = check_plan(blueprint, dossier, script, audio)
            else:
                blueprint = result
                blueprint.scenes = [fit_camera(s) for s in blueprint.scenes]
                issues, timeline = check_plan(blueprint, dossier, script, audio)
            review = None
            if not issues:
                try:
                    review = ReviewerAgent(self.model).review(blueprint, packet, consume)
                    issues = review.local_issues + [i.message for i in review.findings.issues if i.severity == "blocking"]
                except (ProviderError, DirectionError):
                    issues = ["Quality review unavailable; human review required."]
            if not issues or attempt == 1 or calls >= request.max_model_calls:
                break
            prompt += "\nREPAIR ISSUES: " + json.dumps(issues) + "\nPLAN: " + blueprint.model_dump_json()
        changed = [s.scene_id for s in blueprint.scenes if not previous or s.model_dump() != next(
            (p.model_dump() for p in previous.blueprint.scenes if p.scene_id == s.scene_id), None)]
        return Plan(topic=script.topic, dossier_sha256=fingerprint(dossier), script_sha256=fingerprint(script),
            parent_plan_sha256=fingerprint(previous) if previous else None, request=request, blueprint=blueprint,
            status="ready" if not issues and review and review.status == "pass" else "needs_revision",
            issues=list(dict.fromkeys(issues)), review=review, timing_basis="measured" if audio else "estimated",
            duration_seconds=round(max(e for _,e in clock.values()),4), timeline=timeline if not issues else [],
            changed_scene_ids=changed, model_calls=calls, models_used=list(dict.fromkeys(self.model.used)))
