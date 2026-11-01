import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
import {initialState} from '../../war_studio/web/state.mjs';

async function fixture(run,{offline=false}={}){
 const p={...initialState().projects[0],revision_id:'revision-1',workflow_status:'awaiting_review',video_url:null,
  stages:['research','writing','script_review','direction','plan_review','narration','terrain','assets','timing','effects','music_source','mix','visual_review','audio_review','picture','mux','final_review'].map(name=>({name,status:'done'})),
  issues:[],job:null,publications:[],publish_options:{youtube_privacy:'private',tiktok_privacy:'',disable_comment:true,disable_duet:true,disable_stitch:true},demo:false,sample:false};
 const projects=[p],requests=[];const files=new Set(['index.html','studio.css','studio.mjs','state.mjs','backend.mjs']);
 const server=createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost'),path=url.pathname;
  if(path.startsWith('/api/')){
   let text='';for await(const chunk of req)text+=chunk;const body=text?JSON.parse(text):null;
   requests.push({path,method:req.method,body});res.setHeader('Content-Type','application/json');
   if(path==='/api/config'){res.statusCode=offline?503:200;res.end(JSON.stringify(offline?{detail:'Offline'}:{mode:'live',key:'test-session'}));return;}
   if(req.method!=='GET'&&req.headers['x-studio-key']!=='test-session'){res.writeHead(403).end('{}');return;}
   let data={};
   if(path==='/api/projects'){
    if(req.method==='POST'){const created={...structuredClone(p),id:'new-project',title:body.topic,topic:body.topic,status:'generating',workflow_status:'pending',revision_id:'new-revision',job:{id:'job',kind:'generate',status:'queued',stage:''}};projects.push(created);data=created;}
    else data={projects};
   }else if(path==='/api/connections')data=Object.fromEntries(['youtube','instagram','tiktok'].map(id=>[id,{configured:true,status:'verified',id:id+'-account',name:id+' account',privacy:['SELF_ONLY'],mode:'sandbox'}]));
   else if(path==='/api/analytics')data={views:123,likes:5,comments:2,shares:null,engagement:null,rows:[{id:p.id,title:p.title,views:123,likes:5,comments:2,shares:null,engagement:null}],channels:[{platform:'youtube',views:123},{platform:'instagram',views:null},{platform:'tiktok',views:null}],videos:[{id:p.id,title:p.title}],basis:'lifetime_snapshot',updated:1000,issues:{tiktok:'Scope unavailable'}};
   else if(path.endsWith('/metadata')){p.metadata=body.posts;p.selectedPlatforms=body.selected;p.publish_options=Object.fromEntries(Object.entries(body).filter(([k])=>!['posts','selected','revision'].includes(k)));data={status:'saved'};}
   else if(path.endsWith('/edits')){p.revision_id='revision-2';p.revision=2;p.status='generating';p.job={id:'edit-job',kind:'generate',status:'queued',stage:''};data=p;}
   else if(path.endsWith('/prepare'))data={ticket:'ticket',video_sha256:'a'.repeat(64),metadata:{posts:p.metadata,...p.publish_options},accounts:{youtube:{name:'youtube account'}},skip:[]};
   else if(path.endsWith('/publish'))data={id:'publish-job',status:'queued'};
   res.end(JSON.stringify(data));return;
  }
  const name=path==='/'?'index.html':path.slice(1);if(!files.has(name)){res.writeHead(404).end();return;}
  res.setHeader('Content-Type',name.endsWith('.mjs')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');res.end(await readFile(resolve('war_studio/web',name)));
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch();
 try{await run(await browser.newPage({viewport:{width:1440,height:1000}}),`http://127.0.0.1:${server.address().port}`,{p,projects,requests});}finally{await browser.close();await new Promise(r=>server.close(r));}
}

test('connected UI uses backend projects, debounced metadata and explicit publish confirmation',async()=>fixture(async(page,url,fixture)=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(url);
 await page.getByRole('button',{name:/The trap at Austerlitz/}).click();assert.match(await page.locator('#pipeline').textContent(),/17 \/ 17/);
 await page.getByRole('button',{name:'Publish',exact:true}).click();
 await page.getByLabel('Video title',{exact:true}).fill('A saved real title');
 const saved=page.waitForResponse(r=>r.url().endsWith('/metadata')&&r.request().method()==='PUT');await saved;
 assert.equal(fixture.p.metadata.youtube.title,'A saved real title');assert.equal(fixture.requests.filter(r=>r.path.endsWith('/metadata')).length,1);
 assert.match(await page.locator('.panel').last().textContent(),/TikTok sends this video to your mobile inbox/);
 assert.equal(await page.getByText('AI-generated content labels are enabled for YouTube and TikTok.').count(),0);
 await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{globalThis.copiedCaption=text;}}}));
 await page.getByRole('button',{name:'Copy TikTok caption & hashtags',exact:true}).click();
 assert.match(await page.evaluate(()=>globalThis.copiedCaption),/#MilitaryHistory/);
 await page.evaluate(()=>{navigator.clipboard.writeText=async()=>{throw Error('Unavailable');};});
 await page.getByRole('button',{name:'Copy TikTok caption & hashtags',exact:true}).click();
 assert.match(await page.locator('#toast').textContent(),/Clipboard unavailable/);
 await page.getByRole('button',{name:'Publish video',exact:true}).click();
 await page.getByRole('button',{name:'Approve & publish',exact:true}).waitFor();assert.equal(fixture.requests.filter(r=>r.path.endsWith('/publish')).length,0);
 await page.getByRole('button',{name:'Approve & publish',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('dialog').open);
 assert.deepEqual(fixture.requests.find(r=>r.path.endsWith('/publish')).body,{ticket:'ticket',consent:true});
 await page.getByRole('button',{name:'Edit video',exact:true}).click();
 await page.getByLabel('Your edit').fill('Make the music quieter.');
 await page.locator('#edit-kind').selectOption('music_mix');await page.locator('[data-level="music_gain_db"]').fill('-35');await page.getByRole('button',{name:'Apply edits',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.page-heading').textContent.includes('Revision 2'));
 assert.equal(fixture.requests.find(r=>r.path.endsWith('/edits')).body.kind,'music_mix');
 assert.equal(fixture.requests.find(r=>r.path.endsWith('/edits')).body.patch.music_gain_db,-35);
 await page.getByRole('button',{name:'Analytics',exact:true}).click();await page.getByText('Latest lifetime counters from your connected accounts.').waitFor();
 assert.equal(await page.locator('[data-metric="Total views"]').textContent(),'123');assert.equal(await page.locator('[data-metric="Shares"]').textContent(),'—');
 assert.match(await page.locator('main').textContent(),/Scope unavailable/);
 await page.getByRole('button',{name:'New video',exact:true}).click();await page.getByLabel('What should we explore?').fill('A new real topic');
 await page.getByRole('button',{name:'Generate video',exact:true}).click();await page.getByRole('heading',{name:'A new real topic',exact:true}).waitFor();
 assert.equal(fixture.requests.find(r=>r.path==='/api/projects'&&r.method==='POST').body.terrain,'battlefield');
 assert.deepEqual(errors,[]);
}));

test('backend outage displays an error instead of silently switching to demo projects',async()=>fixture(async(page,url)=>{
 await page.goto(url);await page.getByRole('heading',{name:'Studio is unavailable.'}).waitFor();
 assert.equal(await page.locator('.video-card').count(),0);
 assert.equal(await page.getByRole('button',{name:'Reload studio'}).count(),1);
},{offline:true}));
