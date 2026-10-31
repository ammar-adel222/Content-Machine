"""Run one unit brief without a dossier, script or storyboard."""
import argparse
import os
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from war_research.providers import LanguageModel, load_env
from .agent import Library, OfflineModel
from .models import Brief
from .preview import render_preview
from .units import UnitDesigner, save_unit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Design and visually review any missing map unit")
    parser.add_argument("brief", type=Path, help="JSON Brief: category=unit, concept, description")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--library", type=Path, default=Path("output/visual-library/atlas-ink-v1"))
    parser.add_argument("--output", type=Path, default=Path("output/units"))
    parser.add_argument("--model")
    parser.add_argument("--max-model-calls", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        brief = Brief.model_validate_json(args.brief.read_text(encoding="utf-8"))
        if args.env_file.exists():
            load_env(args.env_file)
        key = os.environ.get("GROQ_API_KEY", "")
        name = args.model or os.environ.get("CONTENT_MODEL", "qwen/qwen3.8-27b")
        model = LanguageModel([("groq", name, key)]) if key else OfflineModel()
        result = UnitDesigner(model, Library(args.library), preview=render_preview).create(
            brief, max_model_calls=args.max_model_calls)
        root = save_unit(result, args.output / uuid4().hex, render_preview)
        print(f"Unit {'ready' if result.asset else 'needs_revision'}: {root / 'report.md'}")
        return 0 if result.asset else 2
    except (ValueError, RuntimeError, OSError) as error:
        print("Unit failed:", "Invalid structured input." if isinstance(error, ValidationError) else str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
