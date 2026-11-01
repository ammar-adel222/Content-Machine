"""Content-addressed phrase WAVs, exact silence assembly and recoverable clip receipts."""
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4
import wave
from array import array
import math
from war_director.models import AudioTiming
from war_writer.agent import fingerprint
from war_writer.storage import tts_plan
from .models import Clip, Narration, NarrationRequest

RATE=24000


def digest(data):return hashlib.sha256(data).hexdigest()


def inspect(data):
    try:
        with wave.open(io.BytesIO(data),'rb') as audio:
            frames=audio.getnframes()
            if audio.getparams()[:3]!=(1,2,RATE) or audio.getcomptype()!='NONE' or not 0<frames<=120*RATE:
                raise ValueError('TTS clips must be 24kHz mono 16-bit PCM, between 0 and 120 seconds.')
            pcm=audio.readframes(frames)
            if len(pcm)!=frames*2:raise ValueError('TTS audio is truncated.')
    except (wave.Error,EOFError):raise ValueError('TTS output is not a readable PCM WAV.') from None
    # Reject empty/silent clips. Transcript fidelity still requires listening or ASR.
    if not any(pcm):raise ValueError('TTS output contains only silence.')
    return frames,pcm


def trim_edges(data):
    frames,pcm=inspect(data);samples=array('h');samples.frombytes(pcm)
    block=RATE//100;active=[]
    for start in range(0,frames,block):
        values=samples[start:start+block]
        if math.sqrt(sum(v*v for v in values)/len(values))>100:active.append(start)
    if not active:return data
    first=max(0,active[0]-round(.04*RATE));last=min(frames,active[-1]+block+round(.07*RATE))
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(RATE);audio.writeframes(pcm[first*2:last*2])
    return buffer.getvalue()


def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(uuid4().hex+'.tmp')
    temp.write_bytes(data);temp.replace(path)


def prepare(script,request):
    if script.status!='ready' or script.issues:raise ValueError('A ready, reviewed script is required for narration.')
    chunks=tts_plan(script)['chunks'];ids={c['id'] for c in chunks}
    if not chunks or len(ids)!=len(chunks):raise ValueError('Script phrase IDs must be unique and nonempty.')
    if set(request.phrase_notes)-ids:raise ValueError('Narration overrides reference an unknown phrase ID.')
    prepared=[]
    for chunk in chunks:
        pronunciation=[f'{p.term}: {p.say_as}' for p in script.draft.pronunciations if p.term.casefold() in chunk['text'].casefold()]
        direction=' '.join(p for p in [chunk['direction'],request.notes,request.phrase_notes.get(chunk['id'],''),
            'Pronunciation guidance: '+ '; '.join(pronunciation) if pronunciation else '',
            'Read the transcript exactly. Do not add an introduction or trailing commentary.'] if p)
        identity={'version':1,'text':chunk['text'],'direction':direction,'voice':request.voice,'model':request.model}
        if request.trim_silence:identity['edge_trim']='rms-10ms-v1'
        key=digest(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode())
        prepared.append((chunk,direction,key,chunk['pause_after_ms']))
    return prepared


