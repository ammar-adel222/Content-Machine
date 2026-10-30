import argparse
import os
from functools import partial
from pathlib import Path
from war_director.models import AudioTiming, Plan
from war_research.models import Dossier
from war_research.providers import LanguageModel, load_env, request_json
from war_writer.models import Script
from .agent import ContentAgent, Library, OfflineModel
from .models import Manifest
from .storage import save
from .preview import render_preview


def main(argv=None):
    p = argparse.ArgumentParser(description="Design missing visuals and compile a PixiJS map playback bundle")
    p.add_argument("dossier",type=Path)
    p.add_argument("script",type=Path)
    p.add_argument("plan",type=Path)
    p.add_argument("--manifest",type=Path,help="Reuse/edit a saved visual manifest")
    p.add_argument("--audio-timing",type=Path)
    p.add_argument("--env-file",type=Path,default=Path(".env"))
    p.add_argument("--model")
    p.add_argument("--provider",choices=("gemini","groq","openrouter"),default="groq")
    p.add_argument("--review-provider",choices=("gemini","groq","openrouter"))
    p.add_argument("--review-model",help="Choose a vision-capable reviewer when the designer is text-only")
    p.add_argument("--max-model-calls",type=int,default=16)
    p.add_argument("--library",type=Path,default=Path("output/visual-library/atlas-ink-v1"))
    p.add_argument("--output",type=Path,default=Path("output/content"))
    p.add_argument("--pixi",type=Path,default=Path(__file__).resolve().parents[1]/"renderer/node_modules/pixi.js/dist/pixi.min.js")
    args = p.parse_args(argv)
    try:
        if args.env_file.exists():
            load_env(args.env_file)
        dossier = Dossier.model_validate_json(args.dossier.read_text(encoding="utf-8"))
        script = Script.model_validate_json(args.script.read_text(encoding="utf-8"))
        plan = Plan.model_validate_json(args.plan.read_text(encoding="utf-8"))
        manifest = Manifest.model_validate_json(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
        audio = AudioTiming.model_validate_json(args.audio_timing.read_text(encoding="utf-8")) if args.audio_timing else None
        defaults={"gemini":"gemini-3.5-flash-lite","groq":"qwen/qwen3.8-27b","openrouter":"nvidia/nemotron-3.5-super-vl:free"}
        def client(provider,selected):
            key=os.environ.get(provider.upper()+"_API_KEY", "")
            name=selected or defaults[provider]
            # A free visual build can wait for a short TPM reset; research/writer
            # keep their fast fallback policy and the shared five-second default.
            return LanguageModel([(provider,name,key)],transport=partial(request_json,max_retry_wait=60)) if key else OfflineModel()
        model=client(args.provider,args.model or os.environ.get("CONTENT_MODEL"))
        review_model=args.review_model or os.environ.get("CONTENT_REVIEW_MODEL")
        reviewer=client(args.review_provider or args.provider,review_model) if args.review_provider or review_model else model
        result = ContentAgent(model,Library(args.library),preview=render_preview,reviewer=reviewer).build(dossier,script,plan,manifest=manifest,audio=audio,max_model_calls=args.max_model_calls)
        directory = save(result,plan,script,args.output,audio=audio,pixi=args.pixi)
        print(f"Content {result.status}: {directory/'report.md'}")
        return 0 if result.status == "ready" else 2
    except (ValueError,RuntimeError,OSError) as error:
        # Structured validation errors can contain input data: keep the CLI error safe.
        from pydantic import ValidationError
        print("Content failed:","Invalid structured input." if isinstance(error,ValidationError) else str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
