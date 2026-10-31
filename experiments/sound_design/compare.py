"""Build a level-matched listening gallery without selecting a winner."""
from array import array
import argparse
import html
import json
import math
from pathlib import Path
import shutil
from war_content.sound_render import read_wave, synth_sample, write_wave
from .models import Brief

BASELINES={'armored_tracks':'tracks','wooden_siege_tower':'wheels','matchlock_shot':'musket'}


def level_match(clips):
    energies=[math.sqrt(sum(v*v for v in c)/max(1,len(c))) for c in clips]
    if not clips or any(r<1e-9 for r in energies):raise ValueError('Cannot level-match empty or silent audio.')
    peaks=[max((abs(v) for v in c),default=0) for c in clips]
    # Match RMS without compressing either candidate's transient shape.
    target=min([10**(-24/20)]+[.891*r/max(p,1e-12) for r,p in zip(energies,peaks)])
    return [array('f',(v*target/max(r,1e-12) for v in c)) for c,r in zip(clips,energies)],20*math.log10(max(target,1e-12))


def gallery(runs, output):
    root=Path(output);root.mkdir(parents=True,exist_ok=False)
    cards=[];results=[]
    for number,run in enumerate(map(Path,runs)):
        result=json.loads((run/'result.json').read_text(encoding='utf-8'));brief=Brief.model_validate(result['brief']).model_dump()
        name=f'{number}-{brief["concept"]}';folder=root/name;folder.mkdir()
        header=f'<h2>{html.escape(brief["concept"].replace("_"," ").title())}</h2><p>{html.escape(brief["description"])}</p>'
        if not (run/'candidate.wav').is_file():
            cards.append('<section>'+header+'<p>No candidate audio: '+html.escape('; '.join(result['issues']))+'</p></section>');results.append(result);continue
        candidate=read_wave(run/'candidate.wav');clips=[candidate];sources=['Generated DSP recipe']
        baseline=BASELINES.get(brief['concept'])
        if baseline:
            mono=synth_sample(baseline);count=round(brief['duration']*48000)
            baseline_clip=array('f',[0.0])*(count*2)
            for i in range(count):
                value=mono[i%len(mono)] if brief['loop'] or i<len(mono) else 0
                fade=min(1,i/240,(count-1-i)/240)
                baseline_clip[2*i]=baseline_clip[2*i+1]=value*fade
            clips.append(baseline_clip);sources.append('Existing production '+baseline+' recipe')
        clips,target=level_match(clips)
        order=[1,0] if number%2 and len(clips)==2 else list(range(len(clips)))
        controls=[];reveal=[]
        for slot,index in enumerate(order):
            label=chr(65+slot);file=f'{label}.wav';write_wave(folder/file,clips[index])
            controls.append(f'<label>Sample {label}<audio controls preload="metadata" src="{name}/{file}"></audio></label>')
            reveal.append(f'{label}: {sources[index]}')
        shutil.copyfile(run/'recipe.json',folder/'recipe.json')
        status='Ready for listening review' if result['status']=='technical_pass_listening_pending' else 'Needs revision'
        cards.append('<section>'+header+f'<p>{status} · matched RMS {target:.1f}dBFS</p>'+''.join(controls)+
                     '<p>Judge identity, texture, repetition, harshness and phone-speaker audibility. No automatic winner.</p>'+
                     '<details><summary>Reveal sources</summary><p>'+html.escape(' · '.join(reveal))+f'</p><a href="{name}/recipe.json">Inspect generated recipe</a></details></section>')
        results.append(dict(concept=brief['concept'],run=str(run),status=result['status'],matched_rms_dbfs=target,
                            sources=[sources[i] for i in order],metrics=result['metrics'],listening_approved=False))
    markup='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Experimental sound design — listening comparison</title>
<style>body{max-width:850px;margin:36px auto;padding:0 20px;background:#182124;color:#eee6d4;font:17px/1.55 system-ui}section{border-top:1px solid #62706a;padding:18px 0 30px}h1,h2{font-family:Georgia,serif}audio{display:block;width:min(100%,460px);margin:10px 0 24px}a{color:#dfb76d}summary{cursor:pointer}</style>
<h1>Experimental sound design</h1><p>Original AI-authored recipes versus existing effects where available. Sources are hidden under each reveal. RMS levels are matched; this is not perceptual loudness normalization. No candidate is production-approved.</p>'''+''.join(cards)
    (root/'index.html').write_text(markup,encoding='utf-8')
    (root/'comparison.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return root


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    try:print(gallery(args.runs,args.output)/'index.html');return 0
    except (ValueError,OSError,KeyError) as error:print(f'Comparison failed: {error}');return 1


if __name__=='__main__':raise SystemExit(main())
