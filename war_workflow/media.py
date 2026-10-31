"""First live adapters: edit an existing music project's audio without authoring again."""
from array import array
import json
import math
from pathlib import Path
import subprocess
import wave
from .graph import Adapter
from .models import Limits, Output
from .planner import fingerprint
from .store import ProjectStore, WorkflowError, file_hash


def probe(path):
    result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height',
                           '-of','json',str(path)],capture_output=True,timeout=30)
    try:data=json.loads(result.stdout)
    except ValueError:raise WorkflowError('Cannot inspect this video.') from None
    if result.returncode or not any(s.get('codec_type')=='video' for s in data.get('streams',[])):
        raise WorkflowError('A readable video is required.')
    try:duration=float(data['format']['duration'])
    except (KeyError,ValueError):raise WorkflowError('Video duration is unavailable.') from None
    if not math.isfinite(duration) or duration<=0:raise WorkflowError('Video duration is invalid.')
    return data


def import_media(root,bundle,video,*,picture_approved=False):
    from war_content.music_models import MusicConfig
    from war_content.play import ready
    bundle=Path(bundle).resolve();video=Path(video).resolve()
    if not ready(bundle):raise WorkflowError('Choose a complete content/preview bundle.')
    for name in ('music-config.json','music-source.wav','music-metrics.json','sound-effects.wav','soundtrack.wav'):
        if not (bundle/name).is_file():raise WorkflowError('Import a music-enabled bundle with its separate stems.')
    scene=json.loads((bundle/'scene.json').read_text(encoding='utf-8'));duration=float(scene['duration'])
    info=probe(video)
    if abs(float(info['format']['duration'])-duration)>.05:raise WorkflowError('Imported picture duration does not match the audio project.')
    config=MusicConfig.model_validate_json((bundle/'music-config.json').read_text(encoding='utf-8'))
    music_files={'wave':str(bundle/'music-source.wav'),'config':str(bundle/'music-config.json')}
    if config.source.kind=='file':music_files['original']=str((bundle/config.source.path).resolve())
    store=ProjectStore.create(root,scene['topic']+' — audio revision',target_seconds=max(1,round(duration)),
                              limits=Limits(model_attempts=0,search_requests=0,tts_requests=0))
    revision=store.load();revision.params['mix']=config.mix.model_dump()
    base={'bundle':str(bundle),'basis':'Imported media; upstream authoring agents were not run.',
          'publishing_ready':False,'duration':duration}
    outputs={
        'timing':Output(data={'duration':duration,'basis':'Imported clip clock only.'},views={'duration':duration}),
        'effects':Output(data=base,files={'wave':str(bundle/'sound-effects.wav')},views={'waveform':file_hash(bundle/'sound-effects.wav')}),
        'music_source':Output(data=base,files=music_files,views={'waveform':file_hash(bundle/'music-source.wav')}),
        'mix':Output(data=base,files={'wave':str(bundle/'soundtrack.wav'),'metrics':str(bundle/'music-metrics.json')}),
        'picture':Output(data=base,files={'video':str(video)}),
        'visual_review':Output(data={'basis':'Explicit approval of imported picture only.','video_sha256':file_hash(video)},
                               review='pass' if picture_approved else 'revise'),
        'narration':Output(data=base|{'present':bool(scene['soundtrack'].get('has_narration'))},
                           files={'wave':str(bundle/'narration.wav')} if scene['soundtrack'].get('has_narration') else {}),
    }
    for stage,output in outputs.items():
        artifact=store.write_artifact(stage,fingerprint({'import':output.model_dump(),'stage':stage}),output,'import-v1')
        revision.artifacts[stage]=artifact.id
    # Imported media is not a fabricated research/script/director history.
    revision.dirty=['audio_review','mux','final_review'];store.save(revision)
    return store


def mix(ctx):
    from war_content.music import compile_bundle
    from war_content.music_models import MusicConfig,MixSettings
    source=Path((ctx.previous or ctx.inputs['effects']).output.data['bundle'])
    config=MusicConfig.model_validate_json((source/'music-config.json').read_text(encoding='utf-8'))
    try:config.mix=MixSettings.model_validate(config.mix.model_dump()|ctx.params)
    except ValueError:raise WorkflowError('Invalid audio mix parameters; use the fields in music-config.json.') from None
    target=compile_bundle(source,ctx.output_dir,config=config,config_root=source,cache=ctx.store.root/'music-cache')
    duration=json.loads((target/'scene.json').read_text(encoding='utf-8'))['duration']
    files={'wave':str(target/'soundtrack.wav'),'metrics':str(target/'music-metrics.json'),
           'config':str(target/'music-config.json'),'music_source':str(target/'music-source.wav'),
           'effects':str(target/'sound-effects.wav')}
    if (target/'narration.wav').is_file():files['narration']=str(target/'narration.wav')
    if config.source.kind=='file':files['original']=str(target/('music-original'+Path(config.source.path).suffix.lower()))
    return Output(data={'bundle':str(target),'duration':duration,'publishing_ready':False},files=files)


def audio_review(ctx):
    current=ctx.inputs['mix']
    with wave.open(current.output.files['wave'],'rb') as audio:
        if audio.getsampwidth()!=2 or audio.getnchannels()!=2:raise WorkflowError('Expected a 16-bit stereo final mix.')
        duration=audio.getnframes()/audio.getframerate();samples=array('h',audio.readframes(audio.getnframes()))
    peak=max((abs(v)/32768 for v in samples),default=0)
    if abs(duration-float(current.output.data['duration']))>.01 or peak>.893:
        return Output(data={'duration':duration,'peak':peak},review='revise',issues=['Final mix duration or headroom failed checks.'])
    return Output(data={'reviewed_mix':current.id,'duration':duration,'peak':peak,'basis':'Technical audio checks; listening approval is still required.'},review='pass')


def mux(ctx):
    from war_content.sound_effects import mux_video
    target=ctx.output_dir/'final.mp4';mix=ctx.inputs['mix'];picture=ctx.inputs['picture']
    mux_video(picture.output.files['video'],mix.output.files['wave'],target,mix.output.data['duration'])
    return Output(data={'duration':mix.output.data['duration'],'picture':picture.id,'mix':mix.id,'publishing_ready':False},files={'video':str(target)})


def final_review(ctx):
    video=ctx.inputs['mux'];info=probe(video.output.files['video'])
    if not any(s.get('codec_type')=='audio' for s in info['streams']):
        return Output(data={},review='revise',issues=['Final output is missing its composed audio track.'])
    if abs(float(info['format']['duration'])-float(video.output.data['duration']))>.05:
        return Output(data={},review='revise',issues=['Final video duration differs from its audio plan.'])
    return Output(data={'reviewed_video':video.id,'basis':'Technical container checks; human content/listening review remains required.'},review='pass')


def adapters():
    return {'mix':Adapter(mix,'music-mix-v1'),'audio_review':Adapter(audio_review,'audio-check-v1'),
            'mux':Adapter(mux,'mux-v1'),'final_review':Adapter(final_review,'media-check-v1')}
