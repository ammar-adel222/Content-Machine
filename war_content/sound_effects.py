"""Independent offline sound-effect compiler for a saved video bundle."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4
from .play import RUNTIME, WEB, ready
from .sound_models import SoundConfig
from .sound_plan import compile_plan
from .sound_render import mix_voice, read_wave, render_effects, write_wave


def compile_bundle(bundle, config, output, *, narration=None, sample_root=None, video=None):
    source=Path(bundle).resolve()
    if not ready(source):raise ValueError('Choose a ready content or preview bundle.')
    scene=json.loads((source/'scene.json').read_text(encoding='utf-8'))
    if narration is None and scene.get('soundtrack',{}).get('has_narration'):
        narration=source/'narration.wav'
        if not narration.is_file():
            raise ValueError('Provide the narration stem to rebuild effects for this narrated bundle.')
    plan=compile_plan(scene,config)
    target=Path(output)/uuid4().hex
    target.mkdir(parents=True,exist_ok=False)
    (target/'sound-plan.json').write_text(plan.model_dump_json(indent=2),encoding='utf-8')
    (target/'sound-config.json').write_text(config.model_dump_json(indent=2),encoding='utf-8')
    lines=['# Sound-effects build','',f'Topic: {scene["topic"]}',f'Duration: {plan.duration}s',
           f'Cues: {len(plan.cues)}','', 'Original synthesized Foley; replacement recordings are listed below. No music.']
    if plan.omitted_actions:
        lines+=['','Omitted unanimated movement cues: '+', '.join(plan.omitted_actions)]
    if plan.unresolved_units:
        lines+=['','Status: needs_profiles','Choose a movement profile or explicit none for: '+', '.join(plan.unresolved_units)]
        (target/'sound-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        return target,False
    samples={}
    for effect,sample in config.samples.items():
        path=Path(sample.path)
        if not path.is_absolute():path=Path(sample_root or '.')/path
        if not path.is_file():raise ValueError(f'Missing replacement WAV for {effect}.')
        samples[effect]=path
        lines.append(f'- {effect}: {path.name}; SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}; {sample.attribution}')
    dry,dry_stats=mix_voice(render_effects(plan,samples))
    voice=read_wave(narration) if narration else None
    mixed,stats=mix_voice(dry,voice)
    write_wave(target/'sound-effects.wav',dry)
    write_wave(target/'soundtrack.wav',mixed)
    if voice is not None:shutil.copyfile(narration,target/'narration.wav')
    for name in RUNTIME:
        shutil.copyfile(WEB/name,target/name)
    # Copy only runtime and media files, never unrelated files from the source folder.
    for file in source.iterdir():
        if file.name in ('pixi.min.js','content.json') or (file.name.startswith('relief-') and file.suffix=='.png'):
            if file.is_file():shutil.copyfile(file,target/file.name)
    scene['soundtrack']={'file':'soundtrack.wav','sha256':hashlib.sha256((target/'soundtrack.wav').read_bytes()).hexdigest(),
                         'duration':plan.duration,'has_narration':bool(narration),'source_scene_sha256':plan.scene_sha256}
    (target/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
    lines+=['','Status: ready',f'Peak: {stats["peak_dbfs"]:.2f} dBFS; RMS: {stats["rms_dbfs"]:.2f} dBFS',
            f'Narration: {bool(narration)}; speech-active 20ms blocks: {stats["speech_blocks"]}',
            'Voice ducking: effects reduce by up to 12dB during detected speech, with attack/release smoothing.',
            '48kHz stereo, 16-bit PCM. Equal-power restrained panning; stereo remains mono-compatible.',
            'No firing is inferred from movement or a narration word. Weapon/impact cues require explicit engagement spots.',
            'Sound profiles describe illustrative Foley, not verified historical recordings.',
            'The source content publishing/review status is preserved.']
    (target/'sound-metrics.json').write_text(json.dumps(dict(mix=stats,effects=dry_stats),indent=2),encoding='utf-8')
    (target/'sound-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if video:
        mux_video(video,target/'soundtrack.wav',target/'preview-with-sound.mp4',plan.duration)
    return target,True


def mux_video(video, audio, output, duration):
    # The caller supplies a reviewed matching silent render. Validate duration before
    # stream-copying it, so audio is not silently attached to a different-length cut.
    probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(video)],capture_output=True,timeout=30)
    try:seconds=float(json.loads(probe.stdout)['format']['duration'])
    except (ValueError,KeyError):raise ValueError('Cannot inspect the supplied silent video.') from None
    if probe.returncode or abs(seconds-duration)>.05:
        raise ValueError('Silent video duration differs from the sound plan.')
    result=subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
                           '-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(output)],
                          capture_output=True,timeout=120)
    if result.returncode:raise RuntimeError('FFmpeg could not attach the sound mix.')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    p.add_argument('--profiles',type=Path,help='Editable SoundConfig JSON')
    p.add_argument('--narration',type=Path,help='16-bit PCM WAV; voice is the priority in the mix')
    p.add_argument('--video',type=Path,help='Matching silent MP4, muxed without rerendering the map')
    p.add_argument('--output',type=Path,default=Path('output/content'))
    args=p.parse_args(argv)
    try:
        config=SoundConfig.model_validate_json(args.profiles.read_text(encoding='utf-8')) if args.profiles else SoundConfig()
        target,ok=compile_bundle(args.bundle,config,args.output,narration=args.narration,
                                 sample_root=args.profiles.parent if args.profiles else None,video=args.video)
        print(f'Sound {"ready" if ok else "needs_profiles"}: {target/"sound-report.md"}')
        return 0 if ok else 2
    except (ValueError,RuntimeError,OSError,KeyError,subprocess.SubprocessError) as error:
        from pydantic import ValidationError
        print('Sound failed:','Invalid structured input.' if isinstance(error,ValidationError) else str(error))
        return 1


if __name__=='__main__':raise SystemExit(main())
