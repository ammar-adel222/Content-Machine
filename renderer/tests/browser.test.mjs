import test from 'node:test';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';

test('real PixiJS canvas draws, seeks backwards deterministically, and shows playback controls',async()=>{
 const primitive={kind:'rect',x:0,y:0,width:1.2,height:.8,points:[],fill:'team',stroke:'ink',stroke_width:.05};
 const scene={scene_id:'s1',focus:{x:.5,y:.5},view_width:1,labels:['Synthetic renderer test'],start:0,end:20,
  actions:[{id:'move',unit_id:'a',kind:'move',route:[{x:.2,y:.5},{x:.7,y:.5}],formation:'column',stagger:.2}]};
 const data={topic:'Synthetic renderer test',duration:20,blueprint:{scale:'tactical',scenes:[scene],
  terrain:[{id:'land',kind:'desert',label:'Test land',shape:'polygon',points:[{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}]}],
  forces:[{id:'a',side:'Blue',position:{x:.2,y:.5},subgroups:3}]},scenes:[scene],
  timeline:[{kind:'introduce',unit_id:'a',start_sec:0,end_sec:0,action_id:'intro-a'},
   {kind:'move',unit_id:'a',start_sec:0,end_sec:20,action_id:'move'}],
  bindings:{terrain:{land:'icon'},unit:{a:'icon'}},assets:{icon:{primitives:[primitive]}},
  captions:[{start:0,end:10,text:'First test phrase.'},{start:10,end:20,text:'Second test phrase.'}]};
 const root=resolve('war_content/web');
 const server=createServer(async(req,res)=>{
  try{
   if(req.url==='/scene.json'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));return;}
   const file=req.url==='/pixi.min.js'?resolve('renderer/node_modules/pixi.js/dist/pixi.min.js'):resolve(root,req.url==='/'?'index.html':req.url.slice(1));
   if(!file.startsWith(root) && !file.endsWith('pixi.min.js')){res.writeHead(403).end();return;}
   res.setHeader('Content-Type',file.endsWith('.html')?'text/html':'text/javascript');res.end(await readFile(file));
  }catch{res.writeHead(404).end();}
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 let browser;
 try{
  browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1080,height:1920}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
  await page.evaluate(()=>contentEngine.renderAt(3));const first=await page.locator('canvas').screenshot();
  await page.evaluate(()=>contentEngine.renderAt(15));const later=await page.locator('canvas').screenshot();
  assert.notDeepEqual(first,later);
  await page.evaluate(()=>contentEngine.renderAt(3));assert.deepEqual(await page.locator('canvas').screenshot(),first);
  await page.getByRole('button',{name:'Play'}).click();await page.waitForFunction(()=>document.getElementById('play').textContent==='Pause');
  await page.getByRole('button',{name:'Pause'}).click();
  await page.locator('#seek').fill('14');await page.locator('#seek').dispatchEvent('input');
  assert.equal(await page.locator('#time').textContent(),'0:14');assert.deepEqual(errors,[]);
 }finally{await browser?.close();await new Promise(r=>server.close(r));}
});
