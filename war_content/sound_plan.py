"""Derive bounded sound cues from the saved animation timeline, not narration nouns."""
import hashlib
import json
import math
from .sound_models import SoundConfig, SoundCue, SoundPlan


def compile_plan(scene, config: SoundConfig):
    duration = float(scene['duration'])
    forces = {f['id']: f for f in scene.get('blueprint', {}).get('forces', [])}
    if set(config.profiles) - set(forces):
        raise ValueError('Sound profiles reference unknown forces.')
    definitions = {a['id']: a for s in scene.get('blueprint', {}).get('scenes', []) for a in s['actions']}
    actions = [{**definitions.get(a.get('action_id'), {}), **a} for a in scene.get('timeline', [])]
    known = {a.get('action_id'): a for a in actions}
    cues, unresolved, omitted = [], set(), []
    animated=not scene.get('geography') and (not scene.get('battlefield') or scene.get('purpose')=='unit_animation_study')

    def seed(text):
        return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)

    for a in actions:
        if a['kind'] not in ('move', 'withdraw'):
            continue
        if not animated:
            omitted.append(a['action_id'])
            continue
        uid = a['unit_id']
        if uid not in forces or not a.get('route') or len(a['route']) < 2:
            raise ValueError('Movement sound needs a known force and route.')
        force = forces[uid]
        intro = next((r for r in actions if r['kind'] == 'introduce' and r['unit_id'] == uid), None)
        if intro is None or intro['start_sec'] > a['start_sec']:
            raise ValueError('Movement sound cannot precede unit introduction.')
        start, end = float(a['start_sec']), float(a['end_sec'])
        if not 0 <= start < end <= duration:
            raise ValueError('Movement sound has invalid timeline bounds.')
        if not any(p != a['route'][0] for p in a['route'][1:]):
            continue
        profile = config.profiles.get(uid)
        fallback = {'infantry': 'footsteps', 'cavalry': 'hooves'}.get(force.get('kind'))
        if profile is None and fallback is None:
            unresolved.add(uid)
            continue
        effect = profile.movement if profile else fallback
        if effect == 'none':
            continue
        gain = profile.gain_db if profile else -14
        count = 1 if scene['blueprint']['scale'] == 'campaign' else int(force['subgroups'])
        if not 1 <= count <= 12:
            raise ValueError('Sound subgroups must be 1–12.')
        # A symbolic formation gets at most three Foley layers, never a literal
        # soldier-count barrage. Select real actor indices to match departure times.
        indices = sorted({round(i * (count-1) / max(1, min(3, count)-1)) for i in range(min(3, count))})
        stagger = float(a.get('stagger', .15))
        if not 0 <= stagger <= .3:
            raise ValueError('Sound stagger must match the animation contract.')
        p, q = a['route'][0], a['route'][-1]
        for index in indices:
            delay = min(stagger * (end-start), 1.2) * index / max(1, count-1)
            stop = min([end] + [f['end_sec'] for f in actions if f['kind'] == 'fade' and f['unit_id'] == uid and f['start_sec'] < end])
            if stop <= start + delay:
                continue
            cues.append(SoundCue(unit_id=uid, action_id=a['action_id'], effect=effect,
                start=start+delay, end=stop, gain_db=gain-10*math.log10(len(indices)),
                pan_start=max(-.5,min(.5,(p['x']-.5)*.6)), pan_end=max(-.5,min(.5,(q['x']-.5)*.6)),
                seed=seed(uid+':'+str(index)), subgroup=index))
    for spot in config.spots:
        if not animated:
            raise ValueError('This map has static area callouts, not synchronized weapon animation.')
        action = known.get(spot.action_id)
        if not action or action['kind'] != 'engage' or action.get('unit_id') not in forces:
            raise ValueError('Weapon/impact sounds need an explicit engage action.')
        if not action['start_sec'] <= spot.time < action['end_sec']:
            raise ValueError('Weapon sound is outside its engagement cue.')
        cues.append(SoundCue(unit_id=action['unit_id'], action_id=spot.action_id, effect=spot.effect,
            start=spot.time, end=min(duration,spot.time+({'cannon':2.0,'clash':.6}.get(spot.effect, .9))),
            gain_db=spot.gain_db, pan_start=0, pan_end=0, seed=seed(spot.action_id+str(spot.time)), subgroup=0, loop=False))
    scene_hash=hashlib.sha256(json.dumps(scene,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return SoundPlan(scene_sha256=scene_hash, duration=duration, cues=cues, unresolved_units=sorted(unresolved),omitted_actions=omitted)
