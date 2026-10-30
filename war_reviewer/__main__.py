"""Standalone script or director review, reusable by future workflow orchestration."""
import argparse
import os
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from war_research.agent import ResearchError
from war_research.models import Dossier
from war_research.providers import LanguageModel, ProviderError, load_env
from war_writer.models import Script
from .agent import ReviewerAgent


def main(argv=None):
    p = argparse.ArgumentParser(description="Review a saved script or director plan against its research")
    p.add_argument("dossier", type=Path)
    p.add_argument("script", type=Path)
    p.add_argument("--plan", type=Path)
    p.add_argument("--audio-timing", type=Path)
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--model")
    p.add_argument("--output", type=Path, default=Path("output/reviews"))
    args = p.parse_args(argv)
    try:
        from war_director.agent import DirectionError, check_plan, context, validate_inputs
        from war_director.models import AudioTiming, Plan
        from war_writer.agent import check_draft
        dossier = Dossier.model_validate_json(args.dossier.read_text(encoding="utf-8"))
        script = Script.model_validate_json(args.script.read_text(encoding="utf-8"))
        validate_inputs(dossier, script, require_ready=False)
        local = check_draft(script.draft, dossier, script.target_seconds) + script.issues + dossier.findings.blocking_gaps
        if dossier.readiness != "ready":
            local.append("Research is marked incomplete.")
        artifact = script.draft
        if args.plan:
            plan = Plan.model_validate_json(args.plan.read_text(encoding="utf-8"))
            from war_writer.agent import fingerprint
            if plan.script_sha256 != fingerprint(script) or plan.dossier_sha256 != fingerprint(dossier):
                raise DirectionError("Plan input versions do not match this research and script.")
            artifact = plan.blueprint
            audio = AudioTiming.model_validate_json(args.audio_timing.read_text(encoding="utf-8")) if args.audio_timing else None
            if plan.timing_basis == "measured" and not audio:
                raise DirectionError("Reviewing a measured plan requires --audio-timing.")
            plan_issues, _ = check_plan(artifact, dossier, script, audio)
            local += plan_issues
        if args.env_file.exists():
            load_env(args.env_file)
        model = LanguageModel([("gemini", args.model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                                os.environ.get("GEMINI_API_KEY", ""))])
        review = ReviewerAgent(model).review(artifact, context(dossier, script), lambda: None, local)
        directory = args.output/uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        (directory/"review.json").write_text(review.model_dump_json(indent=2), encoding="utf-8")
        messages = review.local_issues + [i.message for i in review.findings.issues]
        (directory/"review.md").write_text("# Quality review\n\nStatus: **" + review.status + "**\n\n" +
            "\n".join("- " + m for m in messages) + "\n\nPlan/text review only; no rendered video or audio was inspected.\n", encoding="utf-8")
        print(f"Review {review.status}: {directory/'review.md'}")
        return 0 if review.status == "pass" else 2
    except (ValueError, OSError, ResearchError, RuntimeError) as error:
        print("Review failed:", "Invalid structured input or configuration." if isinstance(error, ValidationError) else str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
