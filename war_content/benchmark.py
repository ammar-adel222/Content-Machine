"""Repeatable design/vision smoke comparison; no model is used to judge its own art."""
import argparse
import base64
import json
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from pydantic import Field
from war_research.models import Model
from war_research.providers import LanguageModel, load_env, request_json
from .agent import DESIGN_INSTRUCTIONS
from .models import Brief, Design

TASKS = [Brief(category="unit",concept="tank",description="A generic top-down tracked tank with two tracks, hull, turret and barrel facing right."),
         Brief(category="terrain",concept="cliff",description="A top-down repeatable cliff escarpment motif: an irregular lip with short descending hatching.")]
DISCUSSED = ["dots-studio/dots-3-note-preview:free","nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free","thinkingmachines/inkling-small:free",
    "nvidia/nemotron-3.5-super-vl:free","minimax/minimax-m3:free"]


class Inspection(Model):
    tank_in_water: Literal["red", "blue", "both", "none"]
    labels_overlap: bool
    bridge_visible: bool
    tank_count: int = Field(ge=0,le=20)


class VisionAnswer(Model):
    control: Inspection
    problem: Inspection


TRUTH = VisionAnswer(control=Inspection(tank_in_water="none",labels_overlap=False,bridge_visible=True,tank_count=2),
                     problem=Inspection(tank_in_water="red",labels_overlap=True,bridge_visible=False,tank_count=2))


def vision_score(answer):
    expected,actual=TRUTH.model_dump(),answer.model_dump()
    return sum(actual[scene][key]==value for scene,row in expected.items() for key,value in row.items())


def candidates(catalog):
    available={r["id"]:r for r in catalog if all(float(r.get("pricing",{}).get(k,"1"))==0 for k in ("prompt","completion"))}
    result=[{"provider":"gemini","model":"gemini-3.5-flash-lite","vision":True},
            {"provider":"gemini","model":"gemini-3.8-flash","vision":True},
            {"provider":"groq","model":"qwen/qwen3.8-27b","vision":True},
            {"provider":"groq","model":"openai/gpt-oss-120b","vision":False},
            {"provider":"groq","model":"openai/gpt-oss-20b","vision":False}]
    for model in DISCUSSED:
        row=available.get(model)
        result.append({"provider":"openrouter","model":model,"vision":bool(row and "image" in row.get("architecture",{}).get("input_modalities",[])),
                       **({} if row else {"skip":"No currently listed zero-priced route."})})
    return result


def evaluate(candidate,model,images):
    result={**candidate,"designs":[],"vision":None,"attempts":0}
    def consume():
        if result["attempts"]>=3:raise RuntimeError("Benchmark attempt budget exhausted.")
        result["attempts"]+=1
    for brief in TASKS:
        started=time.perf_counter()
        try:
            design=model.generate(DESIGN_INSTRUCTIONS+"\nBRIEF: "+brief.model_dump_json(),Design,consume)
            result["designs"].append({"concept":brief.concept,"status":"valid","seconds":round(time.perf_counter()-started,2),"design":design.model_dump()})
        except (ValueError,RuntimeError) as error:
            result["designs"].append({"concept":brief.concept,"status":"failed","seconds":round(time.perf_counter()-started,2),"error":str(error)})
    if candidate["vision"]:
        try:
            answer=model.generate("Inspect the two supplied map screenshots ONLY; do not infer hidden movement. "
                "First image is control, second is problem. For each, which tank color has its hull "
                "center in blue river water, do EAST RIDGE/RIVER CROSSING label texts visibly overlap, "
                "is a brown bridge visible across the river, and how many tanks are visible?",
                VisionAnswer,consume,images=images)
            result["vision"]={"status":"ok","correct":vision_score(answer),"total":8,"answer":answer.model_dump()}
        except (ValueError,RuntimeError) as error:
            result["vision"]={"status":"failed","error":str(error)}
    else:
        result["vision"]={"status":"unsupported"}
    result["models_used"]=list(dict.fromkeys(model.used))
    return result


