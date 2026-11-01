import test from 'node:test';
import assert from 'node:assert/strict';
import {heightAt,meshData,terrainPoint,labelledFeatures} from '../../war_content/web/battlefield.mjs';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
test('battlefield mesh has measured height, matching texture coordinates and indexed triangles',()=>{
 const field={layer:{width:100,height:100,bounds:{west:0,south:0,east:.1,north:.1}},heights:{columns:2,rows:2,values:[0,100,200,300]},exaggeration:5};
 assert.equal(heightAt(field.heights,.5,.5),150);assert.equal(heightAt(field.heights,-1,2),200);
 const flat=terrainPoint(field,.5,.5,0),raised=terrainPoint(field,.5,.5,100);
 assert.ok(raised.y<flat.y);assert.equal(raised.x,flat.x);
 const mesh=meshData(field);assert.equal(mesh.vertices.length,8);assert.equal(mesh.uvs.length,8);assert.equal(mesh.indices.length,6);
 assert.ok([...mesh.uvs].every(v=>v>=0&&v<=1));assert.ok([...mesh.indices].every(v=>v>=0&&v<4));
});

test('actual WebGL battlefield mesh loads with a stream and village and supports deterministic seeking',async()=>{
 const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 let server;
 try{
  const page=await browser.newPage({viewport:{width:1080,height:1920}});
  await page.setContent('<canvas width="4" height="4"></canvas>');
  const png=Buffer.from(await page.evaluate(()=>{const c=document.querySelector('canvas');c.getContext('2d').fillRect(0,0,4,4);return c.toDataURL().split(',')[1];}),'base64');
  const field={layer:{title:'Test terrain',width:100,height:100,bounds:{west:0,south:0,east:.1,north:.1},relief:'relief-battlefield.png'},
   heights:{columns:3,rows:3,values:[200,210,220,210,300,240,220,250,260]},exaggeration:5,
   features:[{name:'Test stream',kind:'stream',points:[[.02,.09],[.02,.01]]},{name:'Test village',kind:'village',points:[[.03,.06]]},{name:'Test heights',kind:'ridge',points:[[.06,.06]]}]};
  const data={topic:'Tactical test',duration:20,battlefield:field,
   scenes:[{start:0,end:10,labels:['Heights']},{start:10,end:20,labels:['Stream']}],
   captions:[{start:0,end:10,text:'First tactical phase.'},{start:10,end:20,text:'Second tactical phase.'}]};
  const root=resolve('war_content/web');
  server=createServer(async(req,res)=>{
   const pathname=new URL(req.url,'http://localhost').pathname,name=pathname==='/'?'index.html':pathname.slice(1);
   try{
    if(name==='scene.json'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));return;}
    if(name==='relief-battlefield.png'){res.setHeader('Content-Type','image/png');res.end(png);return;}
    if(name.includes('..')){res.writeHead(404).end();return;}
    const file=name==='pixi.min.js'?resolve('renderer/node_modules/pixi.js/dist/pixi.min.js'):resolve(root,name);
    res.setHeader('Content-Type',name.endsWith('.html')?'text/html':'text/javascript');res.end(await readFile(file));
   }catch{res.writeHead(404).end();}
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
  assert.match(await page.locator('small').textContent(),/Tactical terrain study/);
  await page.evaluate(()=>contentEngine.renderAt(3));const initial=await page.locator('canvas').screenshot();
  await page.evaluate(()=>contentEngine.renderAt(15));assert.notDeepEqual(await page.locator('canvas').screenshot(),initial);
  await page.evaluate(()=>contentEngine.renderAt(3));assert.deepEqual(await page.locator('canvas').screenshot(),initial);
  for(const aspect of ['portrait','landscape']){
   await page.goto(`http://127.0.0.1:${server.address().port}/?aspect=${aspect}`);await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
   assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
   const pixels=await page.evaluate(()=>{
    const source=contentEngine.app.canvas,c=document.createElement('canvas');c.width=source.width;c.height=source.height;
    const ctx=c.getContext('2d');ctx.drawImage(source,0,0);
    return {width:source.width,height:source.height,corners:[[2,2],[source.width-3,2],[2,source.height-3],[source.width-3,source.height-3]].map(([x,y])=>[...ctx.getImageData(x,y,1,1).data])};
   });
   assert.equal(pixels.width,aspect==='portrait'?1080:1920);assert.equal(pixels.height,aspect==='portrait'?1920:1080);
   for(const rgba of pixels.corners){assert.equal(rgba[3],255);assert.notDeepEqual(rgba.slice(0,3),[238,232,216]);}
  }
  // Exercise the actual projected choreography branch, not only the pure math.
  const move={id:'advance',kind:'move',unit_id:'unit',formation:'column',stagger:.2,
   route:[{x:.3,y:.7},{x:.3,y:.5},{x:.65,y:.4}]};
  Object.assign(data,{purpose:'unit_animation_study',animation_camera:{x:.5,y:.5},
   blueprint:{scale:'tactical',forces:[{id:'unit',kind:'infantry',side:'Blue',position:move.route[0],subgroups:4}],scenes:[{actions:[move]}]},
   timeline:[{kind:'introduce',unit_id:'unit',start_sec:0,end_sec:0},{action_id:'advance',kind:'move',unit_id:'unit',start_sec:1,end_sec:12}],
   bindings:{unit:{unit:'shape'}},assets:{shape:{primitives:[{kind:'ellipse',x:0,y:0,width:.8,height:.8,fill:'team',stroke:'ink',stroke_width:.05}]}}});
  await page.goto(`http://127.0.0.1:${server.address().port}/?aspect=portrait`);await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
  await page.evaluate(()=>contentEngine.renderAt(4));const movingFrame=await page.locator('canvas').screenshot();
  const actors=await page.evaluate(()=>{const all=[];function visit(node){if(node.label?.startsWith('unit:'))all.push({x:node.x,y:node.y,angle:node.rotation,alpha:node.alpha});for(const child of node.children??[])visit(child);}visit(contentEngine.app.stage);return all;});
  assert.equal(actors.length,4);assert.ok(actors.every(a=>a.alpha===1&&Number.isFinite(a.angle)));
  assert.ok(new Set(actors.map(a=>a.x+','+a.y)).size===4);
  await page.evaluate(()=>contentEngine.renderAt(17));assert.notDeepEqual(await page.locator('canvas').screenshot(),movingFrame);
  await page.evaluate(()=>contentEngine.renderAt(4));assert.deepEqual(await page.locator('canvas').screenshot(),movingFrame);
  // Production replay uses the same terrain/units with director-controlled camera cues.
  data.unit_presentations={unit:'upright'};data.purpose='battlefield_replay';data.terrain_credits='Synthetic terrain fixture';
  data.scenes[0].focus={x:.35,y:.55};data.scenes[0].view_width=1;
  data.scenes[1].focus={x:.65,y:.45};data.scenes[1].view_width=.6;
  await page.goto(`http://127.0.0.1:${server.address().port}/?aspect=portrait`);await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
  assert.match(await page.locator('small').textContent(),/Tactical battlefield/);
  await page.evaluate(()=>contentEngine.renderAt(4));const replayFrame=await page.locator('canvas').screenshot();
  const replayActors=await page.evaluate(()=>{let n=0;function visit(node){if(node.label?.startsWith('unit:')&&node.alpha===1)n++;for(const c of node.children??[])visit(c);}visit(contentEngine.app.stage);return n;});
  assert.equal(replayActors,4);
  const presentationState=()=>page.evaluate(()=>{
   let caption,trail;function visit(n){if(n.label==='captions')caption=n;if(n.label==='movement-trails')trail=n;for(const c of n.children??[])visit(c);}visit(contentEngine.app.stage);
   return {scale:trail.parent.scale.x,trailWidth:trail.getBounds().width,y:caption.y,
    active:caption.activeWord,words:caption.children.filter(n=>n.visible).map(n=>({fill:n.currentFill,stroke:n.style.stroke.width}))};
  });
  const movingPresentation=await presentationState();
  assert.ok(movingPresentation.trailWidth>0);
  assert.ok(movingPresentation.words.some(w=>w.fill===0xf5c542));
  assert.ok(movingPresentation.words.every(w=>w.stroke===10));
  await page.evaluate(()=>contentEngine.renderAt(13));const staticStart=await presentationState();
  await page.evaluate(()=>contentEngine.renderAt(17));const staticEnd=await presentationState();
  assert.ok(staticEnd.scale>staticStart.scale);assert.equal(staticEnd.y,staticStart.y);
  assert.equal(staticEnd.trailWidth,0);
  await page.evaluate(()=>contentEngine.renderAt(4));
  const rotations=await page.evaluate(()=>{
   const result=[];function visit(node){if(node.label?.startsWith('unit:'))result.push([node.rotation,node.children[1].rotation]);for(const c of node.children??[])visit(c);}
   visit(contentEngine.app.stage);return result;
  });
  assert.ok(rotations.every(([heading,body])=>heading===0&&body===0));

  const captionCollisions=await page.evaluate(()=>{
   const units=[];let caption;
   function visit(node){
    if(node.label?.startsWith('unit:')&&node.alpha===1)units.push(node.getBounds());
    if(node.text==='First tactical phase.')caption=node.getBounds();
    for(const child of node.children??[])visit(child);
   }
   visit(contentEngine.app.stage);
   if(!caption)throw Error('Missing rendered timed caption');
   return {y:caption.y,bottom:caption.y+caption.height};
  });
  assert.equal(captionCollisions.y,Math.round(1920*.72));
  assert.ok(captionCollisions.bottom<1920*.85);

  await page.evaluate(()=>contentEngine.renderAt(17));assert.notDeepEqual(await page.locator('canvas').screenshot(),replayFrame);
  await page.evaluate(()=>contentEngine.renderAt(4));assert.deepEqual(await page.locator('canvas').screenshot(),replayFrame);

  data.blueprint.forces.push({id:'enemy',kind:'infantry',side:'Red',position:{x:.67,y:.4},subgroups:3});
  data.bindings.unit.enemy='shape';data.unit_presentations.enemy='upright';
  data.blueprint.scenes[0].actions.push({id:'contact',kind:'engage',unit_id:'unit',target_id:'enemy'});
  data.timeline.push({kind:'introduce',unit_id:'enemy',start_sec:0,end_sec:0},{action_id:'contact',kind:'engage',unit_id:'unit',start_sec:12.1,end_sec:16.8});
  await page.goto(`http://127.0.0.1:${server.address().port}/?aspect=portrait`);await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError);
  assert.equal(await page.evaluate(()=>globalThis.contentError),undefined);
  const activeClashes=()=>page.evaluate(()=>{
   const nodes=[];function visit(n){if(n.label?.startsWith('clash:')&&n.visible)nodes.push(n.label);for(const c of n.children??[])visit(c);}visit(contentEngine.app.stage);return nodes;
  });
  await page.evaluate(()=>contentEngine.renderAt(11.9));assert.deepEqual(await activeClashes(),[]);
  await page.evaluate(()=>contentEngine.renderAt(13));assert.deepEqual(await activeClashes(),['clash:contact']);
  const clashHud=await page.evaluate(()=>{let value='';function visit(n){if(n.label==='hud:clash')value=n.text;for(const c of n.children??[])visit(c);}visit(contentEngine.app.stage);return value;});
  assert.match(clashHud,/CLASH/);
  const clashFrame=await page.locator('canvas').screenshot();
  await page.evaluate(()=>contentEngine.renderAt(18));assert.deepEqual(await activeClashes(),[]);
  await page.evaluate(()=>contentEngine.renderAt(13));assert.deepEqual(await page.locator('canvas').screenshot(),clashFrame);
 }finally{await browser.close();if(server)await new Promise(r=>server.close(r));}
});


test('segmented waterways have one label per river while retaining village labels',()=>{
 const stream={kind:'stream',name:'Goldbach',points:[[0,0],[1,1]]};
 const village={kind:'village',name:'Telnitz',points:[[0,0]]};
 const features=[{...stream},{...stream},{...stream},village];
 assert.deepEqual(labelledFeatures(features),[features[1],village]);
});
