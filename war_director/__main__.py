import argparse
import os
from pathlib import Path
from pydantic import ValidationError
from war_research.agent import ResearchError
from war_research.models import Dossier
from war_research.providers import LanguageModel, ProviderError, load_env
from war_writer.models import Script
from .agent import DirectorAgent, DirectionError, retime
from .models import AudioTiming, DirectionRequest, Plan
from .storage import save


def main(argv=None):
    p = argparse.ArgumentParser(description="Plan a battle/war video from saved research and narration")
    p.add_argument("dossier", type=Path)
    p.add_argument("script", type=Path)
    p.add_argument("--previous", type=Path)
    p.add_argument("--scene")
    p.add_argument("--notes", default="")
    p.add_argument("--audio-timing", type=Path)
    p.add_argument("--retime", action="store_true", help="Recompile a previous plan with measured audio; no model calls")
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--model", default=None)
    p.add_argument("--max-model-calls", type=int, default=4)
    p.add_argument("--output", type=Path, default=Path("output/directing"))
    args = p.parse_args(argv)
    try:
        dossier = Dossier.model_validate_json(args.dossier.read_text(encoding="utf-8"))
        script = Script.model_validate_json(args.script.read_text(encoding="utf-8"))
        previous = Plan.model_validate_json(args.previous.read_text(encoding="utf-8")) if args.previous else None
        audio = AudioTiming.model_validate_json(args.audio_timing.read_text(encoding="utf-8")) if args.audio_timing else None
        request = DirectionRequest(notes=args.notes, scene_id=args.scene, max_model_calls=args.max_model_calls)
        if args.retime:
            if not previous or not audio or args.scene or args.notes:
                raise DirectionError("Retiming needs --previous and --audio-timing, without scene edits or notes.")
            plan = retime(previous, dossier, script, audio)
        else:
            if args.env_file.exists():
                load_env(args.env_file)
            model = LanguageModel([("gemini", args.model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                                    os.environ.get("GEMINI_API_KEY", ""))])
            plan = DirectorAgent(model).direct(dossier, script, request, previous, audio)
        directory = save(plan, args.output)
        print(f"Director {plan.status}: {directory/'storyboard.md'}")
        return 0 if plan.status == "ready" else 2
    except (ValueError, OSError, ResearchError, DirectionError, ProviderError) as error:
        print("Directing failed:", "Invalid structured input or configuration." if isinstance(error, ValidationError) else str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
