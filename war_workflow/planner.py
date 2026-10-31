"""Content dependencies control invalidation; review gates control admissibility."""
from dataclasses import dataclass, field
import hashlib
import json
from .models import Stage


def fingerprint(value):
    if hasattr(value,'model_dump'):value=value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def computation_key(stage,version,params,instructions,inputs):
    return fingerprint(dict(stage=stage,version=version,params=params,instructions=instructions,inputs=inputs))


@dataclass(frozen=True)
class Spec:
    inputs: dict[str,str] = field(default_factory=dict)  # dependency -> semantic view
    gates: tuple[str,...] = ()
    review: bool = False


SPECS={
    'research':Spec(),
    'writing':Spec({'research':'claims'}),
    'script_review':Spec({'research':'claims','writing':'content'},review=True),
    'direction':Spec({'research':'content','writing':'visual'},('script_review',)),
    'plan_review':Spec({'research':'content','writing':'visual','direction':'content'},review=True),
    'narration':Spec({'writing':'speech'},('script_review',)),
    'terrain':Spec({'research':'geography','direction':'spatial'},('plan_review',)),
    'assets':Spec({'research':'claims','direction':'units'},('plan_review',)),
    'timing':Spec({'research':'content','direction':'content','narration':'timing','writing':'content'},('plan_review',)),
    'effects':Spec({'timing':'effects','direction':'sound_profiles'}),
    'music_source':Spec({'timing':'duration'}),
    'mix':Spec({'narration':'waveform','effects':'waveform','music_source':'waveform'}),
    'visual_review':Spec({'terrain':'content','assets':'content','timing':'visual','writing':'captions'},review=True),
    'audio_review':Spec({'mix':'content'},review=True),
    'picture':Spec({'terrain':'content','assets':'content','timing':'visual','writing':'captions'},('visual_review','audio_review')),
    'mux':Spec({'picture':'content','mix':'content'},('visual_review','audio_review')),
    'final_review':Spec({'mux':'content'},review=True),
}
ROOTS={
    'research':('research',),'script':('writing',),'narration':('narration',),'route':('direction',),
    'terrain':('terrain',),'unit_design':('assets',),'camera':('visual_review','picture'),
    'caption':('visual_review','picture'),'format':('visual_review','picture'),
    'sound_effect':('effects',),'music_track':('music_source',),'music_mix':('mix',),'mix_levels':('mix',),
}


def order():
    pending=dict(SPECS);result=[]
    while pending:
        ready=[s for s,spec in pending.items() if set(spec.inputs).union(spec.gates)<=set(result)]
        if not ready:raise ValueError('Workflow dependencies contain a cycle or unknown stage.')
        for stage in ready:result.append(stage);pending.pop(stage)
    return result


ORDER=order()


def affected(roots):
    dirty=set(roots)
    if dirty-set(SPECS):raise ValueError('Unknown workflow stage.')
    while True:
        updated=dirty|{s for s,spec in SPECS.items() if set(spec.inputs)&dirty}
        if updated==dirty:return [s for s in ORDER if s in dirty]
        dirty=updated


def describe(revision):
    return dict(revision=revision.id,status=revision.status,
                pending=[s for s in ORDER if s in revision.dirty],
                retained=[s for s in ORDER if s not in revision.dirty and s in revision.artifacts],
                scope=revision.edit.model_dump(mode='json') if revision.edit else None,
                drafts=revision.drafts,
                note='Pending stages may reuse cached results after their current input views are checked.')
