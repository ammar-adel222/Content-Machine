"""Graph audio stages: movement Foley, cached music and current-stem composition."""
from pathlib import Path
import json
import math
import shutil
from uuid import uuid4
from war_content.sound_models import SoundConfig
from war_content.sound_plan import compile_plan
from war_content.sound_render import RATE, read_wave, render_effects, mix_voice, write_wave
from war_content.music_models import MusicConfig, MusicSource, MixSettings
from war_content.music import prepare_music
from war_content.music_render import mix_music
from war_narration.agent import atomic
from .graph import Adapter
from .models import Output
from .store import WorkflowError, file_hash


def structured(ctx,allow_objects=False):
    if ctx.instructions.get('notes') or ctx.instructions.get('scene_ids'):
        raise WorkflowError('Audio edits need structured settings: profiles/spots/samples, music source, or mix levels.')
    if ctx.instructions.get('object_ids') and not allow_objects:
        raise WorkflowError('Music and mix settings apply to the whole soundtrack.')


def duration(ctx):
    value=float(ctx.inputs['timing'].output.data['duration'])
    if not math.isfinite(value) or not 0<value<=150:raise WorkflowError('Audio needs a finite measured duration of at most 150 seconds.')
    return value


def resolve_file(ctx,path,previous_path=None,snapshot=None,base=None):
    selected=Path(path)
    if not selected.is_absolute():selected=Path(base or ctx.store.root)/selected
    if selected.is_file():return selected.resolve()
    if path==previous_path and snapshot and Path(snapshot).is_file():return Path(snapshot)
    raise WorkflowError('Selected audio source is missing; supply a local file or restore its saved snapshot.')


def sound_settings(ctx):
    structured(ctx,allow_objects=True)
    previous=ctx.previous.output.data.get('sound_config',{}) if ctx.previous else {}
    patch=dict(ctx.params)
    values=previous|patch
    for key in ('profiles','samples'):
        supplied=patch.get(key,{})
        if not isinstance(supplied,dict) or any(not isinstance(v,dict) for v in supplied.values()):
            raise WorkflowError('Sound profiles and samples must be object settings maps.')
        original=previous.get(key,{})
        values[key]=original|{name:original.get(name,{})|value for name,value in supplied.items()}
    config=SoundConfig.model_validate(values)
    targets=set(ctx.instructions.get('object_ids',[]))
    if targets and (set(patch)-{'profiles'} or set(patch.get('profiles',{}))-targets):
        raise WorkflowError('A scoped effects edit may change only the selected force profiles.')
    samples={}
    for effect,sample in config.samples.items():
        old=previous.get('samples',{}).get(effect,{}).get('path')
        snapshot=ctx.previous.output.files.get('sample_'+effect) if ctx.previous else None
        samples[effect]=resolve_file(ctx,sample.path,old,snapshot)
    return config,samples


def music_settings(ctx):
    structured(ctx)
    previous=ctx.previous.output.data.get('source_request',{}) if ctx.previous else {}
    base=ctx.previous.output.data.get('source_root') if ctx.previous else None
    if not previous and ctx.previous and ctx.previous.output.files.get('config'):
        path=Path(ctx.previous.output.files['config']);data=json.loads(path.read_text(encoding='utf-8'))
        previous=data.get('source',data);base=path.parent
    selected=MusicSource.model_validate(previous|ctx.params)
    if ctx.params.get('path')!=previous.get('path') and 'path' in ctx.params:base=ctx.store.root
    original=None
    if selected.kind=='file':
        snapshot=ctx.previous.output.files.get('original') if ctx.previous else None
        original=resolve_file(ctx,selected.path,previous.get('path'),snapshot,base)
    return selected,original,str(base or ctx.store.root)


def mix_settings(ctx):
    structured(ctx)
    previous=ctx.previous.output.data.get('mix_settings',{}) if ctx.previous else {}
    return MixSettings.model_validate(previous|ctx.params)


def work_dir(ctx):
    path=ctx.output_dir/uuid4().hex;path.mkdir();return path


def json_file(folder,name,data):
    path=folder/name
    atomic(path,json.dumps(data,ensure_ascii=False,indent=2).encode());return str(path)


def effects(ctx):
    config,samples=sound_settings(ctx);seconds=duration(ctx)
    timing=ctx.inputs['timing'].output.data
    plan=timing['plan']
    if plan['blueprint']!=ctx.inputs['direction'].output.data['blueprint']:
        raise WorkflowError('Effects need matching current direction and measured timing.')
    scene={'duration':seconds,'blueprint':plan['blueprint'],'timeline':timing['actions']}
    cues=compile_plan(scene,config)
    folder=work_dir(ctx)
    data={'duration':seconds,'kind':'effects_stem','sound_config':config.model_dump(mode='json'),
          'cue_count':len(cues.cues),'publishing_ready':False}
    files={'config':json_file(folder,'sound-config.json',data['sound_config']),
           'plan':json_file(folder,'sound-plan.json',cues.model_dump(mode='json'))}
    if cues.unresolved_units:
        return Output(data=data,files=files,issues=['Choose a movement profile or explicit none for: '+', '.join(cues.unresolved_units)])
    for effect,path in samples.items():
        read_wave(path,rate=RATE)  # Validate before publishing a replacement snapshot.
        target=folder/('sample-'+effect+'-'+file_hash(path)+'.wav');shutil.copyfile(path,target);files['sample_'+effect]=str(target)
        samples[effect]=target
    dry,metrics=mix_voice(render_effects(cues,samples,rate=RATE),rate=RATE)
    path=folder/'sound-effects.wav';write_wave(path,dry,rate=RATE);files['wave']=str(path)
    files['metrics']=json_file(folder,'effects-metrics.json',metrics)
    return Output(data=data,files=files,views={'waveform':file_hash(path)})


