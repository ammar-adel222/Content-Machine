import importlib.util,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
HAS_HTTPX=bool(importlib.util.find_spec('httpx'))
if HAS_HTTPX:
    import httpx
    from war_studio.platforms import Platforms,PlatformError,caption
    from war_studio.database import Database


@unittest.skipUnless(HAS_HTTPX,'Install studio dependencies')
class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.db=Database(self.root/'db');self.video=self.root/'video.mp4';self.video.write_bytes(b'0123456789')
        self.env={'YOUTUBE_CLIENT_ID':'client','YOUTUBE_CLIENT_SECRET':'secret','YOUTUBE_REFRESH_TOKEN':'refresh',
          'INSTAGRAM_ACCESS_TOKEN':'ig-access','INSTAGRAM_BUSINESS_ACCOUNT_ID':'account','TIKTOK_ACCESS_TOKEN':'tt-access',
          'TIKTOK_CLIENT_KEY':'tt-client','TIKTOK_CLIENT_SECRET':'tt-secret','TIKTOK_REFRESH_TOKEN':'tt-refresh','TIKTOK_PUBLISH_MODE':'direct'}
        self.post={'title':'A historical story','description':'The terrain mattered.','hashtags':'#History'}
        self.options={'youtube_privacy':'private','tiktok_privacy':'SELF_ONLY','disable_comment':True,'disable_duet':True,'disable_stitch':True}

    def platform(self,transport):
        client=httpx.Client(transport=httpx.MockTransport(transport));self.addCleanup(client.close)
        return Platforms(self.db,self.env,client)

    def test_profiles_refresh_tokens_and_sandbox_privacy_are_persisted(self):
        calls=[]
        def handle(req):
            calls.append(str(req.url))
            if req.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':'secret-access','expires_in':3600})
            if req.url.path.endswith('channels'):return httpx.Response(200,json={'items':[{'id':'yt','snippet':{'title':'Test channel'},'contentDetails':{'relatedPlaylists':{'uploads':'playlist'}}}]})
            if 'creator_info' in req.url.path:return httpx.Response(200,json={'data':{'creator_username':'tt','creator_nickname':'Test creator','privacy_level_options':['PUBLIC_TO_EVERYONE','SELF_ONLY'],'max_video_post_duration_sec':180}})
            return httpx.Response(200,json={'id':'ig','username':'Test IG'})
        p=self.platform(handle)
        for platform in ('youtube','instagram','tiktok'):self.assertTrue(p.configured(platform));self.assertTrue(p.profile(platform)['id'])
        self.assertEqual(p.profile('tiktok')['privacy'],['SELF_ONLY'])
        p.profile('youtube');self.assertEqual(sum('oauth2' in url for url in calls),1)
        self.assertNotIn('secret-access',json.dumps(self.db.get('connection:youtube')))
        self.env['TIKTOK_APP_MODE']='production';self.assertIn('PUBLIC_TO_EVERYONE',p.profile('tiktok')['privacy'])

    def test_http_errors_timeouts_redirects_and_malformed_json_are_redacted(self):
        p=self.platform(lambda req:httpx.Response(401,json={'error':{'code':'scope_not_authorized','message':'secret-api-key'}}))
        with self.assertRaises(PlatformError) as result:p.call('GET','https://example.test')
        self.assertIn('scope_not_authorized',str(result.exception));self.assertNotIn('secret-api-key',str(result.exception))
        def disconnect(req):raise httpx.ConnectError('secret-url')
        p=self.platform(disconnect)
        with self.assertRaises(PlatformError) as result:p.call('POST','https://example.test',mutation=True)
        self.assertTrue(result.exception.uncertain);self.assertNotIn('secret-url',str(result.exception))
        for response in (httpx.Response(302),httpx.Response(200,text='invalid JSON'),httpx.Response(200,json=[])):
            p=self.platform(lambda req,r=response:r)
            with self.assertRaises(PlatformError):p.call('GET','https://example.test')

    def test_youtube_resumable_upload_preserves_reviewed_metadata(self):
        requests=[];checkpoints=[]
        def handle(req):
            requests.append(req)
            if req.url.host=='oauth2.googleapis.com':return httpx.Response(200,json={'access_token':'access'})
            if req.method=='POST':return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/session'})
            return httpx.Response(200,json={'id':'video-id'})
        result=self.platform(handle).publish('youtube',self.video,self.post,self.options,lambda s,v:checkpoints.append((s,v)))
        self.assertEqual(result['status'],'published');self.assertEqual(checkpoints[0][0],'uploading')
        body=json.loads(requests[1].content);self.assertEqual(body['snippet']['title'],self.post['title']);self.assertEqual(body['status']['privacyStatus'],'private')
        self.assertNotIn('containsSyntheticMedia',body['status']);self.assertEqual(requests[-1].content,b'0123456789')
        for url in ('http://www.googleapis.com/upload','https://attacker.test/upload','https://googleapis.com.attacker.test/upload','https://user@www.googleapis.com/upload'):
            with self.assertRaises(PlatformError):Platforms.upload_url(url,['googleapis.com'])

    def test_instagram_direct_binary_upload_records_before_submitting(self):
        phases=[];requests=[]
        def handle(req):
            requests.append(req)
            if req.url.path.endswith('/media'):return httpx.Response(200,json={'id':'container','uri':'https://rupload.facebook.com/upload'})
            if req.url.host=='rupload.facebook.com':return httpx.Response(200,text='uploaded')
            if req.url.path.endswith('/media_publish'):
                self.assertIn('submitting',phases);return httpx.Response(200,json={'id':'published-id'})
            if req.url.path.endswith('/container'):return httpx.Response(200,json={'status_code':'FINISHED'})
            return httpx.Response(200,json={'permalink':'https://www.instagram.com/reel/test/'})
        result=self.platform(handle).publish('instagram',self.video,self.post,self.options,lambda s,v:phases.append(s))
        self.assertEqual(result['status'],'published');self.assertEqual(phases,['uploading','processing','submitting','published'])
        self.assertTrue(all(r.url.host in ('graph.facebook.com','rupload.facebook.com') for r in requests))
        self.assertEqual(requests[1].headers['offset'],'0');self.assertEqual(requests[1].content,b'0123456789')

    def test_instagram_processing_and_definitive_container_failure_are_not_published(self):
        for status,expected in [('IN_PROGRESS','processing'),('ERROR','failed'),('EXPIRED','failed')]:
            p=self.platform(lambda req:httpx.Response(200,json={'status_code':status}))
            self.assertEqual(p.poll('instagram',{'container':'test'},lambda *args:self.fail('Must not publish'))['status'],expected)

    def test_tiktok_single_chunk_and_processing_receipt(self):
        requests=[];checkpoints=[]
        def handle(req):
            requests.append(req)
            if req.url.path.endswith('/init/'):return httpx.Response(200,json={'data':{'publish_id':'publish-id','upload_url':'https://open-upload.tiktokapis.com/upload'}})
            if req.method=='PUT':return httpx.Response(201,text='uploaded')
            return httpx.Response(200,json={'data':{'status':'PROCESSING_UPLOAD'},'error':{'code':'ok'}})
        p=self.platform(handle);result=p.publish('tiktok',self.video,self.post,self.options,lambda s,v:checkpoints.append((s,v)))
        self.assertEqual(result['status'],'processing');self.assertEqual(result['publish_id'],'publish-id')
        self.assertEqual(requests[1].headers['Content-Range'],'bytes 0-9/10')
        self.assertNotIn('is_aigc',json.loads(requests[0].content)['post_info'])
        p=self.platform(lambda req:httpx.Response(200,json={'data':{'status':'PUBLISH_COMPLETE','publicaly_available_post_id':['id']}}))
        self.assertEqual(p.poll('tiktok',{'publish_id':'test'},lambda *args:None)['id'],'id')
        p=self.platform(lambda req:httpx.Response(200,json={'data':{'status':'FAILED'}}))
        self.assertEqual(p.poll('tiktok',{'publish_id':'test'},lambda *args:None)['status'],'failed')

    def test_tiktok_expired_token_refresh_persists_rotated_refresh_token(self):
        attempts=[]
        def handle(req):
            attempts.append(req)
            if req.url.path.endswith('/oauth/token/'):return httpx.Response(200,json={'access_token':'new-access','refresh_token':'rotated-refresh','expires_in':1000})
            if len(attempts)==1:return httpx.Response(401,json={'error':{'code':'access_token_invalid'}})
            return httpx.Response(200,json={'data':{'ok':True}})
        p=self.platform(handle);self.assertTrue(p.tk('test/',{})['data']['ok'])
        self.assertEqual(self.db.get('token:tiktok')['refresh_token'],'rotated-refresh')
        self.assertEqual(attempts[-1].headers['authorization'],'Bearer new-access')

    def test_platform_specific_validation_blocks_invalid_posts_before_upload(self):
        p=self.platform(lambda req:self.fail('No network expected'))
        creator={'privacy':['SELF_ONLY'],'max_duration':120,'comment_disabled':True}
        p.validate('youtube',self.post,self.options,{},105);p.validate('instagram',self.post,self.options,{},105);p.validate('tiktok',self.post,self.options,creator,105)
        cases=[('youtube',self.post|{'title':'x'*101},self.options,{},105),('youtube',self.post|{'title':'<title>'},self.options,{},105),
          ('instagram',self.post|{'description':'x'*2201},self.options,{},105),('instagram',self.post|{'hashtags':' '.join('#tag' for i in range(31))},self.options,{},105),
          ('tiktok',self.post,self.options|{'tiktok_privacy':'PUBLIC_TO_EVERYONE'},creator,105),('tiktok',self.post,self.options,creator,150),
          ('tiktok',self.post,self.options|{'disable_comment':False},creator,105),('tiktok',self.post|{'description':'😀'*1200},self.options,creator,105)]
        for args in cases:
            with self.assertRaises(ValueError):p.validate(*args)

    def test_analytics_missing_insights_are_null_instead_of_zero(self):
        def handle(req):
            if req.url.path.endswith('/account'):return httpx.Response(200,json={'id':'account','username':'IG'})
            if req.url.path.endswith('/media'):return httpx.Response(200,json={'data':[{'id':'post','caption':'Story','like_count':4,'comments_count':2}]})
            return httpx.Response(403,json={'error':{'code':10}})
        rows=self.platform(handle).videos('instagram');self.assertIsNone(rows[0]['views']);self.assertIsNone(rows[0]['shares']);self.assertEqual(rows[0]['likes'],4)

    def test_instagram_login_stages_on_existing_host_then_uses_video_url(self):
        self.env['INSTAGRAM_ACCESS_TOKEN']='IG-current-token';requests=[];phases=[]
        def handle(req):
            requests.append(req)
            if req.url.host=='uguu.se':return httpx.Response(200,json={'files':[{'url':'https://d.uguu.se/temporary.mp4'}]})
            if req.url.path.endswith('/media'):
                self.assertIn(b'video_url=',req.content);self.assertNotIn(b'upload_type=',req.content)
                return httpx.Response(200,json={'id':'container'})
            if req.url.path.endswith('/container'):return httpx.Response(200,json={'status_code':'FINISHED'})
            if req.url.path.endswith('/me/media_publish'):return httpx.Response(200,json={'id':'published'})
            return httpx.Response(200,json={'permalink':'https://www.instagram.com/reel/test/'})
        result=self.platform(handle).publish('instagram',self.video,self.post,self.options,lambda s,v:phases.append(s))
        self.assertEqual(result['status'],'published');self.assertEqual(phases[0],'staging')
        self.assertNotIn('authorization',requests[0].headers)
        self.assertTrue(all(r.url.host in ('uguu.se','graph.instagram.com') for r in requests))

    def test_staging_failure_cannot_create_or_publish_instagram_media(self):
        self.env['INSTAGRAM_ACCESS_TOKEN']='IG-current-token';requests=[]
        def handle(req):requests.append(req);return httpx.Response(200,json={'files':[]})
        with self.assertRaises(PlatformError):self.platform(handle).publish('instagram',self.video,self.post,self.options,lambda *args:None)
        self.assertEqual([r.url.host for r in requests],['uguu.se'])

    def test_tiktok_defaults_to_inbox_and_requires_mobile_review(self):
        self.env.pop('TIKTOK_PUBLISH_MODE');requests=[]
        def handle(req):
            requests.append(req)
            if req.url.path.endswith('/inbox/video/init/'):
                self.assertEqual(set(json.loads(req.content)),{'source_info'})
                return httpx.Response(200,json={'data':{'publish_id':'inbox-id','upload_url':'https://open-upload.tiktokapis.com/upload'}})
            if req.method=='PUT':return httpx.Response(201)
            return httpx.Response(200,json={'data':{'status':'SEND_TO_USER_INBOX'}})
        p=self.platform(handle);p.validate('tiktok',self.post,self.options|{'tiktok_privacy':''},{},105)
        result=p.publish('tiktok',self.video,self.post,self.options,lambda *args:None)
        self.assertEqual(result['status'],'awaiting_mobile');self.assertEqual(result['delivery_mode'],'inbox')
        self.assertFalse(any(r.url.path=='/v2/post/publish/video/init/' for r in requests))
        self.assertIn('mobile app',result['issue'])
