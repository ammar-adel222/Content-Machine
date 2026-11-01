"""One detached worker drains durable jobs; OS locks and saved receipts survive UI restarts."""
import argparse,json,os,time
from dataclasses import replace
from pathlib import Path
from threading import Event,Thread
from war_workflow.graph import Runner
from war_workflow.store import Conflict,WorkflowError
from war_research.providers import load_env
from .service import Studio
from .platforms import Platforms,PlatformError
from .contracts import PUBLISH_POLICY


def adapters():
    from war_workflow.media import adapters as media
    from war_workflow.authoring import adapters as authoring
    from war_workflow.speech import adapters as speech
    from war_workflow.production import adapters as production
    from war_workflow.audio import adapters as audio
    return media()|authoring()|speech()|production()|audio()


def generate(studio,job,factory=adapters):
    db=studio.db;registry=factory()
    for stage,adapter in list(registry.items()):
        def run(ctx,fn=adapter.run,stage=stage):
            if db.job(job['id'])['cancel']:raise WorkflowError('Stopped at the next stage boundary by the user.')
            db.update(job['id'],stage=stage)
            return fn(ctx)
        registry[stage]=replace(adapter,run=run)
    revision=Runner(studio.store(job['project']),registry).run(job['revision'])
    cancelled=db.job(job['id'])['cancel']
    db.update(job['id'],status='cancelled' if cancelled else 'completed' if revision.status in ('awaiting_review','approved') else revision.status,
              issue='Stopped at a stage boundary.' if cancelled else '\n'.join(revision.issues))


def publish(studio,job,platforms):
    db=studio.db;ticket=db.get('ticket:'+job['payload']['ticket']);id=job['project'];revision=job['revision']
    if ticket.get('policy')!=PUBLISH_POLICY:raise Conflict('Publishing method changed; review this post again.')
    store=studio.store(id)
    if store.load().id!=revision or studio.video(id,revision)[1]!=ticket['sha256'] or studio.metadata(id,store.load())!=ticket['metadata']:raise Conflict('Video or metadata changed since publishing confirmation.')
    Runner(store,{}).approve(revision)
    video,_=studio.video(id,revision)
    failures=[]
    for platform,account in ticket['accounts'].items():
        db.update(job['id'],stage=platform)
        old=db.publication(id,revision,platform)
        if old and old['status']!='failed':continue
        remote={}
        def checkpoint(status,values):
            remote.update(values);db.record(id,revision,platform,status,remote)
        # Confirm account identity again so a token change cannot silently retarget the post.
        try:
            profile=platforms.profile(platform)
            if profile['id']!=account['id']:raise ValueError('Platform account changed; review publishing again.')
            if profile.get('delivery_mode')!=account.get('delivery_mode') or profile.get('upload_method')!=account.get('upload_method'):raise ValueError('Platform upload method changed; review publishing again.')
            platforms.validate(platform,ticket['metadata']['posts'][platform],ticket['metadata'],profile,studio.summary(id)['seconds'] or 0)
            checkpoint('starting',{'account':account['id'],'post':ticket['metadata']['posts'][platform],'options':{k:v for k,v in ticket['metadata'].items() if k not in ('posts','selected')},'video_sha256':ticket['sha256']})
            result=platforms.publish(platform,video,ticket['metadata']['posts'][platform],ticket['metadata'],checkpoint)
            for _ in range(20):
                if result['status']!='processing':break
                time.sleep(3)
                result=platforms.poll(platform,result,checkpoint)
            checkpoint(result['status'],result)
        except (PlatformError,ValueError) as error:
            current=db.publication(id,revision,platform)
            if current and current['status']=='published':continue  # e.g. permalink lookup failed after confirmed publication.
            status='processing' if current and current['status']=='processing' and isinstance(error,PlatformError) and not error.uncertain else 'uncertain' if isinstance(error,PlatformError) and error.uncertain else 'failed'
            checkpoint(status,{'issue':str(error)});failures.append(platform+': '+str(error))
    db.update(job['id'],status='completed' if not failures else 'partial',issue='\n'.join(failures))


def sync(studio,platforms,selected=None):
    db=studio.db
    for p in selected or ('youtube','instagram','tiktok'):
        if not platforms.configured(p):continue
        try:
            with db.connect() as connection:pending=[dict(r) for r in connection.execute("SELECT * FROM publications WHERE platform=? AND status IN ('processing','awaiting_mobile')",(p,))]
            for row in pending:
                payload=json.loads(row['payload'])
                def checkpoint(status,values):
                    payload.update(values);db.record(row['project'],row['revision'],p,status,payload)
                try:
                    result=platforms.poll(p,payload,checkpoint);checkpoint(result['status'],result)
                except PlatformError as error:
                    if error.uncertain:checkpoint('uncertain',{'issue':str(error)})
            videos=platforms.videos(p)
            with db.connect() as connection:
                links={json.loads(r['payload']).get('id'):(r['project'],r['revision']) for r in connection.execute("SELECT * FROM publications WHERE platform=? AND status='published'",(p,))}
                for video in videos:
                    project,revision=links.get(video['id'],('external_'+p+'_'+video['id'],'external'))
                    connection.execute('INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?)',(project,revision,p,'lifetime',json.dumps(video),time.time()))
            db.put('analytics-issue:'+p,'')
        except (PlatformError,ValueError,KeyError) as error:db.put('analytics-issue:'+p,str(error) if isinstance(error,PlatformError) else 'Sync failed. Verify account permissions and connection status; previous snapshots are retained.')


def execute(studio,job,platforms):
    if job['kind']=='generate':return generate(studio,job)
    if job['kind']=='publish':return publish(studio,job,platforms)
    if job['kind']=='sync':sync(studio,platforms)
    elif job['kind']=='verify':
        for p in job['payload']['platforms']:
            try:platforms.profile(p)
            except (PlatformError,ValueError,KeyError) as error:
                studio.db.put('connection:'+p,{'status':'error','issue':str(error) if isinstance(error,PlatformError) else 'Invalid account response.','checked':time.time()})
    else:raise ValueError('Unknown worker job.')
    studio.db.update(job['id'],status='completed')


def drain(studio,platforms,executor=execute):
    db=studio.db
    try:
        with db.worker_lock():
            db.recover();stop=Event()
            def beat():
                while not stop.is_set():db.put('worker',{'active':True,'pid':os.getpid(),'time':time.time()});stop.wait(5)
            heartbeat=Thread(target=beat,daemon=True);heartbeat.start()
            try:
                while jobs:=db.queued():
                    job=db.job(jobs[0])
                    if job['cancel']:db.update(job['id'],status='cancelled');continue
                    db.update(job['id'],status='running')
                    try:executor(studio,job,platforms)
                    except Exception as error:
                        # Provider bodies and credentials never enter public errors or logs.
                        issue=str(error) if isinstance(error,(Conflict,WorkflowError)) else 'Job failed ('+type(error).__name__+'). Completed receipts are retained.'
                        db.update(job['id'],status='failed',issue=issue)
            finally:stop.set();heartbeat.join();db.put('worker',{'active':False,'time':time.time()})
    except Conflict:return


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--projects',type=Path,required=True);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    if args.env_file and args.env_file.is_file():load_env(args.env_file)
    studio=Studio(args.projects,args.root);platforms=Platforms(studio.db)
    try:drain(studio,platforms)
    finally:platforms.close()


if __name__=='__main__':main()