def music_source(ctx):
    selected,original,base=music_settings(ctx);seconds=duration(ctx)
    actual=selected.model_copy(update={'path':str(original)}) if original else selected
    cache=ctx.store.root/'music-cache'
    _,details,_,reused=prepare_music(MusicConfig(source=actual),seconds,ctx.store.root,cache)
    prepared=cache/details['cache_key']/'music-source.wav'
    if file_hash(prepared)!=details['prepared_sha256']:raise WorkflowError('Prepared music failed its integrity check.')
    folder=work_dir(ctx)
    target=folder/'music-source.wav';shutil.copyfile(prepared,target)
    files={'wave':str(target),'config':json_file(folder,'music-source.json',selected.model_dump(mode='json')),
           'metadata':json_file(folder,'music-source-metadata.json',details)}
    if original:
        saved=folder/('original-'+file_hash(original)+original.suffix.lower());shutil.copyfile(original,saved);files['original']=str(saved)
    return Output(data={'duration':seconds,'source_request':selected.model_dump(mode='json'),'source_root':base,'prepared':details,'reused':reused,'publishing_ready':False},
                  files=files,views={'waveform':file_hash(target)})


def mix(ctx):
    settings=mix_settings(ctx)
    fx_artifact=ctx.inputs['effects'];music_artifact=ctx.inputs['music_source'];voice_artifact=ctx.inputs['narration']
    fx=read_wave(fx_artifact.output.files['wave'],rate=RATE);music=read_wave(music_artifact.output.files['wave'],rate=RATE)
    seconds=float(fx_artifact.output.data['duration'])
    if not math.isfinite(seconds) or not 0<seconds<=150:raise WorkflowError('Invalid effects duration.')
    expected=round(seconds*RATE)*2
    if len(fx)!=expected or len(music)!=expected:raise WorkflowError('Music and effects stems must exactly match the measured video duration.')
    present=bool(voice_artifact.output.data.get('present',voice_artifact.output.files.get('wave')))
    if present and not voice_artifact.output.files.get('wave'):raise WorkflowError('The narration stem is missing.')
    voice=read_wave(voice_artifact.output.files['wave'],rate=RATE) if present else None
    if 'narration' in voice_artifact.output.data and voice is not None and len(voice)!=expected:
        raise WorkflowError('Generated narration no longer matches its measured video duration.')
    prepared=music_artifact.output.data.get('prepared',{})
    active=float(prepared.get('active_duration',seconds))
    mixed,bed,metrics=mix_music(fx,voice,music,settings,active,rate=RATE)
    files={};folder=work_dir(ctx)
    for key,artifact in (('effects',fx_artifact),('music_source',music_artifact),('narration',voice_artifact)):
        if artifact.output.files.get('wave'):
            target=folder/(key+'.wav');shutil.copyfile(artifact.output.files['wave'],target);files[key]=str(target)
    for name,samples in (('soundtrack',mixed),('music',bed)):
        target=folder/(name+'.wav');write_wave(target,samples,rate=RATE);files['wave' if name=='soundtrack' else 'music']=str(target)
    files['config']=json_file(folder,'mix-settings.json',settings.model_dump(mode='json'))
    files['metrics']=json_file(folder,'mix-metrics.json',metrics)
    return Output(data={'duration':seconds,'mix_settings':settings.model_dump(mode='json'),'has_narration':present,
                        'inputs':{s:a.id for s,a in ctx.inputs.items()},'publishing_ready':False},files=files)


def rebind_mix(ctx,cached):
    # Waveform-identical inputs still get current artifact provenance, without DSP.
    output=cached.output.model_copy(deep=True)
    output.data['inputs']={s:a.id for s,a in ctx.inputs.items()}
    return output


def adapters():
    def sound_context(ctx):
        config,files=sound_settings(ctx)
        return {'config':config.model_dump(mode='json'),'samples':{k:file_hash(p) for k,p in files.items()}}
    def music_context(ctx):
        selected,original,base=music_settings(ctx)
        return {'source':selected.model_dump(mode='json'),'source_root':base,'sha256':file_hash(original) if original else None}
    return {'effects':Adapter(effects,'movement-foley-v2-clash',cache_context=sound_context),
            'music_source':Adapter(music_source,'quiet-music-source-v1',cache_context=music_context),
            'mix':Adapter(mix,'stem-mix-v1',rebind_mix,lambda ctx:mix_settings(ctx).model_dump(mode='json'))}
