"""Independent word-cue imports and local estimates; no network or new speech generation."""
from array import array
from pathlib import Path
from difflib import SequenceMatcher
import math
import re
from pydantic import Field, model_validator
from typing import Literal
from war_research.models import Model
from .agent import RATE, inspect


class WordCue(Model):
    text: str = Field(min_length=1,max_length=450)
    start: float = Field(ge=0,le=150,allow_inf_nan=False)
    end: float = Field(ge=0,le=150,allow_inf_nan=False)

    @model_validator(mode='after')
    def ordered(self):
        if self.end<self.start:raise ValueError('Word end precedes its start.')
        return self


class CaptionWords(Model):
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    script_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    duration: float = Field(gt=0,le=150,allow_inf_nan=False)
    basis: Literal['local_estimate','asr_word']
    matched_fraction: float = Field(default=0,ge=0,le=1,allow_inf_nan=False)
    phrases: dict[str,list[WordCue]]


def validate_words(words,narration):
    if words.source_sha256!=narration.sha256 or words.script_sha256!=narration.script_sha256:
        raise ValueError('Word cues belong to different narration or script.')
    if abs(words.duration-narration.frames/RATE)>.001:raise ValueError('Word cue duration differs from narration.')
    if set(words.phrases)!={c.phrase_id for c in narration.clips}:raise ValueError('Word cues do not cover the current phrases.')
    for clip in narration.clips:
        cues=words.phrases[clip.phrase_id];start=clip.start_frame/RATE;end=(clip.start_frame+clip.frames)/RATE
        if [c.text for c in cues]!=clip.text.split():raise ValueError('Word cues must preserve the exact script tokens.')
        previous=start
        for cue in cues:
            if cue.start<previous-.001 or cue.end<cue.start or cue.end>end+.001:raise ValueError('Word cues are unordered or outside their measured phrase.')
            previous=cue.end
    return words


def estimate_words(narration):
    phrases={}
    for clip in narration.clips:
        frames,pcm=inspect(Path(clip.file).read_bytes());samples=array('h');samples.frombytes(pcm)
        step=RATE//100;active=[]
        for start in range(0,frames,step):
            values=samples[start:start+step]
            if math.sqrt(sum(v*v for v in values)/len(values))>100:active.append((start,min(frames,start+step)))
        if not active:raise ValueError('No voiced audio found for local word estimates.')
        tokens=clip.text.split();weights=[max(1,len(re.findall(r'[aeiouy]+',t.lower()))-int(t.lower().endswith('e')))+.3*bool(re.search(r'[.!?]$',t)) for t in tokens]
        total=sum(weights);voiced=sum(end-start for start,end in active)
        def point(fraction):
            remaining=voiced*fraction
            for start,end in active:
                if remaining<=end-start:return (clip.start_frame+start+remaining)/RATE
                remaining-=end-start
            return (clip.start_frame+active[-1][1])/RATE
        cues=[];progress=0
        for token,weight in zip(tokens,weights):
            cues.append(WordCue(text=token,start=point(progress/total),end=point((progress+weight)/total)));progress+=weight
        phrases[clip.phrase_id]=cues
    return validate_words(CaptionWords(source_sha256=narration.sha256,script_sha256=narration.script_sha256,
        duration=narration.frames/RATE,basis='local_estimate',phrases=phrases),narration)


def align_words(narration,observed):
    observed=[WordCue(text=str(item['word']),start=item['start'],end=item['end']) for item in observed]
    if observed and observed[-1].end>narration.frames/RATE+.25:raise ValueError('Transcription extends beyond the narration.')
    if not observed or len(observed)>5000:raise ValueError('Invalid transcription word count.')
    for previous,word in zip(observed,observed[1:]):
        if word.start<previous.start-.15:raise ValueError('Transcription words are unordered.')
        if word.start<previous.start:
            word.start=previous.start;word.end=max(word.start,word.end)
    expected=[(clip,token) for clip in narration.clips for token in clip.text.split()]
    normal=lambda text:re.sub(r'[^a-z0-9]','',text.lower())
    matcher=SequenceMatcher(None,[normal(token) for clip,token in expected],[normal(c.text) for c in observed],autojunk=False)
    matches=sum(block.size for block in matcher.get_matching_blocks());coverage=matches/max(len(expected),len(observed))
    if coverage<.85:raise ValueError('Transcription does not match enough of the saved narration.')
    aligned=[None]*len(expected)
    for kind,i,j,a,b in matcher.get_opcodes():
        if kind=='equal':
            for index,word in zip(range(i,j),observed[a:b]):aligned[index]=(word.start,word.end)
        elif i<j:
            start=observed[a].start if a<b else observed[a-1].end if a else 0
            end=observed[b-1].end if a<b else observed[b].start if b<len(observed) else narration.frames/RATE
            end=max(start,end);weights=[max(1,len(token)) for clip,token in expected[i:j]];total=sum(weights);progress=0
            for index,weight in zip(range(i,j),weights):
                aligned[index]=(start+(end-start)*progress/total,start+(end-start)*(progress+weight)/total);progress+=weight
    phrases={};last={}
    for (clip,token),(start,end) in zip(expected,aligned):
        left=clip.start_frame/RATE;right=(clip.start_frame+clip.frames)/RATE
        start=max(left,last.get(clip.phrase_id,left),min(right,start));end=max(start,min(right,end))
        phrases.setdefault(clip.phrase_id,[]).append(WordCue(text=token,start=start,end=end));last[clip.phrase_id]=end
    return validate_words(CaptionWords(source_sha256=narration.sha256,script_sha256=narration.script_sha256,
        duration=narration.frames/RATE,basis='asr_word',matched_fraction=coverage,phrases=phrases),narration)
