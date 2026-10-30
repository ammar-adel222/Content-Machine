"""CLI entry point: discover, research, save. No publishing side effects."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pydantic import ValidationError

from .agent import ResearchAgent, ResearchError
from .models import Discovery, ResearchRequest
from .providers import LanguageModel, ProviderError, Web, load_env
from .storage import Cache, past_topics, save


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Source-backed research for war tactics videos")
    topics = result.add_mutually_exclusive_group()
    topics.add_argument("--topic", help="Research this exact battle or war")
    topics.add_argument("--direction", help="Discover topics within this theme")
    topics.add_argument("--selection-file", type=Path, help="Resume a saved discovery.json")
    result.add_argument("--scope", choices=["auto", "battle", "war"], default="auto")
    result.add_argument("--target-seconds", type=int, default=105)
    result.add_argument("--exclude", action="append", default=[])
    result.add_argument("--as-of", help="Information cutoff YYYY-MM-DD (default UTC date)")
    result.add_argument("--env-file", type=Path, default=Path(".env"))
    result.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    result.add_argument("--fallback", choices=["gemini", "groq"], help="Optional second provider")
    result.add_argument("--model", help="Override primary provider's model")
    result.add_argument("--output", type=Path, default=Path("output/research"))
    result.add_argument("--max-searches", type=int, help="Search budget (default 10)")
    result.add_argument("--max-extract-urls", type=int, help="Extraction URL budget (default 5)")
    result.add_argument("--max-model-calls", type=int, help="Model-attempt budget (default 5)")
    result.add_argument("--discover-only", action="store_true")
    result.add_argument("--no-cache", action="store_true")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.env_file.exists():
            load_env(args.env_file)
        providers = []
        for index, provider in enumerate(dict.fromkeys([args.provider, args.fallback])):
            if provider is None:
                continue
            model = (args.model if index == 0 else None) or os.environ.get(
                f"{provider.upper()}_MODEL", {"gemini": "gemini-3.5-flash-lite", "groq": "qwen/qwen3.8-27b",
                    "openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free"}[provider])
            providers.append((provider, model, os.environ.get(f"{provider.upper()}_API_KEY", "")))
        agent = ResearchAgent(Web(os.environ.get("TAVILY_API_KEY", "")), LanguageModel(providers),
                              None if args.no_cache else Cache(args.output / ".cache"))
        budgets = {name: getattr(args, name) for name in ("max_searches", "max_extract_urls", "max_model_calls")
                   if getattr(args, name) is not None}
        if args.selection_file:
            discovery = Discovery.model_validate_json(args.selection_file.read_text(encoding="utf-8"))
            discovery.request = ResearchRequest(**{**discovery.request.model_dump(), **budgets})
        else:
            parameters = dict(mode="specific" if args.topic else "direction" if args.direction else "auto",
                topic=args.topic or args.direction or "", scope=args.scope, target_seconds=args.target_seconds,
                excluded_topics=list(dict.fromkeys(args.exclude + past_topics(args.output))), **budgets)
            if args.as_of:
                parameters["as_of"] = args.as_of
            discovery = agent.discover(ResearchRequest(**parameters))
            saved = save(discovery, args.output)
            print(f"Discovery saved: {saved / 'discovery.json'}")
        if args.discover_only:
            return 0
        dossier = agent.research(discovery)
        directory = save(dossier, args.output)
        print(f"Research {dossier.readiness}: {directory / 'report.md'}")
        return 0 if dossier.readiness == "ready" else 2
    except (ValueError, OSError, ResearchError, ProviderError) as error:
        # Validation details can contain source text; avoid dumping provider payloads.
        message = "Invalid structured input or configuration." if isinstance(error, ValidationError) else str(error)
        print(f"Research failed: {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
