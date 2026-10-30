"""Immutable script versions and a provider-neutral TTS handoff."""

import json
import re
from pathlib import Path
from uuid import uuid4

from .models import Script


def tts_plan(script: Script) -> dict:
    chunks = []
    for scene in script.draft.scenes:
        for index, phrase in enumerate(scene.phrases, 1):
            emphasis = ", ".join(phrase.emphasis) or "Follow natural sentence stress"
            chunks.append({"id": f"{scene.id}.p{index}", "scene_id": scene.id, "text": phrase.text,
                "direction": f"{script.draft.narrator_style} Tone: {scene.tone}. {scene.delivery_notes} "
                             f"Pace: {phrase.pace}. Emphasize: {emphasis}.",
                "pause_after_ms": phrase.pause_after_ms, "claim_ids": scene.claim_ids})
    return {"schema_version": "1.0", "status": script.status, "topic": script.topic,
            "dossier_sha256": script.dossier_sha256,
            "pronunciations": [p.model_dump() for p in script.draft.pronunciations],
            "timing_note": "Pauses are assembly targets. Measure generated speech before synchronizing visuals.",
            "chunks": chunks}


def markdown(script: Script) -> str:
    d = script.draft
    lines = [f"# {d.title}", "", f"**Topic:** {script.topic} | **Status:** {script.status}",
             f"**Words:** {script.word_count} | **Estimated:** {script.estimated_seconds}s | **Target:** {script.target_seconds}s",
             "", "## Narration", ""]
    lines += [" ".join(p.text for s in d.scenes for p in s.phrases), "", "## Voice direction", "", d.narrator_style, ""]
    for scene in d.scenes:
        lines += [f"### {scene.id}: {scene.role}", "", f"**Tone:** {scene.tone}", scene.delivery_notes,
                  f"**Visual intent:** {scene.visual_intent}", f"**Research claims:** {', '.join(scene.claim_ids)}", ""]
        for phrase in scene.phrases:
            lines += [f"> {phrase.text}", "", f"Pace: {phrase.pace}; emphasis: {', '.join(phrase.emphasis) or 'natural'}; "
                      f"pause afterward: {phrase.pause_after_ms}ms.", ""]
    lines += ["## Pronunciation guide (advisory)", ""]
    lines += [f"- {p.term}: {p.say_as}" for p in d.pronunciations] or ["- None supplied."]
    lines += ["", "## Caption", "", d.caption, "", "## Review and limitations", ""]
    lines += [f"- {item}" for item in script.issues + script.warnings]
    lines += ["", "## Version and provenance", "", f"Research SHA-256: `{script.dossier_sha256}`",
              f"Parent script SHA-256: `{script.parent_script_sha256 or 'initial version'}`",
              f"Changed scenes: {', '.join(script.changed_scene_ids) or 'none'}",
              f"Model attempts: {script.model_calls}; models: {', '.join(script.models_used)}", ""]
    return "\n".join(lines)


def save(script: Script, root: Path) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", script.topic).strip("-").lower()[:70] or "topic"
    directory = root / f"{slug}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (directory / "script.md").write_text(markdown(script), encoding="utf-8")
    (directory / "tts_plan.json").write_text(json.dumps(tts_plan(script), ensure_ascii=False, indent=2), encoding="utf-8")
    return directory
