"""Run a writer or targeted revision against a saved research dossier."""

import argparse
import os
from pathlib import Path

from pydantic import ValidationError

from war_research.models import Dossier
from war_research.providers import LanguageModel, ProviderError, load_env

from .agent import WritingAgent, WritingError
from .models import Script, WritingRequest
from .storage import save


def parser():
    p = argparse.ArgumentParser(description="Write directed narration from a saved research dossier")
    p.add_argument("dossier", type=Path)
    p.add_argument("--previous", type=Path, help="Previous script.json for a revision")
    p.add_argument("--scene", help="Revise only this scene; requires --previous and --notes")
    p.add_argument("--notes", default="")
    p.add_argument("--target-seconds", type=int)
    p.add_argument("--max-model-calls", type=int, default=4)
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--provider", choices=["gemini", "openrouter", "groq"], default="gemini")
    p.add_argument("--model", help="Override the provider's model ID")
    p.add_argument("--fallback", choices=["openrouter", "gemini", "groq"])
    p.add_argument("--output", type=Path, default=Path("output/writing"))
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        dossier = Dossier.model_validate_json(args.dossier.read_text(encoding="utf-8"))
        previous = Script.model_validate_json(args.previous.read_text(encoding="utf-8")) if args.previous else None
        request = WritingRequest(target_seconds=args.target_seconds, notes=args.notes,
                                 scene_id=args.scene, max_model_calls=args.max_model_calls)
        if args.env_file.exists():
            load_env(args.env_file)
        providers = []
        defaults = {"openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "gemini": "gemini-3.5-flash-lite", "groq": "qwen/qwen3.8-27b"}
        for index, provider in enumerate(dict.fromkeys([args.provider, args.fallback])):
            if provider:
                model = (args.model if index == 0 else None) or os.environ.get(f"{provider.upper()}_MODEL", defaults[provider])
                providers.append((provider, model, os.environ.get(f"{provider.upper()}_API_KEY", "")))
        script = WritingAgent(LanguageModel(providers)).write(dossier, request, previous)
        directory = save(script, args.output)
        print(f"Script {script.status}: {directory / 'script.md'}")
        return 0 if script.status == "ready" else 2
    except (ValueError, OSError, ProviderError, WritingError) as error:
        message = "Invalid script, research, or configuration." if isinstance(error, ValidationError) else str(error)
        print(f"Writing failed: {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
