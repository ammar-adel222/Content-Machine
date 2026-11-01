"""Loopback FastAPI application. Browser-visible data never contains provider secrets."""
import asyncio,json,os,secrets,subprocess,sys,time
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse
from war_research.providers import load_env
from war_workflow.store import Conflict,WorkflowError
from .__main__ import WEB,ASSETS
from .contracts import NewVideo,EditVideo,Metadata,Confirm,RevisionRequest,PLATFORMS
from .platforms import Platforms,PlatformError
from .service import Studio


def create_app(projects=Path('output/projects'),root=Path('output/studio'),env_file=None,*,platforms_factory=Platforms,launch=True):
    if env_file and Path(env_file).is_file():load_env(Path(env_file))
    studio=Studio(projects,root);platforms=platforms_factory(studio.db);nonce=secrets.token_urlsafe(32)
    spawn_lock=Lock();last_spawn=[0.0]
    def kick():
        if not launch:return
        with spawn_lock:
            heartbeat=studio.db.get('worker',{})
            if heartbeat.get('active') and time.time()-heartbeat.get('time',0)<30:return
            with studio.db.connect() as db:active=db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone()
            if not active or time.time()-last_spawn[0]<3:return
            last_spawn[0]=time.time()
            command=[sys.executable,'-m','war_studio.worker','--projects',str(studio.projects),'--root',str(studio.db.root)]
            if env_file:command+=['--env-file',str(Path(env_file).resolve())]
            with (studio.db.root/'worker.log').open('ab') as log:
                subprocess.Popen(command,cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
    @asynccontextmanager
    async def lifespan(app):
        async def monitor():
            while True:
                try:await asyncio.to_thread(kick)
                except OSError:pass
                await asyncio.sleep(5)
        task=asyncio.create_task(monitor())
        try:yield
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            platforms.close()
    app=FastAPI(title='Content Machine Studio',lifespan=lifespan);app.state.studio=studio

    @app.middleware('http')
    async def local_only(request:Request,call_next):
        if request.url.hostname not in ('127.0.0.1','localhost','::1'):return JSONResponse({'detail':'Local studio host required.'},status_code=403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin');expected=str(request.base_url).rstrip('/')
            if (origin and origin!=expected) or not secrets.compare_digest(request.headers.get('x-studio-key',''),nonce):return JSONResponse({'detail':'Reload the studio before making changes.'},status_code=403)
        response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request,error):return JSONResponse({'detail':'Invalid request fields. Check the selected options and text lengths.'},status_code=422)
    @app.exception_handler(Conflict)
    async def conflict(request,error):return JSONResponse({'detail':str(error)},status_code=409)
    @app.exception_handler(WorkflowError)
    async def workflow_error(request,error):return JSONResponse({'detail':str(error)},status_code=400)
    @app.exception_handler(ValueError)
    async def value_error(request,error):return JSONResponse({'detail':str(error)},status_code=400)
    @app.exception_handler(PlatformError)
    async def platform_error(request,error):return JSONResponse({'detail':str(error)},status_code=502)

    @app.get('/api/config')
    def config():return {'mode':'live','key':nonce,'platforms':list(PLATFORMS),'target_seconds':105}
    @app.get('/api/projects')
    def projects_list():return {'projects':studio.summaries()}
    @app.post('/api/projects',status_code=202)
    def create(request:NewVideo):
        project=studio.create(request);kick();return project
    @app.get('/api/projects/{id}')
    def project(id:str):return studio.summary(id)
    @app.post('/api/projects/{id}/edits',status_code=202)
    def edit(id:str,request:EditVideo):
        project=studio.edit(id,request);kick();return project
    @app.post('/api/projects/{id}/resume',status_code=202)
    def resume(id:str,request:RevisionRequest):
        job=studio.resume(id,request.revision);kick();return {'id':job['id']}
    @app.post('/api/projects/{id}/cancel')
    def cancel(id:str):
        studio.store(id);job=studio.db.latest(id)
        if not job or job['kind']!='generate' or job['status'] not in ('queued','running'):raise Conflict('Only active generation jobs can be stopped here.')
        studio.db.update(job['id'],cancel=1,status='cancelled' if job['status']=='queued' else 'running');return {'status':'stop_requested'}
    @app.put('/api/projects/{id}/metadata')
    def metadata(id:str,request:Metadata):studio.save_metadata(id,request);return {'status':'saved'}
    @app.get('/api/projects/{id}/video')
    def video(id:str,revision:str|None=None):
        path,sha=studio.video(id,revision);return FileResponse(path,media_type='video/mp4',headers={'ETag':'"'+sha+'"'})
    @app.post('/api/projects/{id}/prepare')
    def prepare(id:str):return studio.prepare(id,platforms)
    @app.post('/api/projects/{id}/publish',status_code=202)
    def publish(id:str,request:Confirm):
        job=studio.confirm(id,request.ticket);kick();return {'id':job['id'],'status':job['status']}
    @app.get('/api/connections')
    def connections():return {p:{'configured':platforms.configured(p),**studio.db.get('connection:'+p,{'status':'unchecked'})} for p in PLATFORMS}
    @app.post('/api/connections/verify',status_code=202)
    def verify():
        job=studio.db.enqueue('__connections__','', 'verify',{'platforms':list(PLATFORMS)});kick();return {'id':job['id']}
    @app.post('/api/analytics/sync',status_code=202)
    def sync():
        job=studio.db.enqueue('__analytics__','','sync');kick();return {'id':job['id']}
    @app.get('/api/analytics')
    def analytics(platform:str='all',video:str='all'):return studio.analytics(platform,video)
    @app.get('/api/jobs/{id}')
    def job(id:str):
        item=studio.db.job(id);return {k:item[k] for k in ('id','kind','status','stage','issue','cancel')}
    @app.get('/{asset:path}')
    def static(asset:str):
        route='/'+asset
        if route not in ASSETS:return JSONResponse({'detail':'Not found.'},status_code=404)
        return FileResponse(WEB/ASSETS[route],media_type='text/javascript' if asset.endswith('.mjs') else None)
    return app
