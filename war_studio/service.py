"""Connect browser actions to immutable project contracts and the durable job queue."""
from datetime import datetime,timezone
from pathlib import Path
import json,re,time
from uuid import uuid4
from war_workflow.models import Edit,Artifact
from war_workflow.planner import ORDER,fingerprint
from war_workflow.store import ProjectStore,Conflict,WorkflowError
from .contracts import PLATFORMS,Metadata,PUBLISH_POLICY
from .database import Database


class Studio:
    def __init__(self,projects,root):self.projects=Path(projects).resolve();self.projects.mkdir(parents=True,exist_ok=True);self.db=Database(root)

    def store(self,id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',id):raise ValueError('Invalid project ID.')
        path=(self.projects/id).resolve()
        if not path.is_relative_to(self.projects):raise ValueError('Invalid project path.')
        return ProjectStore(path)

    def receipt(self,store,revision,stage):
        id=revision.artifacts.get(stage)
        if not id:return None
        # Display receipts without hashing every large WAV/MP4 on each progress poll.
        return Artifact.model_validate_json(store.receipt_path(stage,id).read_text(encoding='utf-8'))

    def metadata(self,id,revision):
        result=self.db.get('metadata:'+id+':'+revision.id)
        if result:return result
        store=self.store(id);script=self.receipt(store,revision,'writing')
        draft=script.output.data.get('draft',{}) if script else {}
        title=draft.get('title',store.metadata()['topic']);description=draft.get('caption','')
        return Metadata(revision=revision.id,posts={p:{'title':title,'description':description,'hashtags':'#MilitaryHistory #HistoryExplained'} for p in PLATFORMS},selected=list(PLATFORMS)).model_dump(mode='json')

    def summaries(self):
        result=[]
        for folder in self.projects.iterdir():
            if not folder.is_dir() or not (folder/'project.sqlite').is_file():continue
            try:result.append(self.summary(folder.name))
            except (ValueError,WorkflowError,OSError):continue
        return sorted(result,key=lambda p:p['created'],reverse=True)

    def summary(self,id):
        store=self.store(id);revision=store.load();job=self.db.latest(id)
        script=self.receipt(store,revision,'writing');mux=self.receipt(store,revision,'mux');mix=self.receipt(store,revision,'mix')
        title=script.output.data.get('draft',{}).get('title') if script else None
        duration=mux.output.data.get('duration') if mux else None
        with store.connection() as db:
            revisions=[json.loads(row['payload']) for row in db.execute('SELECT payload FROM revisions ORDER BY rowid')]
        posts=[]
        with self.db.connect() as db:
            for row in db.execute('SELECT * FROM publications WHERE project=?',(id,)):
                payload=json.loads(row['payload']);posts.append({k:row[k] for k in ('revision','platform','status','updated')}|{k:payload.get(k) for k in ('id','url','issue')})
        active=job and job['status'] in ('queued','running')
        finished=revision.status in ('awaiting_review','approved') and not revision.dirty
        status='generating' if active else 'ready' if finished else 'draft'
        if posts and any(r['revision']==revision.id and r['status']=='published' for r in posts):status='published' if finished else status
        meta=self.metadata(id,revision)
        return {'id':id,'title':title or store.metadata()['topic'],'topic':script.output.data.get('topic',store.metadata()['topic']) if script else store.metadata()['topic'],
          'kind':revision.params.get('research',{}).get('scope','battle'),'format':revision.params.get('picture',{}).get('aspect','portrait'),
          'status':status,'workflow_status':revision.status,'duration':f'{int(duration)//60}:{int(duration)%60:02}' if duration else '—',
          'seconds':duration,'created':revision.created_at.isoformat(),'date':revision.created_at.date().isoformat(),'revision':len(revisions),'revision_id':revision.id,
          'history':[{'revision':i+1,'id':r['id'],'title':r.get('edit',{}).get('kind','Original') if r.get('edit') else 'Original','date':r['created_at']} for i,r in enumerate(revisions[:-1])],
          'edits':[{'revision':i+1,'scope':r['edit']['kind'],'text':self.db.get('edit-note:'+r['edit']['request_id'],r['edit']['notes']),'date':r['created_at']} for i,r in enumerate(revisions) if r.get('edit')],
          'metadata':meta['posts'],'selectedPlatforms':meta['selected'],'publish_options':{k:v for k,v in meta.items() if k not in ('posts','selected','revision')},
          'video_url':f'/api/projects/{id}/video?revision={revision.id}&artifact={mux.id[:12]}' if mux else None,
          'stages':[{'name':s,'status':'running' if active and job['stage']==s else 'pending' if s in revision.dirty else 'done'} for s in ORDER],
          'issues':revision.issues,'job':{k:job[k] for k in ('id','kind','status','stage','issue','cancel')} if job else None,
          'publications':posts,'mix_settings':mix.output.data.get('mix_settings',{}) if mix else {},'sample':False,'demo':False}

    def create(self,request):
        id=uuid4().hex;store=ProjectStore.create(self.projects/id,request.topic or 'Researcher’s choice',aspect=request.format,target_seconds=request.seconds)
        revision=store.load();revision.params['research'].update(mode='specific' if request.topic else 'auto',topic=request.topic,scope=request.kind)
        revision.params['terrain']={'mode':request.terrain};store.save(revision)
        self.db.enqueue(id,revision.id,'generate');return self.summary(id)

    def edit(self,id,request):
        store=self.store(id)
        structured=request.kind in ('camera','caption','sound_effect','music_track','music_mix','mix_levels')
        if structured and not request.patch:raise ValueError('This edit target needs explicit settings. Use the audio level controls or advanced saved-contract settings.')
        with store.run_lock():
            latest=self.db.latest(id)
            if latest and latest['status'] in ('queued','running'):raise Conflict('Wait for or cancel the active job before editing.')
            # Source paths are a local backend capability, never arbitrary filesystem reads.
            for key in ('source_bundle','caption_word_timing'):
                if request.patch.get(key):
                    path=Path(request.patch[key]).resolve()
                    if not path.is_relative_to(self.projects.parent):raise ValueError('Source files must be inside the project output directory.')
            if request.kind in ('music_mix','mix_levels'):
                from war_content.music_models import MixSettings
                current=self.receipt(store,store.load(),'mix')
                MixSettings.model_validate((current.output.data.get('mix_settings',{}) if current else {})|request.patch)
            revision=store.edit(Edit(parent_revision=request.revision,kind=request.kind,patch=request.patch,notes='' if structured else request.notes,request_id=request.request_id))
            self.db.put('edit-note:'+request.request_id,request.notes)
            prior=self.db.get('metadata:'+id+':'+request.revision)
            if prior:self.db.put('metadata:'+id+':'+revision.id,prior|{'revision':revision.id})
            self.db.enqueue(id,revision.id,'generate')
        return self.summary(id)

    def resume(self,id,revision):
        store=self.store(id)
        if store.load().id!=revision:raise Conflict('Reload the latest revision before resuming.')
        return self.db.enqueue(id,revision,'generate')

    def save_metadata(self,id,request):
        revision=self.store(id).load()
        if request.revision!=revision.id:raise Conflict('Project changed; reload before saving post details.')
        if len(set(request.selected))!=len(request.selected):raise ValueError('Publishing platforms must be unique.')
        if set(request.posts)!=set(PLATFORMS):raise ValueError('Save metadata for all three platforms.')
        self.db.put('metadata:'+id+':'+revision.id,request.model_dump(mode='json'))

    def video(self,id,revision=None):
        store=self.store(id);rev=store.load(revision)
        if 'mux' not in rev.artifacts:raise WorkflowError('This revision has no completed video.')
        artifact=store.read_artifact('mux',rev.artifacts['mux']);return Path(artifact.output.files['video']),artifact.file_hashes['video']

    def prepare(self,id,platforms):
        store=self.store(id);revision=store.load()
        if revision.status not in ('awaiting_review','approved') or revision.dirty:raise Conflict('Finish and review this revision before publishing.')
        metadata=self.metadata(id,revision);video,sha=self.video(id,revision.id)
        if not metadata['selected']:raise ValueError('Choose at least one publishing platform.')
        summary=self.summary(id);accounts={};existing=[]
        for p in metadata['selected']:
            receipt=self.db.publication(id,revision.id,p)
            if receipt and receipt['status']!='failed':existing.append(p);continue
            profile=platforms.profile(p);platforms.validate(p,metadata['posts'][p],metadata,profile,summary['seconds'] or 0)
            if p=='tiktok' and video.stat().st_size>64*1024*1024:raise ValueError('TikTok upload currently supports files up to 64 MB.')
            if p=='instagram' and profile.get('upload_method')=='temporary_https' and video.stat().st_size>128*1024*1024:raise ValueError('Instagram temporary hosting supports files up to 128 MiB.')
            accounts[p]=profile
        if not accounts:raise Conflict('Selected platforms already have receipts. Refresh their status instead of republishing.')
        ticket=uuid4().hex
        payload={'project':id,'revision':revision.id,'sha256':sha,'metadata':metadata,'accounts':accounts,'skip':existing,'created':time.time(),'policy':PUBLISH_POLICY}
        self.db.put('ticket:'+ticket,payload)
        return {'ticket':ticket,'revision':revision.id,'video_sha256':sha,'metadata':metadata,'accounts':accounts,'skip':existing}

    def confirm(self,id,ticket):
        item=self.db.get('ticket:'+ticket)
        if not item or item['project']!=id or time.time()-item['created']>600:raise Conflict('Publishing review expired; review the post again.')
        if item.get('policy')!=PUBLISH_POLICY:raise Conflict('Publishing method changed; reload and review the post again.')
        store=self.store(id);revision=store.load()
        if revision.id!=item['revision'] or self.metadata(id,revision)!=item['metadata'] or self.video(id,revision.id)[1]!=item['sha256']:raise Conflict('Video or post details changed; review the post again.')
        # Atomic ticket consumption and queue insertion: double clicks return the same job.
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT id FROM jobs WHERE kind=? AND payload=?',('publish',json.dumps({'ticket':ticket}))).fetchone()
            if existing:return self.db.job(existing['id'])
            now=time.time();job=uuid4().hex
            try:db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,0)',(job,id,revision.id,'publish',json.dumps({'ticket':ticket}),'queued','','',now,now))
            except __import__('sqlite3').IntegrityError:raise Conflict('This project already has an active job.') from None
        return self.db.job(job)

    def analytics(self,platform='all',video='all'):
        if platform not in ('all',*PLATFORMS):raise ValueError('Unknown analytics platform.')
        with self.db.connect() as db:
            rows=[json.loads(r['payload'])|{'project':r['project'],'platform':r['platform'],'updated':r['updated']} for r in db.execute("SELECT * FROM metrics WHERE day='lifetime'")]
        chosen=[r for r in rows if (platform=='all' or r['platform']==platform) and (video=='all' or r['project']==video)]
        def total(items,key):
            values=[r.get(key) for r in items if isinstance(r.get(key),(int,float))]
            return sum(values) if values else None
        def totals(items):
            values={key:total(items,key) for key in ('views','likes','comments','shares')}
            complete=bool(items) and all(all(r.get(k) is not None for k in ('views','likes','comments','shares')) for r in items)
            values['engagement']=100*(values['likes']+values['comments']+values['shares'])/values['views'] if complete and values['views'] else None
            return values
        grouped={}
        for r in chosen:grouped.setdefault(r['project'],[]).append(r)
        result=[{'id':id,'title':items[0].get('title',id),'platforms':[r['platform'] for r in items],**totals(items)} for id,items in grouped.items()]
        videos=list({r['project']:r.get('title',r['project']) for r in rows}.items())
        return totals(chosen)|{'rows':result,'channels':[{'platform':p,'views':total([r for r in chosen if r['platform']==p],'views')} for p in PLATFORMS],
          'videos':[{'id':id,'title':title} for id,title in videos],'basis':'lifetime_snapshot','updated':max((r['updated'] for r in chosen),default=None),
          'issues':{p:self.db.get('analytics-issue:'+p,'') for p in PLATFORMS}}
