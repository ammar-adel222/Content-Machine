"""Derive bounded sound cues from the saved animation timeline, not narration nouns."""
import hashlib
import json
import math
import random
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
    animated=not scene.get('geography') and (not scene.get('battlefield') or scene.get('purpose') in ('unit_animation_study','battlefield_replay'))

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
    if animated and config.clash_enabled:
        explicit={spot.action_id for spot in config.spots}
        for action in actions:
            if action['kind']!='engage' or action.get('action_id') in explicit:continue
            actor=forces.get(action.get('unit_id'));target=forces.get(action.get('target_id'))
            if actor is None or target is None or actor.get('side')==target.get('side'):continue
            start,end=float(action['start_sec']),float(action['end_sec'])
            if not 0<=start<end<=duration:raise ValueError('Engagement sound has invalid timeline bounds.')
            intros={a['unit_id']:a['start_sec'] for a in actions if a['kind']=='introduce'}
            if any(uid not in intros or intros[uid]>start for uid in (actor['id'],target['id'])):
                raise ValueError('Engagement sound cannot precede either force introduction.')
            def position(force):
                point=force.get('position')
                for row in sorted(actions,key=lambda row:row['start_sec']):
                    if row['unit_id']!=force['id'] or row['kind'] not in ('move','withdraw') or row['start_sec']>start:continue
                    route=row.get('route',[])
                    if len(route)<2:continue
                    span=row['end_sec']-row['start_sec']
                    lengths=[math.hypot(b['x']-a['x'],b['y']-a['y']) for a,b in zip(route,route[1:])]
                    remaining=sum(lengths)*min(1,max(0,(start-row['start_sec'])/max(span,1e-8)))
                    point=route[-1]
                    for a,b,length in zip(route,route[1:],lengths):
                        if length and remaining<=length:
                            f=remaining/length;point={'x':a['x']+(b['x']-a['x'])*f,'y':a['y']+(b['y']-a['y'])*f};break
                        remaining-=length
                return point
            a,b=position(actor),position(target)
            if a is None or b is None:raise ValueError('Engagement sound needs both force positions.')
            if scene['blueprint']['scale']=='tactical' and actor.get('kind') in ('infantry','cavalry','army') and math.hypot(a['x']-b['x'],a['y']-b['y'])>.080001:
                raise ValueError('Engagement sound starts before opposing forces reach contact.')
            cues.append(SoundCue(unit_id=actor['id'],action_id=action['action_id'],effect='clash',
                start=start,end=min(end,start+.6),gain_db=config.clash_gain_db,pan_start=0,pan_end=0,
                seed=seed(action['action_id']),subgroup=0,loop=False))
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
    for texture in config.textures:
        force=forces.get(texture.unit_id)
        claims={c for item in list(forces.values())+list(definitions.values()) for c in item.get('claim_ids',[])}
        if not animated or force is None or texture.claim_id not in claims:
            raise ValueError('Battle texture needs an animated force and a claim referenced by this plan.')
        intro=next((a for a in actions if a['kind']=='introduce' and a['unit_id']==texture.unit_id),None)
        if not intro or not intro['start_sec']<=texture.start<texture.end<=duration:
            raise ValueError('Battle texture must follow introduction and stay inside the video.')
        rng=random.Random(seed(texture.claim_id+texture.unit_id));time=texture.start+.05
        while time<texture.end:
            cues.append(SoundCue(unit_id=texture.unit_id,action_id='texture:'+texture.claim_id,effect='clash',
                start=time,end=min(texture.end,time+.6),gain_db=texture.gain_db,
                pan_start=rng.uniform(-.3,.3),pan_end=0,seed=seed(texture.claim_id+str(time)),subgroup=0,loop=False))
            time+=rng.uniform(1.7,3.4)
    scene_hash=hashlib.sha256(json.dumps(scene,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return SoundPlan(scene_sha256=scene_hash, duration=duration, cues=cues, unresolved_units=sorted(unresolved),omitted_actions=omitted)
