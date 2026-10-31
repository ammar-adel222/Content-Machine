import argparse
import json
from pathlib import Path
from uuid import uuid4
from .models import Edit
from .planner import describe
from .store import ProjectStore


def main(argv=None):
    p=argparse.ArgumentParser(description='Saved content projects and targeted revision planning')
    commands=p.add_subparsers(dest='command',required=True)
    create=commands.add_parser('init');create.add_argument('--topic',required=True)
    create.add_argument('--output',type=Path,default=Path('output/projects'));create.add_argument('--seconds',type=int,default=105)
    create.add_argument('--aspect',choices=['portrait','landscape'],default='portrait')
    imported=commands.add_parser('import-media');imported.add_argument('bundle',type=Path);imported.add_argument('--video',type=Path,required=True)
    imported.add_argument('--output',type=Path,default=Path('output/projects'));imported.add_argument('--picture-approved',action='store_true')
    for command in ('status','plan','run','approve'):
        sub=commands.add_parser(command);sub.add_argument('project',type=Path);sub.add_argument('--revision')
        if command=='run':sub.add_argument('--env-file',type=Path,default=Path('.env'))
    edit=commands.add_parser('edit');edit.add_argument('project',type=Path);edit.add_argument('--parent',required=True)
    edit.add_argument('--kind',required=True);edit.add_argument('--settings',type=Path);edit.add_argument('--notes',default='')
    edit.add_argument('--scene',action='append',default=[]);edit.add_argument('--object',action='append',default=[])
    edit.add_argument('--request-id')
    args=p.parse_args(argv)
    try:
        if args.command=='init':
            store=ProjectStore.create(args.output/uuid4().hex,args.topic,aspect=args.aspect,target_seconds=args.seconds)
            print(f'Project: {store.root}');print(json.dumps(describe(store.load()),indent=2));return 0
        if args.command=='import-media':
            from .media import import_media
            store=import_media(args.output/uuid4().hex,args.bundle,args.video,picture_approved=args.picture_approved)
            print(f'Project: {store.root}');print(json.dumps(describe(store.load()),indent=2));return 0
        store=ProjectStore(args.project)
        if args.command=='edit':
            patch=json.loads(args.settings.read_text(encoding='utf-8')) if args.settings else {}
            values=dict(parent_revision=args.parent,kind=args.kind,patch=patch,notes=args.notes,
                        scene_ids=args.scene,object_ids=args.object)
            if args.request_id:values['request_id']=args.request_id
            revision=store.edit(Edit(**values))
        elif args.command=='approve':
            from .graph import Runner
            revision=Runner(store,{}).approve(args.revision or store.metadata()['head'])
        elif args.command=='run':
            from .graph import Runner
            # Live adapters are explicit. Missing ones stop with an actionable state.
            from .media import adapters
            from .authoring import adapters as authoring_adapters
            from .speech import adapters as speech_adapters
            from war_research.providers import load_env
            if args.env_file.exists():load_env(args.env_file)
            revision=Runner(store,adapters()|authoring_adapters()|speech_adapters()).run(args.revision)
        else:revision=store.load(args.revision)
        print(json.dumps(describe(revision)|{'executed':revision.executed,'reused':revision.reused,
                                           'issues':revision.issues,'budgets':store.budgets(revision.id)},indent=2))
        return 2 if args.command=='run' and revision.status in ('needs_input','quota_wait','superseded') else 0
    except (ValueError,RuntimeError,OSError,KeyError) as error:
        from pydantic import ValidationError
        print('Project failed:','Invalid structured input.' if isinstance(error,ValidationError) else str(error));return 1


if __name__=='__main__':raise SystemExit(main())
