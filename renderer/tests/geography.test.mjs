import test from 'node:test';
import assert from 'node:assert/strict';
import {projectGeo,scalePixels} from '../../war_content/web/geography.mjs';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';

test('geographic projection is north-up, preserves local aspect, and has a real scale',()=>{
 const layer={width:1200,height:850,bounds:{west:-61,south:-53,east:-57,north:-51}},frame={x:50,y:300,width:980,height:980*850/1200};
 const p=projectGeo(-59,-52,layer,frame),north=projectGeo(-59,-51.9,layer,frame),east=projectGeo(-58.9,-52,layer,frame);
 assert.ok(north.y<p.y);assert.ok(east.x>p.x);
 assert.ok(Math.abs((east.x-p.x)/(p.y-north.y)-Math.cos(52*Math.PI/180))<1e-9);
 const km50=projectGeo(-59+50/(111.32*Math.cos(52*Math.PI/180)),-52,layer,frame);
 assert.ok(Math.abs(km50.x-p.x-scalePixels(50,layer,frame))<1e-9);
});

test('real geography renders from local relief, omits legacy map labels, and supports seeking',async()=>{
 const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 let server;
 try{
  const page=await browser.newPage({viewport:{width:1080,height:1920}});
  await page.setContent('<canvas width="4" height="4"></canvas>');
  const png=Buffer.from(await page.evaluate(()=>{const c=document.querySelector('canvas');c.getContext('2d').fillRect(0,0,4,4);return c.toDataURL().split(',')[1];}),'base64');
  const shape={kind:'ellipse',x:0,y:0,width:1,height:1,points:[],fill:'team',stroke:'ink',stroke_width:.05};
  const scene={scene_id:'s1',start:0,end:20,labels:['Geographic scene']};
  const layer={id:'overview',title:'Source land',bounds:{west:0,south:0,east:1,north:1},width:1200,height:850,
    land:[{rings:[[[.1,.1],[.9,.1],[.9,.9],[.1,.9],[.1,.1]],[[.4,.4],[.6,.4],[.6,.6],[.4,.6],[.4,.4]]]}],relief:'relief-overview.png',
    places:[{id:'p',name:'Test town',lon:.3,lat:.3,kind:'settlement'}]};
  const data={topic:'Source map',duration:20,scenes:[scene],captions:[{start:0,end:10,text:'First phrase.'},{start:10,end:20,text:'Second phrase.'}],
    timeline:[{kind:'introduce',unit_id:'a',start_sec:1,end_sec:1}],
    blueprint:{terrain:[{label:'LEGACY RECTANGLE MUST NOT APPEAR'}],forces:[{id:'a',side:'Blue'}]},assets:{icon:{primitives:[shape]}},bindings:{unit:{a:'icon'}},
    geography:{region:'Source region',layers:[layer],placements:[{unit_id:'a',place_id:'p',scene_ids:['s1'],note:'Area-level callout.'}],omitted_actions:['legacy-route']}};
  const root=resolve('war_content/web');
  server=createServer(async(req,res)=>{
   const pathname=new URL(req.url,'http://localhost').pathname,name=pathname==='/'?'index.html':pathname.slice(1);
   try{
    if(name==='scene.json'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));return;}
    if(name==='relief-overview.png'){res.setHeader('Content-Type','image/png');res.end(png);return;}
    if(name.includes('..')){res.writeHead(404).end();return;}
    const file=name==='pixi.min.js'?resolve('renderer/node_modules/pixi.js/dist/pixi.min.js'):resolve(root,name);
    res.setHeader('Content-Type',name.endsWith('.html')?'text/html':'text/javascript');res.end(await readFile(file));
   }catch{res.writeHead(404).end();}
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
  const labels=await page.evaluate(()=>{const values=[];function visit(c){if(typeof c.text==='string')values.push(c.text);for(const child of c.children??[])visit(child);}visit(contentEngine.app.stage);return values.join(' ');});
  assert.ok(!labels.includes('LEGACY RECTANGLE'));assert.match(labels,/Source map/);
  await page.evaluate(()=>contentEngine.renderAt(2));const initial=await page.locator('canvas').screenshot();
  await page.evaluate(()=>contentEngine.renderAt(15));assert.notDeepEqual(await page.locator('canvas').screenshot(),initial);
  await page.evaluate(()=>contentEngine.renderAt(2));assert.deepEqual(await page.locator('canvas').screenshot(),initial);
  await page.selectOption('#format','landscape');await page.waitForURL('**aspect=landscape');await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  const dimensions=await page.evaluate(()=>[contentEngine.app.canvas.width,contentEngine.app.canvas.height]);assert.deepEqual(dimensions,[1920,1080]);
 }finally{await browser.close();if(server)await new Promise(r=>server.close(r));}
});
