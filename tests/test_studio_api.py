"""Offline integration checks: real project DB/graph, injected platform calls."""
import importlib.util,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from war_workflow.models import Output
from war_workflow.planner import ORDER
from war_workflow.graph import Runner,Adapter
from war_workflow.store import Conflict,WorkflowError
from war_studio.contracts import NewVideo,EditVideo,Metadata
from war_studio.service import Studio

HAS_STUDIO=bool(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'))
if HAS_STUDIO:
    from fastapi.testclient import TestClient
    from war_studio.api import create_app
    from war_studio.platforms import Platforms,PlatformError
    from war_studio.worker import drain,generate,publish,sync

    class FakePlatforms(Platforms):
        def __init__(self,db):self.db=db;self.env={};self.calls=[];self.fail=None
        def configured(self,p):return True
        def close(self):pass
        def profile(self,p):
            result={'id':p+'-account','name':p+' test','privacy':['SELF_ONLY'],'max_duration':300,'comment_disabled':False,'duet_disabled':False,'stitch_disabled':False,'mode':'sandbox'}
            self.db.put('connection:'+p,result|{'status':'verified'});return result
        def publish(self,p,video,post,options,checkpoint):
            self.calls.append(p);checkpoint('uploading',{'container':'remote'})
            if self.fail==p:raise PlatformError('Ambiguous upload.',uncertain=True)
            return {'status':'published','id':p+'-video','url':'https://www.youtube.com/watch?v=test'}
        def videos(self,p):return [{'id':p+'-video','title':'External story','views':100,'likes':5,'comments':1,'shares':None if p=='youtube' else 2}]


@unittest.skipUnless(HAS_STUDIO,'Install the studio extra')
class StudioAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.studio=Studio(root/'projects',root/'studio')
        item=self.studio.create(NewVideo(topic='Offline battle'));self.id=item['id'];self.store=self.studio.store(self.id)
        self.studio.db.update(self.studio.db.latest(self.id)['id'],status='completed')
        def run(ctx):
            data={};files={}
            if ctx.stage=='writing':data={'topic':'Offline battle','scope':'battle','draft':{'title':'A tested battle story','caption':'An offline story.'}}
            if ctx.stage=='mux':
                path=ctx.output_dir/'video.mp4';path.write_bytes(b'0123456789');files={'video':str(path)};data={'duration':100}
            return Output(data=data,files=files,review='pass' if ctx.stage.endswith('review') else None)
        self.registry={s:Adapter(run,'studio-test') for s in ORDER}
        self.revision=Runner(self.store,self.registry).run();self.platforms=FakePlatforms(self.studio.db)
        self.client=TestClient(create_app(self.studio.projects,self.studio.db.root,platforms_factory=FakePlatforms,launch=False),base_url='http://127.0.0.1')
        self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.headers={'X-Studio-Key':self.client.get('/api/config').json()['key']}

    def request(self,method,path,**kwargs):return self.client.request(method,path,headers=self.headers,**kwargs)

    def metadata(self,selected=None):
        data=self.studio.metadata(self.id,self.store.load());data['selected']=selected or ['youtube','instagram'];data['tiktok_privacy']='SELF_ONLY';return data

    def test_project_listing_video_ranges_and_local_request_protection(self):
        item=self.client.get('/api/projects').json()['projects'][0]
        self.assertEqual(item['revision_id'],self.revision.id);self.assertEqual(item['workflow_status'],'awaiting_review')
        response=self.client.get(item['video_url'],headers={'Range':'bytes=2-4'})
        self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'234')
        self.assertEqual(self.client.post('/api/projects',json={'topic':'x'}).status_code,403)
        response=self.client.post('/api/projects',headers=self.headers|{'Origin':'https://other.example'},json={'topic':'x'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.get('/api/config',headers={'Host':'other.example'}).status_code,403)
        self.assertEqual(self.client.get('/.env').status_code,404)
        self.assertEqual(self.request('POST','/api/projects',json={'topic':'x','secret':'never echo'}).status_code,422)

    def test_real_create_empty_topic_saved_settings_and_queued_cancel(self):
        response=self.request('POST','/api/projects',json={'topic':'','kind':'war','format':'landscape','terrain':'schematic'})
        self.assertEqual(response.status_code,202);id=response.json()['id'];store=self.studio.store(id)
        self.assertEqual(store.load().params['research']['mode'],'auto');self.assertEqual(store.load().params['terrain']['mode'],'schematic')
        self.assertEqual(self.request('POST',f'/api/projects/{id}/cancel').status_code,200)
        self.assertEqual(self.studio.db.latest(id)['status'],'cancelled')

    def test_scoped_edit_reuses_contracts_and_rejects_stale_or_external_settings(self):
        body={'revision':self.revision.id,'kind':'music_mix','notes':'Quieter music','patch':{'music_gain_db':-30},'request_id':'edit-1'}
        result=self.request('POST',f'/api/projects/{self.id}/edits',json=body)
        self.assertEqual(result.status_code,202);self.assertEqual(self.store.load().artifacts['writing'],self.revision.artifacts['writing'])
        self.assertNotIn('picture',self.store.load().dirty)
        self.assertEqual(self.store.load().instructions['mix']['notes'],'')
        self.assertEqual(self.studio.summary(self.id)['edits'][-1]['text'],'Quieter music')
        from war_workflow.audio import mix_settings
        self.assertEqual(mix_settings(Runner(self.store,self.registry).context(self.store.load(),'mix')).music_gain_db,-30)
        self.assertEqual(self.request('POST',f'/api/projects/{self.id}/edits',json=body|{'request_id':'edit-2'}).status_code,409)
        job=self.studio.db.latest(self.id);self.studio.db.update(job['id'],status='completed')
        body|={'revision':self.store.load().id,'kind':'terrain','request_id':'edit-3','patch':{'source_bundle':str(Path(self.tmp.name).parent)}}
        self.assertEqual(self.request('POST',f'/api/projects/{self.id}/edits',json=body).status_code,400)

    def test_metadata_persists_and_stale_writes_are_rejected(self):
        data=self.metadata();data['posts']['youtube']['title']='Updated title'
        self.assertEqual(self.request('PUT',f'/api/projects/{self.id}/metadata',json=data).status_code,200)
        self.assertEqual(Studio(self.studio.projects,self.studio.db.root).summary(self.id)['metadata']['youtube']['title'],'Updated title')
        data['revision']='stale';self.assertEqual(self.request('PUT',f'/api/projects/{self.id}/metadata',json=data).status_code,409)

    def test_publish_confirmation_binds_video_metadata_and_is_idempotent(self):
        data=self.metadata();self.studio.save_metadata(self.id,Metadata(**data))
        ticket=self.request('POST',f'/api/projects/{self.id}/prepare').json()
        self.assertIsNone(self.store.load().approval);self.assertEqual(self.platforms.calls,[])
        self.assertEqual(self.request('POST',f'/api/projects/{self.id}/publish',json={'ticket':ticket['ticket'],'consent':False}).status_code,422)
        body={'ticket':ticket['ticket'],'consent':True}
        one=self.request('POST',f'/api/projects/{self.id}/publish',json=body);two=self.request('POST',f'/api/projects/{self.id}/publish',json=body)
        self.assertEqual(one.status_code,202);self.assertEqual(one.json()['id'],two.json()['id'])
        self.assertIsNone(self.store.load().approval)
        publish(self.studio,self.studio.db.job(one.json()['id']),self.platforms)
        self.assertEqual(self.store.load().status,'approved');self.assertEqual(self.platforms.calls,['youtube','instagram'])
        self.assertEqual(self.studio.db.publication(self.id,self.revision.id,'youtube')['status'],'published')
        self.assertEqual(self.request('POST',f'/api/projects/{self.id}/prepare').status_code,409)

    def test_expired_or_changed_publishing_review_cannot_send_media(self):
        self.studio.save_metadata(self.id,Metadata(**self.metadata()))
        ticket=self.studio.prepare(self.id,self.platforms);data=self.metadata();data['posts']['youtube']['title']='Changed after review'
        self.studio.save_metadata(self.id,Metadata(**data))
        with self.assertRaises(Conflict):self.studio.confirm(self.id,ticket['ticket'])
        self.assertEqual(self.platforms.calls,[])
        ticket=self.studio.prepare(self.id,self.platforms);stored=self.studio.db.get('ticket:'+ticket['ticket']);stored['created']=0;self.studio.db.put('ticket:'+ticket['ticket'],stored)
        with self.assertRaises(Conflict):self.studio.confirm(self.id,ticket['ticket'])
        path,_=self.studio.video(self.id);path.write_bytes(b'modified')
        with self.assertRaises(WorkflowError):self.studio.prepare(self.id,self.platforms)

    def test_partial_platform_failure_never_duplicates_completed_uploads(self):
        self.studio.save_metadata(self.id,Metadata(**self.metadata()))
        ticket=self.studio.prepare(self.id,self.platforms);job=self.studio.confirm(self.id,ticket['ticket']);self.platforms.fail='instagram'
        publish(self.studio,job,self.platforms)
        self.assertEqual(self.studio.db.job(job['id'])['status'],'partial')
        self.assertEqual(self.studio.db.publication(self.id,self.revision.id,'instagram')['status'],'uncertain')
        with self.assertRaises(Conflict):self.studio.prepare(self.id,self.platforms)
        self.assertEqual(self.platforms.calls.count('youtube'),1)

    def test_changed_upload_policy_requires_a_fresh_publishing_review(self):
        self.studio.save_metadata(self.id,Metadata(**self.metadata()))
        ticket=self.studio.prepare(self.id,self.platforms);payload=self.studio.db.get('ticket:'+ticket['ticket']);payload.pop('policy');self.studio.db.put('ticket:'+ticket['ticket'],payload)
        with self.assertRaisesRegex(Conflict,'method changed'):self.studio.confirm(self.id,ticket['ticket'])
        self.assertEqual(self.platforms.calls,[])

    def test_tiktok_inbox_receipt_requires_mobile_review_and_prevents_duplicate_uploads(self):
        self.studio.save_metadata(self.id,Metadata(**self.metadata(['tiktok'])))
        ticket=self.studio.prepare(self.id,self.platforms);job=self.studio.confirm(self.id,ticket['ticket'])
        def inbox(p,video,post,options,checkpoint):
            checkpoint('processing',{'publish_id':'inbox-id','delivery_mode':'inbox'})
            return {'status':'awaiting_mobile','publish_id':'inbox-id','issue':'Review in the mobile app.'}
        self.platforms.publish=inbox;publish(self.studio,job,self.platforms)
        receipt=self.studio.db.publication(self.id,self.revision.id,'tiktok')
        self.assertEqual(receipt['status'],'awaiting_mobile')
        with self.assertRaises(Conflict):self.studio.prepare(self.id,self.platforms)

    def test_status_poll_failure_does_not_mark_an_uploaded_video_safe_to_reupload(self):
        self.studio.save_metadata(self.id,Metadata(**self.metadata(['tiktok'])))
        ticket=self.studio.prepare(self.id,self.platforms);job=self.studio.confirm(self.id,ticket['ticket'])
        def pending(p,video,post,options,checkpoint):
            checkpoint('processing',{'publish_id':'inbox-id'})
            return {'status':'processing','publish_id':'inbox-id'}
        def interrupted(*args):raise PlatformError('Read interrupted.')
        self.platforms.publish=pending;self.platforms.poll=interrupted
        with patch('war_studio.worker.time.sleep'):publish(self.studio,job,self.platforms)
        self.assertEqual(self.studio.db.publication(self.id,self.revision.id,'tiktok')['status'],'processing')
        with self.assertRaises(Conflict):self.studio.prepare(self.id,self.platforms)

    def test_analytics_uses_real_snapshots_preserves_missing_values_and_filters(self):
        sync(self.studio,self.platforms)
        data=self.client.get('/api/analytics').json();self.assertEqual(data['basis'],'lifetime_snapshot');self.assertEqual(data['views'],300)
        self.assertIsNone(data['engagement']);self.assertEqual(len(data['rows']),3)
        yt=self.client.get('/api/analytics?platform=youtube').json();self.assertEqual(yt['views'],100);self.assertIsNone(yt['shares'])
        id=yt['rows'][0]['id'];self.assertEqual(len(self.client.get('/api/analytics',params={'video':id}).json()['rows']),1)
        self.assertEqual(self.client.get('/api/analytics?platform=unknown').status_code,400)

    def test_job_recovery_exclusive_queue_and_exception_redaction(self):
        job=self.studio.db.enqueue('worker-test','','verify')
        with self.assertRaises(Conflict):self.studio.db.enqueue('worker-test','','verify')
        self.studio.db.update(job['id'],status='running');self.studio.db.record(self.id,self.revision.id,'youtube','uploading',{'session':'private-upload-url'})
        self.studio.db.recover();self.assertEqual(self.studio.db.job(job['id'])['status'],'interrupted')
        self.assertEqual(self.studio.db.publication(self.id,self.revision.id,'youtube')['status'],'uncertain')
        another=self.studio.db.enqueue('worker-next','','verify')
        def bad(*args):raise KeyError('secret-provider-body')
        drain(self.studio,self.platforms,bad)
        result=self.studio.db.job(another['id']);self.assertEqual(result['status'],'failed');self.assertNotIn('secret-provider-body',result['issue'])
        response=self.client.get('/api/projects/'+self.id).text;self.assertNotIn('private-upload-url',response)

    def test_worker_calls_real_graph_and_cancels_at_stage_boundary(self):
        request=EditVideo(revision=self.revision.id,kind='music_mix',notes='Reduce music',patch={'music_gain_db':-30},request_id='worker-edit')
        self.studio.edit(self.id,request);job=self.studio.db.latest(self.id)
        generate(self.studio,job,lambda:self.registry)
        self.assertEqual(self.studio.db.job(job['id'])['status'],'completed')
        self.studio.edit(self.id,request.model_copy(update={'revision':self.store.load().id,'request_id':'cancel-edit'}));job=self.studio.db.latest(self.id)
        self.studio.db.update(job['id'],cancel=1);generate(self.studio,job,lambda:self.registry)
        self.assertEqual(self.studio.db.job(job['id'])['status'],'cancelled')
