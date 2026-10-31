import argparse
import os
from pathlib import Path
from pydantic import ValidationError
from war_content.agent import OfflineModel
from war_research.providers import LanguageModel, load_env
from .agent import design
from .models import Brief, Recipe


def main(argv=None):
    p=argparse.ArgumentParser(description='Isolated, opt-in text-to-sound-recipe experiment')
    p.add_argument('brief',type=Path)
    p.add_argument('--env-file',type=Path,default=Path('.env'))
    p.add_argument('--provider',choices=['groq','gemini'],default='groq')
    p.add_argument('--model')
    p.add_argument('--recipe',type=Path,help='Render an edited recipe offline instead of generating one')
    p.add_argument('--reuse',action='store_true',help='Reuse an unapproved experimental cache candidate')
    p.add_argument('--cache',type=Path,default=Path('output/sound-design/cache'))
    p.add_argument('--output',type=Path,default=Path('output/sound-design/runs'))
    p.add_argument('--max-model-calls',type=int,default=2)
    args=p.parse_args(argv)
    try:
        brief=Brief.model_validate_json(args.brief.read_text(encoding='utf-8'))
        recipe=Recipe.model_validate_json(args.recipe.read_text(encoding='utf-8')) if args.recipe else None
        if args.env_file.exists():load_env(args.env_file)
        key=os.environ.get(args.provider.upper()+'_API_KEY','')
        name=args.model or {'groq':'qwen/qwen3.8-27b','gemini':'gemini-3.8-flash'}[args.provider]
        model=LanguageModel([(args.provider,name,key)]) if key and not recipe else OfflineModel()
        root,result=design(brief,model,args.output,max_model_calls=args.max_model_calls,recipe=recipe,
                           cache=args.cache,reuse=args.reuse)
        print(f'{result["status"]}: {root/"report.md"}')
        return 0 if result['status']=='technical_pass_listening_pending' else 2
    except (ValueError,RuntimeError,OSError) as error:
        print('Sound experiment failed:','Invalid structured input.' if isinstance(error,ValidationError) else str(error))
        return 1


if __name__=='__main__':raise SystemExit(main())
