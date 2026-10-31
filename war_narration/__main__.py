import argparse
import json
import os
from pathlib import Path
from .agent import generate, save, atomic, audio_timing
from .models import NarrationRequest
from .provider import GeminiSpeech
from .timing import align_plan, srt
from war_writer.models import Script
from war_research.models import Dossier
from war_research.providers import load_env
from war_director.models import Plan


def main(argv=None):
    p=argparse.ArgumentParser(description='Generate cached narration and align a saved battle plan.')
    p.add_argument('script',type=Path);p.add_argument('--output',type=Path,default=Path('output/narration'))
    p.add_argument('--cache',type=Path,default=Path('output/narration-cache'))
    p.add_argument('--config',type=Path);p.add_argument('--env-file',type=Path,default=Path('.env'))
    p.add_argument('--dossier',type=Path);p.add_argument('--plan',type=Path)
    args=p.parse_args(argv)
    try:
        if bool(args.dossier)!=bool(args.plan):raise ValueError('Supply both --dossier and --plan for measured action alignment.')
        if args.env_file.exists():load_env(args.env_file)
        values={'model':os.environ.get('GEMINI_TTS_MODEL','gemini-3.8-flash-tts'),'voice':os.environ.get('GEMINI_TTS_VOICE','Charon')}
        if args.config:values|=json.loads(args.config.read_text(encoding='utf-8'))
        request=NarrationRequest.model_validate(values)
        script=Script.model_validate_json(args.script.read_text(encoding='utf-8'))
        # Validate optional plan inputs before spending any TTS requests.
        dossier=Dossier.model_validate_json(args.dossier.read_text(encoding='utf-8')) if args.dossier else None
        plan=Plan.model_validate_json(args.plan.read_text(encoding='utf-8')) if args.plan else None
        if plan:
            from war_director.agent import validate_inputs
            from war_writer.agent import fingerprint
            validate_inputs(dossier,script)
            if plan.script_sha256!=fingerprint(script) or plan.dossier_sha256!=fingerprint(dossier):raise ValueError('Plan input versions do not match.')
            if plan.status!='ready' or plan.issues or not plan.review or plan.review.status!='pass' or plan.review.artifact_sha256!=fingerprint(plan.blueprint):
                raise ValueError('A ready plan with matching quality review is required for alignment.')
        narration=generate(script,args.output,args.cache,lambda:GeminiSpeech(os.environ.get('GEMINI_API_KEY','')),request)
        manifest=save(narration,args.output)
        atomic(args.output/(manifest.stem+'-audio-timing.json'),audio_timing(narration).model_dump_json(indent=2).encode())
        print('Narration saved:',manifest)
        if plan:
            timed,clock=align_plan(dossier,script,plan,narration)
            key=manifest.stem
            atomic(args.output/(key+'-plan.json'),timed.model_dump_json(indent=2).encode())
            atomic(args.output/(key+'-alignment.json'),json.dumps(clock,indent=2).encode())
            atomic(args.output/(key+'-captions.srt'),srt(clock['phrases']).encode())
            print('Plan timing:',timed.status)
            return 0 if timed.status=='ready' else 2
        return 0
    except (ValueError,RuntimeError,OSError,KeyError):
        print('Narration stopped: invalid input, unavailable provider or exhausted request budget. Completed clips remain cached.')
        return 1


if __name__=='__main__':raise SystemExit(main())
