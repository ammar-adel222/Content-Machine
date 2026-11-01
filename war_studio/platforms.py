"""Bounded official platform calls, injectable transport and durable upload checkpoints."""
from datetime import datetime,timezone
import os,re,time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .contracts import PLATFORMS


class PlatformError(RuntimeError):
    def __init__(self,message,*,uncertain=False,status=0):super().__init__(message);self.uncertain=uncertain;self.status=status


def caption(post):return '\n\n'.join(post[k].strip() for k in ('title','description','hashtags') if post.get(k,'').strip())


class Platforms:
    def __init__(self,db,env=None,client=None):
        self.db=db;self.env=os.environ if env is None else env
        self.client=client or httpx.Client(timeout=60,follow_redirects=False,headers={'User-Agent':'ContentMachineStudio/1.0'})

    def close(self):self.client.close()

    def configured(self,p):
        required={'youtube':['YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REFRESH_TOKEN'],
          'instagram':['INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_BUSINESS_ACCOUNT_ID'],'tiktok':['TIKTOK_ACCESS_TOKEN']}[p]
        return all(self.env.get(k) for k in required)

    def call(self,method,url,*,mutation=False,raw=False,**kwargs):
        try:response=self.client.request(method,url,**kwargs)
        except httpx.HTTPError:raise PlatformError('Platform request interrupted. Verify remote status before retrying.' if mutation else 'Platform request failed; check connectivity.',uncertain=mutation) from None
        if not 200<=response.status_code<300:
            code=''
            try:
                error=response.json().get('error',{});candidate=str(error.get('code','')) if isinstance(error,dict) else ''
                if re.fullmatch(r'[\w.-]{1,60}',candidate):code=' ('+candidate+')'
            except (ValueError,AttributeError):pass
            raise PlatformError(f'Platform HTTP {response.status_code}{code}. Check token, permissions and account configuration.',uncertain=mutation and (response.status_code>=500 or response.status_code<400),status=response.status_code)
        if raw:return response
        try:data=response.json()
        except ValueError:raise PlatformError('Platform returned an invalid response.',uncertain=mutation) from None
        if not isinstance(data,dict):raise PlatformError('Platform returned an invalid response.',uncertain=mutation)
        error=data.get('error')
        if error and (not isinstance(error,dict) or error.get('code') not in (None,'ok')):
            code=error.get('code','rejected') if isinstance(error,dict) else 'rejected'
            code=str(code);code=code if re.fullmatch(r'[\w.-]{1,60}',code) else 'rejected'
            raise PlatformError('Platform rejected the request ('+code+').',uncertain=mutation)
        return data

    def token(self,p,refresh=False):
        cached=self.db.get('token:'+p,{})
        if cached.get('expires',0)>time.time()+90 and not refresh:return cached['access_token']
        if p=='youtube':
            data=self.call('POST','https://oauth2.googleapis.com/token',data={'client_id':self.env['YOUTUBE_CLIENT_ID'],'client_secret':self.env['YOUTUBE_CLIENT_SECRET'],'refresh_token':self.env['YOUTUBE_REFRESH_TOKEN'],'grant_type':'refresh_token'})
        elif p=='tiktok':
            if not cached and not refresh:return self.env['TIKTOK_ACCESS_TOKEN']
            if not all(self.env.get(k) for k in ('TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','TIKTOK_REFRESH_TOKEN')):raise PlatformError('TikTok token expired; refresh credentials are incomplete.')
            data=self.call('POST','https://open.tiktokapis.com/v2/oauth/token/',data={'client_key':self.env['TIKTOK_CLIENT_KEY'],'client_secret':self.env['TIKTOK_CLIENT_SECRET'],'refresh_token':cached.get('refresh_token') or self.env['TIKTOK_REFRESH_TOKEN'],'grant_type':'refresh_token'})
        else:return self.env['INSTAGRAM_ACCESS_TOKEN']
        if not data.get('access_token'):raise PlatformError('Token refresh returned no access token.')
        self.db.put('token:'+p,{'access_token':data['access_token'],'refresh_token':data.get('refresh_token') or cached.get('refresh_token') or self.env.get(p.upper()+'_REFRESH_TOKEN',''),'expires':time.time()+int(data.get('expires_in',3600))})
        return data['access_token']

    def headers(self,p):return {'Authorization':'Bearer '+self.token(p)}

    def tk(self,path,payload,fields=None):
        url='https://open.tiktokapis.com/v2/'+path
        try:return self.call('POST',url,headers=self.headers('tiktok'),json=payload,params={'fields':fields} if fields else None)
        except PlatformError as e:
            if e.status!=401:raise
            self.token('tiktok',refresh=True);return self.call('POST',url,headers=self.headers('tiktok'),json=payload,params={'fields':fields} if fields else None)

    @property
    def igbase(self):
        version=self.env.get('META_GRAPH_VERSION','v25.0')
        if not re.fullmatch(r'v\d+\.\d+',version):raise PlatformError('Invalid Meta Graph API version.')
        host='graph.instagram.com' if self.env.get('INSTAGRAM_ACCESS_TOKEN','').startswith('IG') else 'graph.facebook.com'
        return 'https://'+host+'/'+version+'/'

    def profile(self,p):
        if not self.configured(p):raise PlatformError('Required backend credentials are missing.')
        if p=='youtube':
            data=self.call('GET','https://www.googleapis.com/youtube/v3/channels',headers=self.headers(p),params={'part':'snippet,contentDetails','mine':'true'})
            if not data.get('items'):raise PlatformError('No YouTube channel was returned.')
            item=data['items'][0];result={'id':item['id'],'name':item['snippet']['title'],'uploads':item['contentDetails']['relatedPlaylists']['uploads']}
        elif p=='instagram':
            item=self.call('GET',self.igbase+self.env['INSTAGRAM_BUSINESS_ACCOUNT_ID'],headers=self.headers(p),params={'fields':'id,username'})
            result={'id':item['id'],'name':item['username'],'upload_method':'temporary_https' if 'graph.instagram.com' in self.igbase else 'resumable'}
            if result['upload_method']=='temporary_https':result['staging_host']='uguu.se'
        else:
            item=self.tk('post/publish/creator_info/query/',{})['data']
            sandbox=self.env.get('TIKTOK_APP_MODE','sandbox')!='production'
            result={'id':item.get('creator_username',''),'name':item.get('creator_nickname',item.get('creator_username','')),
             'privacy':[v for v in item.get('privacy_level_options',[]) if not sandbox or v=='SELF_ONLY'],'mode':'sandbox' if sandbox else 'production','delivery_mode':self.env.get('TIKTOK_PUBLISH_MODE','inbox'),'max_duration':item.get('max_video_post_duration_sec',0),
             'comment_disabled':item.get('comment_disabled',True),'duet_disabled':item.get('duet_disabled',True),'stitch_disabled':item.get('stitch_disabled',True)}
        if not result.get('id'):raise PlatformError('Platform returned no account identity.')
        self.db.put('connection:'+p,result|{'checked':time.time(),'status':'verified'})
        return result

    def validate(self,p,post,options,profile,duration):
        text=caption(post)
        if p=='youtube':
            if not post['title'].strip() or len(post['title'])>100 or any(c in post['title'] for c in '<>') or len(post['description']+'\n\n'+post['hashtags'])>5000:raise ValueError('YouTube needs a title of 1–100 characters without angle brackets and a description including hashtags under 5,001 characters.')
        elif p=='instagram':
            if len(text)>2200 or len(re.findall(r'(?<!\w)#\w+',text))>30:raise ValueError('Instagram caption must fit 2,200 characters and 30 hashtags.')
        else:
            if len(text.encode('utf-16-le'))//2>2200:raise ValueError('TikTok caption must fit 2,200 UTF-16 characters.')
            if self.env.get('TIKTOK_PUBLISH_MODE','inbox')=='inbox':return
            if not options.get('tiktok_privacy') or options['tiktok_privacy'] not in profile.get('privacy',[]):raise ValueError('Choose a TikTok privacy option allowed by the current creator account.')
            if duration>profile.get('max_duration',0):raise ValueError('This video exceeds the TikTok account duration limit.')
            for key in ('comment','duet','stitch'):
                if profile.get(key+'_disabled',True) and not options.get('disable_'+key,True):raise ValueError('TikTok account does not allow '+key+'.')

    @staticmethod
    def upload_url(url,hosts):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.username or parsed.password or not parsed.hostname or not any(parsed.hostname==h or parsed.hostname.endswith('.'+h) for h in hosts):raise PlatformError('Platform returned an unexpected upload destination.',uncertain=True)
        return url

    def publish(self,p,video,post,options,checkpoint):
        video=Path(video);size=video.stat().st_size
        if p=='youtube':
            response=self.call('POST','https://www.googleapis.com/upload/youtube/v3/videos',mutation=True,raw=True,headers=self.headers(p)|{'X-Upload-Content-Length':str(size),'X-Upload-Content-Type':'video/mp4'},params={'part':'snippet,status','uploadType':'resumable'},json={'snippet':{'title':post['title'],'description':'\n\n'.join(x for x in (post['description'],post['hashtags']) if x),'categoryId':'27'},'status':{'privacyStatus':options['youtube_privacy'],'selfDeclaredMadeForKids':False}})
            url=self.upload_url(response.headers.get('location',''),['googleapis.com'])
            checkpoint('uploading',{'session':url})
            with video.open('rb') as source:data=self.call('PUT',url,mutation=True,headers={'Content-Type':'video/mp4','Content-Length':str(size)},content=source)
            if not data.get('id'):raise PlatformError('YouTube returned no video ID.',uncertain=True)
            return {'status':'published','id':data['id'],'url':'https://www.youtube.com/watch?v='+data['id']}
        if p=='instagram':
            payload={'media_type':'REELS','caption':caption(post),'share_to_feed':'true'}
            if 'graph.instagram.com' in self.igbase:
                if size>128*1024*1024:raise ValueError('Instagram temporary hosting supports files up to 128 MiB.')
                checkpoint('staging',{'staging_provider':'uguu.se'})
                # Same primary temporary host as edition one; no credentials or silent host fallbacks.
                with video.open('rb') as source:staged=self.call('POST','https://uguu.se/upload',files={'files[]':(video.name,source,'video/mp4')},timeout=180)
                files=staged.get('files',[])
                if not files or not isinstance(files[0],dict):raise PlatformError('Temporary video hosting returned no file URL.')
                payload['video_url']=self.upload_url(files[0].get('url',''),['uguu.se'])
            else:payload['upload_type']='resumable'
            data=self.call('POST',self.igbase+self.env['INSTAGRAM_BUSINESS_ACCOUNT_ID']+'/media',mutation=True,headers=self.headers(p),data=payload)
            if not data.get('id'):raise PlatformError('Instagram returned no container ID.',uncertain=True)
            remote={'container':data['id']};checkpoint('uploading',remote)
            if 'video_url' not in payload:
                url=self.upload_url(data.get('uri',''),['rupload.facebook.com'])
                with video.open('rb') as source:self.call('POST',url,mutation=True,raw=True,headers={'Authorization':'OAuth '+self.token(p),'offset':'0','file_size':str(size),'Content-Type':'application/octet-stream'},content=source)
        else:
            # Single-chunk uploads are bounded to 64 MB here; never misreport larger uploads.
            if size>64*1024*1024:raise ValueError('TikTok upload currently supports files up to 64 MB.')
            mode=self.env.get('TIKTOK_PUBLISH_MODE','inbox')
            if mode not in ('inbox','direct'):raise ValueError('Unsupported TikTok upload mode.')
            payload={'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}}
            if mode=='direct':payload['post_info']={'title':caption(post),'privacy_level':options['tiktok_privacy'],'disable_comment':options['disable_comment'],'disable_duet':options['disable_duet'],'disable_stitch':options['disable_stitch']}
            endpoint='post/publish/inbox/video/init/' if mode=='inbox' else 'post/publish/video/init/'
            data=self.call('POST','https://open.tiktokapis.com/v2/'+endpoint,mutation=True,headers=self.headers(p),json=payload)['data']
            if not data.get('publish_id'):raise PlatformError('TikTok returned no publication ID.',uncertain=True)
            remote={'publish_id':data['publish_id'],'delivery_mode':mode};checkpoint('uploading',remote)
            url=self.upload_url(data.get('upload_url',''),['tiktokapis.com'])
            with video.open('rb') as source:self.call('PUT',url,mutation=True,raw=True,headers={'Content-Type':'video/mp4','Content-Length':str(size),'Content-Range':f'bytes 0-{size-1}/{size}'},content=source)
        checkpoint('processing',remote)
        return self.poll(p,remote,checkpoint)

    def poll(self,p,remote,checkpoint):
        if p=='instagram':
            data=self.call('GET',self.igbase+remote['container'],headers=self.headers(p),params={'fields':'status_code'})
            status=data.get('status_code')
            if status in ('ERROR','EXPIRED'):return remote|{'status':'failed','issue':'Instagram container failed or expired.'}
            if status!='FINISHED':return remote|{'status':'processing'}
            checkpoint('submitting',remote)
            account='me' if 'graph.instagram.com' in self.igbase else self.env['INSTAGRAM_BUSINESS_ACCOUNT_ID']
            data=self.call('POST',self.igbase+account+'/media_publish',mutation=True,headers=self.headers(p),data={'creation_id':remote['container']})
            if not data.get('id'):raise PlatformError('Instagram returned no published ID.',uncertain=True)
            result=remote|{'status':'published','id':data['id'],'issue':''};checkpoint('published',result)
            link=self.call('GET',self.igbase+data['id'],headers=self.headers(p),params={'fields':'permalink'})
            return result|{'url':link.get('permalink','')}
        data=self.tk('post/publish/status/fetch/',{'publish_id':remote['publish_id']})['data']
        if data.get('status')=='FAILED':return remote|{'status':'failed','issue':'TikTok rejected the upload; check its creator portal.'}
        if data.get('status')=='SEND_TO_USER_INBOX':return remote|{'status':'awaiting_mobile','issue':'Sent to TikTok inbox. Open the TikTok mobile app to review and publish.'}
        ids=data.get('publicaly_available_post_id') or data.get('publicly_available_post_id') or []
        if data.get('status')=='PUBLISH_COMPLETE':return remote|{'status':'published','id':str(ids[0]) if ids else '', 'url':'','issue':''}
        return remote|{'status':'processing'}

    def videos(self,p):
        profile=self.profile(p)
        if p=='youtube':
            rows=self.call('GET','https://www.googleapis.com/youtube/v3/playlistItems',headers=self.headers(p),params={'part':'contentDetails','playlistId':profile['uploads'],'maxResults':50}).get('items',[])
            ids=','.join(r['contentDetails']['videoId'] for r in rows)
            if not ids:return []
            rows=self.call('GET','https://www.googleapis.com/youtube/v3/videos',headers=self.headers(p),params={'part':'snippet,statistics','id':ids}).get('items',[])
            result=[{'id':r['id'],'title':r['snippet']['title'],'url':'https://www.youtube.com/watch?v='+r['id'],'views':int(r['statistics']['viewCount']) if 'viewCount' in r['statistics'] else None,'likes':int(r['statistics']['likeCount']) if 'likeCount' in r['statistics'] else None,'comments':int(r['statistics']['commentCount']) if 'commentCount' in r['statistics'] else None,'shares':None} for r in rows]
            try:
                report=self.call('GET','https://youtubeanalytics.googleapis.com/v2/reports',headers=self.headers(p),params={'ids':'channel==MINE','startDate':'2005-01-01','endDate':datetime.now(timezone.utc).date().isoformat(),'dimensions':'video','metrics':'views,likes,comments,shares','filters':'video=='+ids})
                counts={r[0]:r[1:] for r in report.get('rows',[])}
                for item in result:
                    if item['id'] in counts:item.update(dict(zip(('views','likes','comments','shares'),counts[item['id']])))
            except PlatformError:pass  # Upload/read scopes can exist without Analytics API permission.
            return result
        if p=='tiktok':
            data=self.call('POST','https://open.tiktokapis.com/v2/video/list/',headers=self.headers(p),params={'fields':'id,title,share_url,view_count,like_count,comment_count,share_count'},json={'max_count':20})
            return [{'id':r['id'],'title':r.get('title','TikTok video'),'url':r.get('share_url',''),**{out:r.get(key) for out,key in [('views','view_count'),('likes','like_count'),('comments','comment_count'),('shares','share_count')]}} for r in data.get('data',{}).get('videos',[])]
        rows=self.call('GET',self.igbase+profile['id']+'/media',headers=self.headers(p),params={'fields':'id,caption,permalink,like_count,comments_count,media_type','limit':25}).get('data',[])
        result=[]
        for r in rows:
            metrics={'views':None,'shares':None}
            try:
                insights=self.call('GET',self.igbase+r['id']+'/insights',headers=self.headers(p),params={'metric':'views,shares'}).get('data',[])
                for item in insights:
                    if item['name'] in metrics:metrics[item['name']]=item.get('total_value',{}).get('value',item.get('values',[{}])[0].get('value'))
            except PlatformError:pass  # Counts still available; missing insights stay null, never fabricated zero.
            result.append({'id':r['id'],'title':r.get('caption','Instagram post')[:100],'url':r.get('permalink',''),'likes':r.get('like_count'),'comments':r.get('comments_count'),**metrics})
        return result
