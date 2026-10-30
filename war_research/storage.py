"""Disposable web cache and immutable run folders; no database required."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from uuid import uuid4

from .models import Discovery, Dossier


class Cache:
    def __init__(self, root: Path, ttl_seconds: int = 86400):
        self.root, self.ttl = root, ttl_seconds

    def get_or_call(self, operation: str, arguments: object, call):
        # Only public search arguments go into keys; never HTTP headers or credentials.
        key = hashlib.sha256(json.dumps([operation, arguments], sort_keys=True).encode()).hexdigest()
        path = self.root / f"{key}.json"
        try:
            if time.time() - path.stat().st_mtime < self.ttl:
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        result = call()
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return result


def markdown(dossier: Dossier) -> str:
    f = dossier.findings
    lines = [f"# {dossier.selected.topic}", "", f"**Angle:** {dossier.selected.angle}",
             f"**Scope:** {dossier.selected.scope} | **Era:** {f.era}",
             f"**Target:** {f.recommended_seconds}s | **Readiness:** {dossier.readiness}",
             f"**Information cutoff:** {dossier.request.as_of}", "", f.summary, ""]
    for section in dict.fromkeys(claim.section for claim in f.claims):
        lines += [f"## {section.title()}", ""]
        for claim in f.claims:
            if claim.section == section:
                refs = ", ".join(f"{e.source_id}:{e.passage_id}" for e in claim.evidence)
                lines += [f"- **{claim.id} [{claim.status}]** {claim.statement} ({refs})"]
        lines.append("")
    lines += ["## Terrain for the director", ""]
    for feature in f.terrain:
        lines += [f"- **{feature.name}:** {feature.description} {feature.spatial_relation}",
                  f"  Effect: {feature.tactical_effect} ({', '.join(feature.claim_ids)})"]
    lines += ["", "## Event sequence", ""]
    for event in sorted(f.events, key=lambda e: e.order):
        lines += [f"{event.order}. **{event.title}** ({event.time or 'time uncertain'}): {event.action}",
                  f"   Actors: {', '.join(event.actors)}. Location: {event.location}.",
                  f"   Reason: {event.reason} Consequence: {event.consequence}",
                  f"   Evidence: {', '.join(event.claim_ids)}."]
    lines += ["", "## Writer handoff", "",
              f"Essential claims: {', '.join(f.essential_claim_ids) or 'None'}",
              f"Optional claims: {', '.join(f.optional_claim_ids) or 'None'}",
              "", "## Gaps and warnings", ""]
    lines += [f"- **Blocking:** {gap}" for gap in f.blocking_gaps]
    lines += [f"- {gap}" for gap in dict.fromkeys(f.gaps + dossier.warnings) if gap not in f.blocking_gaps] or (["- None reported."] if not f.blocking_gaps else [])
    lines += ["", "## Sources", ""]
    for source in dossier.sources:
        lines += [f"- **{source.id}:** [{source.title}]({source.url}) — {source.kind}; "
                  f"{'page text' if source.full_text else 'search excerpt'}; retrieved {source.retrieved_at.isoformat()}"]
    lines += ["", "## Evidence excerpts", ""]
    citations = {}
    for claim in f.claims:
        for evidence in claim.evidence:
            citations.setdefault((evidence.source_id, evidence.passage_id, evidence.quote), []).append(claim.id)
    for (source_id, passage_id, quote), claim_ids in citations.items():
        lines += [f"- {source_id}:{passage_id} ({', '.join(claim_ids)}): {json.dumps(quote, ensure_ascii=False)}"]
    lines += ["", "## Topic selection", "", dossier.selected.reason,
              f"Selection evidence: {', '.join(dossier.selected.source_ids)}", ""]
    for source in dossier.selection_sources:
        lines += [f"- **{source.id}:** [{source.title}]({source.url})"]
    if dossier.alternatives:
        lines += ["", "Alternatives considered:", ""]
        lines += [f"- {c.topic}: {c.reason} (score {c.scores.total}/25)" for c in dossier.alternatives]
    return "\n".join(lines) + "\n"


def save(result: Discovery | Dossier, root: Path) -> Path:
    name = result.selected.topic if isinstance(result, Dossier) else result.selection.candidates[0].topic
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()[:70] or "topic"
    directory = root / f"{slug}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    filename = "dossier.json" if isinstance(result, Dossier) else "discovery.json"
    (directory / filename).write_text(result.model_dump_json(indent=2), encoding="utf-8")
    if isinstance(result, Dossier):
        (directory / "report.md").write_text(markdown(result), encoding="utf-8")
    return directory


def past_topics(root: Path) -> list[str]:
    """Only completed, usable dossiers count as covered; failed drafts can be retried."""
    topics = []
    for path in sorted(root.glob("*/dossier.json")):
        try:
            data = Dossier.model_validate_json(path.read_text(encoding="utf-8"))
            if data.readiness == "ready":
                topics.append(data.selected.topic)
        except (ValueError, OSError):
            continue
    return list(dict.fromkeys(topics))
