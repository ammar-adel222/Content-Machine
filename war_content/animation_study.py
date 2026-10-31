"""Build a non-publishable movement study from existing terrain and approved units."""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4
from .agent import ContentError, Library
from .geodata import Battlefield
from .play import WEB, RUNTIME, select_bundle


def build_study(terrain, library, output, concepts=('tank', 'war_elephant')):
    source = Path(terrain)
    original = json.loads((source / 'scene.json').read_text(encoding='utf-8'))
    field = Battlefield.model_validate(original['battlefield']).model_dump(mode='json')
    if len(concepts) != 2:
        raise ValueError('Choose exactly two unit concepts for the movement study.')
    catalog = Library(library)
    available = catalog.briefs()
    assets = []
    for concept in concepts:
        brief = next((b for b in available if b['category'] == 'unit' and b['concept'] == concept), None)
        if brief is None:
            raise ContentError(f'Generate and approve a {concept} unit before making this study.')
        from .models import Brief
        asset = catalog.get(Brief.model_validate(brief))
        if asset.review_basis != 'rendered_image' or asset.review_version != 2:
            raise ContentError(f'{concept} needs a current image review first.')
        assets.append(asset)
    # These are illustration coordinates, never a historical deployment plan.
    forces = [dict(id=f'group{i}', name=a.design.label, side=('Blue', 'Red')[i], kind='army',
                   position={'x':.58,'y':.68}, subgroups=4) for i,a in enumerate(assets)]
    actions, timeline = [], []
    for i in range(2):
        uid=f'group{i}'; shift=i*12
        timeline.append(dict(action_id=f'intro-{uid}',unit_id=uid,kind='introduce',start_sec=shift,end_sec=shift))
        for number,start,end,route,formation in (
            (0,1,6,[{'x':.58,'y':.68},{'x':.58,'y':.61},{'x':.70,'y':.54},{'x':.70,'y':.45}],'column'),
            (1,6,10,[{'x':.70,'y':.45},{'x':.64,'y':.34}],('line','wedge')[i])):
            action=dict(id=f'{uid}-move{number}',unit_id=uid,kind='move',route=route,formation=formation,stagger=.2)
            actions.append(action)
            timeline.append(dict(action_id=action['id'],unit_id=uid,kind='move',start_sec=start+shift,end_sec=end+shift))
        if i==0:
            actions.append(dict(id='fade-blue',unit_id=uid,kind='fade'))
            timeline.append(dict(action_id='fade-blue',unit_id=uid,kind='fade',start_sec=11,end_sec=12))
    phases=[(0,1,'Prepare to move'),(1,6,'Column · staggered departure'),(6,10,'Deploy into line'),
            (10,12,'Halt · hold formation'),(12,13,'A second unit design'),(13,18,'Column · follow the bend'),
            (18,22,'Open into a wedge'),(22,24,'Halt · hold formation')]
    scenes=[dict(scene_id=f'phase{i}',start=start,end=end,labels=[label],actions=actions if i==0 else []) for i,(start,end,label) in enumerate(phases)]
    payload=dict(schema_version='1.0',purpose='unit_animation_study',topic='Unit movement study',duration=24,
                 battlefield=field,animation_camera={'x':.63,'y':.52},scenes=scenes,timeline=timeline,
                 blueprint=dict(scale='tactical',forces=forces,scenes=scenes),
                 bindings=dict(unit={f'group{i}':f'design{i}' for i in range(2)}),
                 assets={f'design{i}':a.design.model_dump() for i,a in enumerate(assets)},
                 captions=[dict(start=s['start'],end=s['end'],text=s['labels'][0]+'. Illustrative movement, not a historical battle.') for s in scenes])
    target=Path(output)/uuid4().hex
    # Resolve and constrain local resource paths before copying anything.
    relief=Path(field['layer']['relief'])
    if relief.name != str(relief) or not relief.name.startswith('relief-') or relief.suffix != '.png':
        raise ValueError('Study needs a bundle-local relief image.')
    for name in ('pixi.min.js',str(relief)):
        if not (source/name).is_file():
            raise ContentError(f'Terrain bundle is missing {name}.')
    target.mkdir(parents=True,exist_ok=False)
    (target/'scene.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'content.json').write_text(json.dumps(dict(status='preview',publishing_ready=False,purpose='unit_animation_study')),encoding='utf-8')
    for name in RUNTIME:
        shutil.copyfile(WEB/name,target/name)
    for name in ('pixi.min.js',str(relief)):
        shutil.copyfile(source/name,target/name)
    (target/'report.md').write_text('# Unit animation study\n\n24-second vertical-first preview using measured terrain and approved unit designs.\n\n'
        'Positions, routes, groups and timing are illustrative. This is not a historical battle replay and is not publishing-ready.\n'
        'Shows independent departures, columns following bends, line/wedge deployment and stable halts. No audio.\n',encoding='utf-8')
    return target


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--terrain',type=Path)
    p.add_argument('--library',type=Path,default=Path('output/visual-library/atlas-ink-v1'))
    p.add_argument('--output',type=Path,default=Path('output/content'))
    p.add_argument('--concepts',nargs=2,default=['tank','war_elephant'])
    args=p.parse_args(argv)
    try:
        source=args.terrain or select_bundle(args.output,mode='battlefield')
        target=build_study(source,args.library,args.output,args.concepts)
        print(f'Animation study: {target}')
        return 0
    except (ValueError,RuntimeError,OSError,KeyError) as error:
        print(f'Animation study failed: {error}')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