def generate(script,output,cache,provider_factory,request=None,consume=lambda:None):
    request=NarrationRequest.model_validate((request or NarrationRequest()).model_dump())
    chunks=prepare(script,request)
    output=Path(output).resolve();cache=Path(cache).resolve();output.mkdir(parents=True,exist_ok=True)
    calls=reused=clock=0;clips=[];assembled=bytearray();provider=None
    for chunk,direction,key,pause in chunks:
        path=cache/(key+'.wav');receipt=cache/(key+'.json')
        if path.exists() and receipt.exists():
            data=path.read_bytes();metadata=json.loads(receipt.read_text(encoding='utf-8'))
            if metadata!={'key':key,'sha256':digest(data)}:raise ValueError('Cached narration failed its integrity check; restore or remove that cache entry.')
            frames,pcm=inspect(data);reused+=1
        else:
            if calls>=request.max_requests:raise ValueError('Narration request limit reached; completed clips are cached. Raise max_requests to resume.')
            if provider is None:provider=provider_factory()
            consume();calls+=1
            data=provider.synthesize(chunk['text'],direction,request.model,request.voice)
            if request.trim_silence:data=trim_edges(data)
            frames,pcm=inspect(data)
            atomic(path,data);atomic(receipt,json.dumps({'key':key,'sha256':digest(data)}).encode())
        pause_frames=pause*RATE//1000
        if clock+frames+pause_frames>150*RATE:raise ValueError('Measured narration exceeds 150 seconds; revise delivery or script. Completed clips are cached.')
        clips.append(Clip(phrase_id=chunk['id'],scene_id=chunk['scene_id'],text=chunk['text'],direction=direction,
            key=key,file=str(path),sha256=digest(data),frames=frames,pause_frames=pause_frames,start_frame=clock))
        assembled.extend(pcm);assembled.extend(b'\0'*(pause_frames*2));clock+=frames+pause_frames
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(RATE);audio.writeframes(assembled)
    audio=buffer.getvalue();path=output/('narration-'+digest(audio)+'.wav');atomic(path,audio)
    return Narration(script_sha256=fingerprint(script),request=request,clips=clips,frames=clock,
        wave=str(path),sha256=digest(audio),requests=calls,reused=reused,warnings=([] if 90<=clock/RATE<=120 else [
            'Measured narration is outside the preferred 90–120 seconds; consider revising script or delivery.'])+[
            'Phrase boundaries are measured from generated clips; no word-level forced alignment or transcript verification was performed.',
            'Audition pronunciation, phrase joins and delivery before publishing.'])


def audio_timing(narration):
    return AudioTiming(script_sha256=narration.script_sha256,
        durations={c.phrase_id:c.frames/RATE for c in narration.clips})


def alignment(narration):
    return [dict(id=c.phrase_id,scene_id=c.scene_id,text=c.text,start_sec=c.start_frame/RATE,
        speech_end_sec=(c.start_frame+c.frames)/RATE,end_sec=(c.start_frame+c.frames+c.pause_frames)/RATE,
        pause_after_ms=c.pause_frames*1000//RATE) for c in narration.clips]


def save(narration,output):
    output=Path(output);data=narration.model_dump_json(indent=2).encode()
    path=output/('narration-'+digest(data)+'.json');atomic(path,data);return path


def verify(narration,script):
    if narration.script_sha256!=fingerprint(script):raise ValueError('Narration belongs to a different script version.')
    prepared=prepare(script,narration.request)
    if len(prepared)!=len(narration.clips):raise ValueError('Narration does not cover every script phrase.')
    clock=0
    for clip,(chunk,direction,key,pause) in zip(narration.clips,prepared):
        if (clip.phrase_id,clip.scene_id,clip.text,clip.key,clip.direction,clip.start_frame,clip.pause_frames)!=(
            chunk['id'],chunk['scene_id'],chunk['text'],key,direction,clock,pause*RATE//1000):
            raise ValueError('Narration phrase identity or clock does not match the script.')
        data=Path(clip.file).read_bytes()
        frames,_=inspect(data)
        if digest(data)!=clip.sha256 or frames!=clip.frames:raise ValueError('Narration clip integrity check failed.')
        clock+=clip.frames+clip.pause_frames
    data=Path(narration.wave).read_bytes()
    if clock!=narration.frames or clock>150*RATE or digest(data)!=narration.sha256:raise ValueError('Narration waveform integrity check failed.')
    try:
        with wave.open(io.BytesIO(data),'rb') as audio:
            if audio.getparams()[:3]!=(1,2,RATE) or audio.getnframes()!=clock or len(audio.readframes(clock))!=clock*2:
                raise ValueError('Narration waveform does not match its measured clock.')
    except (wave.Error,EOFError):raise ValueError('Narration waveform is not a readable PCM WAV.') from None