def report(results):
    lines=["# Visual model comparison", "", "Single-sample smoke benchmark, not a general model ranking.",
        "Two original design tasks (tank and cliff), plus two blind screenshots with eight scored observations.",
        "Valid means schema/geometry passed; it does not measure creativity or recognizability.",
        "Inspect the rendered gallery for design quality. Failures measure this adapter/schema/route combination.",
        "No fallbacks or output repairs; one attempt per task. OpenRouter is constrained to zero-priced routes.",
        "", "| Provider/model | Valid designs | Image observations |", "|---|---:|---:|"]
    for r in sorted(results,key=lambda row:(row['provider'],row['model'])):
        if r.get("skip"):
            lines.append(f"| {r['provider']}/{r['model']} | Skipped | {r['skip']} |")
            continue
        valid=sum(x['status']=='valid' for x in r['designs']);v=r['vision']
        score=f"{v['correct']}/8" if v['status']=='ok' else v['status']
        lines.append(f"| {r['provider']}/{r['model']} | {valid}/2 | {score} |")
    lines += ["", "## Failures", ""]
    for r in results:
        if r.get('skip'):continue
        for task in r.get('designs',[]):
            if task['status']=='failed':lines.append(f"- {r['model']} / {task['concept']}: {task['error']}")
        if r.get('vision',{}).get('status')=='failed':lines.append(f"- {r['model']} / images: {r['vision']['error']}")
    return "\n".join(lines)+"\n"


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',type=Path,default=Path('.env'))
    p.add_argument('--output',type=Path,default=Path('output/benchmarks/visual'))
    p.add_argument('--probes',type=Path,default=Path('output/benchmarks/probes'))
    p.add_argument('--resume',action='store_true',help='Keep completed results; only test remaining candidates')
    args=p.parse_args(argv)
    if args.env_file.exists():load_env(args.env_file)
    catalog=request_json('https://openrouter.ai/api/v1/models')['data']
    options=candidates(catalog)
    images=[('image/png',base64.b64encode((args.probes/name).read_bytes()).decode()) for name in ('control.png','problem.png')]
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    signature=hashlib.sha256(json.dumps([DESIGN_INSTRUCTIONS,[t.model_dump() for t in TASKS],images],sort_keys=True).encode()).hexdigest()
    previous=json.loads((args.output/'results.json').read_text(encoding='utf-8')) if args.resume and (args.output/'results.json').exists() else None
    if previous and previous.get('signature') != signature:
        raise ValueError('Benchmark input signature changed; use a new output directory.')
    results=previous['results'] if previous else []
    done={(r['provider'],r['model']) for r in results}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={}
        for option in options:
            if (option['provider'],option['model']) in done:continue
            key=os.environ.get({'gemini':'GEMINI_API_KEY','groq':'GROQ_API_KEY','openrouter':'OPENROUTER_API_KEY'}[option['provider']], '')
            if option.get('skip') or not key:
                results.append({**option,'skip':option.get('skip') or 'API key not configured.'});continue
            model=LanguageModel([(option['provider'],option['model'],key)])
            jobs[pool.submit(evaluate,option,model,images)]=option
        for job in as_completed(jobs):
            result=job.result();results.append(result)
            print(result['provider']+':'+result['model']+' finished',flush=True)
            snapshot={'created_at':datetime.now(timezone.utc).isoformat(),'signature':signature,'results':results}
            (args.output/'results.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
            (args.output/'report.md').write_text(report(results),encoding='utf-8')
    # Also persist runs where all routes were skipped or already completed.
    (args.output/'results.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'signature':signature,'results':results},indent=2),encoding='utf-8')
    (args.output/'report.md').write_text(report(results),encoding='utf-8')
    print(args.output/'report.md')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
