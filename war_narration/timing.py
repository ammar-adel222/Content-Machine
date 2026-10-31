"""Compile existing phrase-relative choreography against the actual generated audio."""
from war_director.agent import retime
from .agent import alignment, audio_timing, verify


def align_plan(dossier,script,plan,narration):
    verify(narration,script)
    measured=audio_timing(narration)
    timed=retime(plan,dossier,script,measured)
    phrases=alignment(narration)
    scenes=[dict(scene_id=s.id,start_sec=next(p['start_sec'] for p in phrases if p['scene_id']==s.id),
                 end_sec=max(p['end_sec'] for p in phrases if p['scene_id']==s.id)) for s in script.draft.scenes]
    return timed,dict(script_sha256=narration.script_sha256,duration=narration.frames/narration.sample_rate,
                     basis='Measured phrase clips plus explicit pauses; phrase-level alignment.',
                     phrases=phrases,scenes=scenes,actions=timed.timeline)


def srt(phrases):
    def stamp(seconds):
        ms=round(seconds*1000);secs,ms=divmod(ms,1000);minutes,secs=divmod(secs,60);hours,minutes=divmod(minutes,60)
        return f'{hours:02}:{minutes:02}:{secs:02},{ms:03}'
    return '\n'.join(f"{i}\n{stamp(p['start_sec'])} --> {stamp(p['speech_end_sec'])}\n{' '.join(p['text'].split())}\n"
                     for i,p in enumerate(phrases,1))
