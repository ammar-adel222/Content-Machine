"""Independent, cached music preparation and editable stem-based audio mixing."""
import argparse
import hashlib
import json
import shutil
import subprocess
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from .music_models import MusicConfig
from .music_render import ambient_bed, pulse_bed, fit_track, mix_music
from .play import ready, WEB, RUNTIME
from .sound_effects import mux_video
from .sound_render import RATE, read_wave, write_wave


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode_track(path, offset, duration):
    with TemporaryDirectory(prefix='content-music-') as tmp:
        target=Path(tmp)/'decoded.wav'
        result=subprocess.run(['ffmpeg','-y','-v','error','-ss',str(offset),'-i',str(path),'-t',str(duration),
                               '-vn','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(target)],capture_output=True,timeout=90)
        if result.returncode:raise ValueError('Cannot decode the selected local music track.')
        return read_wave(target)


def prepare_music(config, duration, source_root, cache, previous=None):
    source=config.source;original=None
    if source.kind=='file':
        original=Path(source.path)
        if not original.is_absolute():original=Path(source_root)/original
        if not original.is_file():raise ValueError('Selected music track is missing; choose a local audio file.')
        if original.suffix.lower() not in ('.wav','.mp3','.ogg','.flac','.m4a','.aac'):
            raise ValueError('Choose WAV, MP3, OGG, FLAC, M4A or AAC music.')
        source_hash=digest(original)
    else:source_hash=hashlib.sha256(('quiet-atlas-'+source.arrangement+'-v1').encode()).hexdigest()
    identity=dict(engine='music-v1',source_hash=source_hash,kind=source.kind,duration=float(duration),
                  offset_sec=float(source.offset_sec),loop=source.loop,crossfade_sec=float(source.crossfade_sec),rate=RATE)
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    previous=previous or {}
    local=Path(source_root)/'music-source.wav'
    if previous.get('cache_key')==key and local.is_file():
        if digest(local)!=previous.get('prepared_sha256'):raise ValueError('Prepared music changed; rebuild from its original track.')
        details={k:v for k,v in previous.items() if k!='project_sha256'}
        return read_wave(local),details,original,True
    folder=Path(cache)/key;metadata=folder/'source.json';audio=folder/'music-source.wav'
    if metadata.exists():
        details=json.loads(metadata.read_text(encoding='utf-8'))
        if details.get('cache_key')!=key or not audio.is_file() or digest(audio)!=details.get('prepared_sha256'):
            raise ValueError('Music cache is inconsistent; repair or remove that cache entry.')
        return read_wave(audio),details,original,True
    raw=decode_track(original,source.offset_sec,duration) if original else (pulse_bed() if source.arrangement=='pulse' else ambient_bed())
    if original is None and source.offset_sec:
        offset=round((source.offset_sec%32)*RATE)*2;raw=raw[offset:]+raw[:offset]
    prepared,details=fit_track(raw,duration,source.loop,source.crossfade_sec)
    folder.mkdir(parents=True,exist_ok=True)
    # Publish cache metadata last; incomplete writes are never accepted as a hit.
    temporary_audio=folder/(uuid4().hex+'.wav');temporary_metadata=folder/(uuid4().hex+'.json')
    try:
        write_wave(temporary_audio,prepared)
        details.update(identity);details.update(cache_key=key,prepared_sha256=digest(temporary_audio))
        temporary_metadata.write_text(json.dumps(details,indent=2),encoding='utf-8')
        temporary_audio.replace(audio);temporary_metadata.replace(metadata)
    finally:
        temporary_audio.unlink(missing_ok=True);temporary_metadata.unlink(missing_ok=True)
    return read_wave(audio),details,original,False


def apply_music(target, config, *, source_root=None, cache='output/music-cache', previous=None):
    """Recompose an owned output bundle from its dry stems, never from a mixed track."""
    root=Path(target);source_root=Path(source_root or root)
    scene=json.loads((root/'scene.json').read_text(encoding='utf-8'));duration=float(scene['duration'])
    if not 0<duration<=150:raise ValueError('Music supports videos up to 150 seconds.')
    effects=read_wave(root/'sound-effects.wav') if (root/'sound-effects.wav').is_file() else array('f',[0.0])*(round(duration*RATE)*2)
    if len(effects)!=round(duration*RATE)*2:raise ValueError('Effects stem duration differs from the video.')
    voice=read_wave(root/'narration.wav') if scene.get('soundtrack',{}).get('has_narration') else None
    music,details,original,reused=prepare_music(config,duration,source_root,cache,previous)
    mixed,bed,stats=mix_music(effects,voice,music,config.mix,details['active_duration'])
    config=config.model_copy(deep=True)
    if original:
        name='music-original'+original.suffix.lower()
        if original.resolve()!=(root/name).resolve():shutil.copyfile(original,root/name)
        config.source.path=name
    write_wave(root/'music-source.wav',music);write_wave(root/'music.wav',bed);write_wave(root/'soundtrack.wav',mixed)
    if not (root/'sound-effects.wav').exists():write_wave(root/'sound-effects.wav',effects)
    (root/'music-config.json').write_text(config.model_dump_json(indent=2),encoding='utf-8')
    stems={name:digest(root/name) for name in ('sound-effects.wav','music-source.wav','music.wav','soundtrack.wav','narration.wav') if (root/name).is_file()}
    project=dict(schema_version='1.0',duration=duration,parent_project_sha256=previous.get('project_sha256') if previous else None,
                 source=details,stems=stems,mix=config.mix.model_dump(),music_title=config.source.title,
                 attribution=config.source.attribution,prepared_music_reused=reused)
    (root/'audio-project.json').write_text(json.dumps(project,indent=2),encoding='utf-8')
    scene['soundtrack']={**scene.get('soundtrack',{}),'file':'soundtrack.wav','sha256':stems['soundtrack.wav'],
                         'duration':duration,'has_narration':voice is not None,'has_music':config.mix.enabled,
                         'music_project_sha256':digest(root/'audio-project.json')}
    (root/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'music-metrics.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    lines=['# Music and editable audio mix','',f'Track: {config.source.title}',f'Attribution: {config.source.attribution}',
           f'Music enabled: {config.mix.enabled}; gain: {config.mix.music_gain_db}dB relative to prepared source.',
           f'Prepared source reused: {reused}; final music RMS: {stats["music_rms_dbfs"]:.2f}dBFS.',
           f'Final peak: {stats["final_peak_dbfs"]:.2f}dBFS.',
           'Narration and prominent effects take priority; music ducks with smooth attack/release.',
           'Edit music-config.json, then run war_content.music on this bundle to remix without rerendering visuals.',
           'Dry narration, effects, prepared music and the mixed music stem remain separate.',
           'Original source, source hashes, settings and parent project identity remain available for revisions.',
           'The source publishing/review status is preserved.']
    (root/'music-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return project


def inherit_music(source, target, cache='output/music-cache'):
    """Preserve a music project when the existing effects compiler rebuilds its stem."""
    source=Path(source);target=Path(target)
    manifest=source/'audio-project.json'
    if not manifest.is_file():return False
    project=json.loads(manifest.read_text(encoding='utf-8'))
    previous={**project['source'],'project_sha256':digest(manifest)}
    config=MusicConfig.model_validate_json((source/'music-config.json').read_text(encoding='utf-8'))
    content=(target/'content.json').read_bytes()
    (target/'content.json').write_text('{"status":"needs_revision","publishing_ready":false}',encoding='utf-8')
    apply_music(target,config,source_root=source,cache=cache,previous=previous)
    (target/'content.json').write_bytes(content)
    return True


def compile_bundle(bundle, output, *, config=None, config_root=None, cache='output/music-cache', narration=None, video=None):
    source=Path(bundle).resolve()
    if not ready(source):raise ValueError('Choose a ready content or preview bundle.')
    scene=json.loads((source/'scene.json').read_text(encoding='utf-8'))
    if scene.get('soundtrack') and not (source/'sound-effects.wav').is_file():
        raise ValueError('Keep the dry effects stem to edit music independently.')
    manifest=source/'audio-project.json';previous={}
    if manifest.is_file():previous={**json.loads(manifest.read_text(encoding='utf-8'))['source'],'project_sha256':digest(manifest)}
    if config is None:
        config=MusicConfig.model_validate_json((source/'music-config.json').read_text(encoding='utf-8')) if (source/'music-config.json').exists() else MusicConfig()
        config_root=source
    target=Path(output)/uuid4().hex;target.mkdir(parents=True,exist_ok=False)
    for name in RUNTIME:shutil.copyfile(WEB/name,target/name)
    original_content=(source/'content.json').read_bytes()
    (target/'content.json').write_text('{"status":"needs_revision","publishing_ready":false}',encoding='utf-8')
    selected={'pixi.min.js','sound-effects.wav','narration.wav','sound-config.json','sound-plan.json','sound-report.md','sound-metrics.json'}
    for file in source.iterdir():
        if file.is_file() and (file.name in selected or (file.name.startswith('relief-') and file.suffix=='.png')):shutil.copyfile(file,target/file.name)
    if narration:
        read_wave(narration);shutil.copyfile(narration,target/'narration.wav')
        scene.setdefault('soundtrack',{})['has_narration']=True
    if scene.get('soundtrack',{}).get('has_narration') and not (target/'narration.wav').is_file():
        raise ValueError('Keep the narration stem to edit the audio mix.')
    (target/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
    apply_music(target,config,source_root=config_root or source,cache=cache,previous=previous)
    (target/'content.json').write_bytes(original_content)
    if video:mux_video(video,target/'soundtrack.wav',target/'preview-with-music.mp4',scene['duration'])
    return target


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path)
    p.add_argument('--config',type=Path);p.add_argument('--narration',type=Path);p.add_argument('--video',type=Path)
    p.add_argument('--output',type=Path,default=Path('output/content'));p.add_argument('--cache',type=Path,default=Path('output/music-cache'))
    args=p.parse_args(argv)
    try:
        config=MusicConfig.model_validate_json(args.config.read_text(encoding='utf-8')) if args.config else None
        root=compile_bundle(args.bundle,args.output,config=config,config_root=args.config.parent if args.config else None,
                            cache=args.cache,narration=args.narration,video=args.video)
        print(f'Music ready: {root/"music-report.md"}');return 0
    except (ValueError,RuntimeError,OSError,KeyError,subprocess.SubprocessError) as error:
        from pydantic import ValidationError
        print('Music failed:','Invalid structured input.' if isinstance(error,ValidationError) else str(error));return 1


if __name__=='__main__':raise SystemExit(main())
