import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';
import {storageKey} from '../../war_studio/web/state.mjs';

async function fixture(run){
 const root=resolve('war_studio/web'),allowed=new Set(['index.html','studio.css','studio.mjs','state.mjs','backend.mjs']);
 const server=createServer(async(req,res)=>{const name=req.url==='/'?'index.html':req.url.slice(1);if(!allowed.has(name)){res.writeHead(404).end();return;}
  try{res.setHeader('Content-Type',name.endsWith('.mjs')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');res.end(await readFile(resolve(root,name)));}catch{res.writeHead(404).end();}
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true});
 try{const page=await browser.newPage({viewport:{width:1440,height:1000}});await run(page,`http://127.0.0.1:${server.address().port}`);}finally{await browser.close();await new Promise(r=>server.close(r));}
}

test('studio generation, scoped edits, saved platform metadata and analytics work without production APIs',async()=>fixture(async(page,url)=>{
 const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith(url))external.push(r.url());});
 await page.clock.install();await page.goto(url);
 assert.equal(await page.getByRole('heading',{name:'Make something worth watching.'}).count(),1);
 await page.getByLabel('What should we explore?').fill('The river crossing');
 await page.getByRole('button',{name:'Generate video'}).click();
 assert.equal(await page.getByRole('heading',{name:'The river crossing'}).count(),1);
 assert.match(await page.locator('#pipeline').textContent(),/Research/);
 await page.reload();assert.equal(await page.getByRole('button',{name:/The river crossing/}).count(),1);
 await page.getByRole('button',{name:/The river crossing/}).click();await page.clock.fastForward(17000);
 await page.waitForFunction(()=>document.querySelector('#pipeline').textContent.includes('Demo complete'));
 await page.getByRole('button',{name:'Map & units',exact:true}).click();
 await page.getByLabel('Your edit').fill('Follow the river, then move closer.');
 await page.getByRole('button',{name:'Apply edits',exact:true}).click();
 assert.match(await page.locator('.page-heading').textContent(),/Revision 2/);
 assert.equal(await page.getByRole('button',{name:'Apply edits',exact:true}).isDisabled(),true);
 await page.getByRole('button',{name:'Activity',exact:true}).click();assert.match(await page.locator('.history-item').first().textContent(),/Map & units/);
 await page.clock.fastForward(17000);await page.getByRole('button',{name:'Publish',exact:true}).click();
 await page.getByLabel('Video title',{exact:true}).fill('<b>A new title</b>');
 await page.getByLabel('Hashtags',{exact:true}).fill('#Terrain #History');
 await page.getByRole('button',{name:'Instagram',exact:true}).click();
 await page.getByLabel('Post title',{exact:true}).fill('An Instagram title');
 await page.getByRole('button',{name:'YouTube',exact:true}).click();assert.equal(await page.getByLabel('Video title',{exact:true}).inputValue(),'<b>A new title</b>');
 await page.getByRole('button',{name:'Publish video',exact:true}).click();
 assert.equal(await page.getByRole('dialog').isVisible(),true);assert.equal(await page.getByRole('button',{name:'Connect APIs to publish'}).isDisabled(),true);
 assert.match(await page.getByRole('dialog').textContent(),/<b>A new title<\/b>/);
 assert.equal(await page.locator('dialog b:has-text("A new title")').count(),0);
 await page.getByRole('button',{name:'Back to editing'}).click();
 for(const c of ['youtube','instagram','tiktok'])await page.locator(`[data-target="${c}"]`).uncheck();
 await page.getByRole('button',{name:'Publish video',exact:true}).click();assert.match(await page.locator('#toast').textContent(),/Choose at least one/);
 await page.getByRole('button',{name:'Analytics',exact:true}).click();assert.equal(await page.locator('[data-metric="Total views"]').textContent(),'119,640');
 await page.getByRole('button',{name:'TikTok',exact:true}).click();await page.getByLabel('Analytics video').selectOption('austerlitz');
 assert.equal(await page.locator('[data-metric="Total views"]').textContent(),'18,600');
 await page.getByLabel('Analytics period').selectOption('7');assert.equal(await page.locator('[data-metric="Total views"]').textContent(),'5,952');
 await page.getByRole('button',{name:'Video library',exact:true}).click();await page.getByLabel('Search videos').fill('missing');assert.match(await page.locator('#video-grid').textContent(),/No stories/);
 await page.getByLabel('Search videos').fill('river');assert.equal(await page.locator('.video-card').count(),1);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
}));

test('studio recovers corrupt storage, explains missing media and fits phone screens',async()=>fixture(async(page,url)=>{
 await page.goto(url);await page.evaluate(key=>localStorage.setItem(key,'broken'),storageKey);await page.reload();
 await page.getByRole('button',{name:/The trap at Austerlitz/}).click();
 await page.waitForSelector('#video-fallback:not(.hidden)');
 await page.setViewportSize({width:390,height:844});
 for(const panel of ['Edit video','Publish','Activity']){
  await page.getByRole('button',{name:panel,exact:true}).click();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 await page.getByRole('button',{name:'Overview',exact:true}).click();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.getByRole('button',{name:'Generate video'}).click();
 assert.equal(await page.getByRole('heading',{name:'Researcher’s choice',exact:true}).count(),1);
 await page.getByRole('button',{name:'Cancel demo run'}).click();assert.match(await page.locator('#workspace-badge').textContent(),/Draft/);
 await page.getByRole('button',{name:'Publishing',exact:true}).click();assert.equal(await page.getByRole('button',{name:'API integration coming next'}).count(),3);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
}));

test('studio remains usable when browser storage is unavailable',async()=>fixture(async(page,url)=>{
 await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new Error('Storage unavailable');};});
 await page.goto(url);await page.getByRole('button',{name:/The trap at Austerlitz/}).click();
 await page.getByRole('button',{name:'Publish',exact:true}).click();await page.getByLabel('Video title',{exact:true}).fill('Unsaved title');
 assert.match(await page.locator('#saved-label').textContent(),/Not saved/);
 assert.match(await page.locator('#toast').textContent(),/storage is unavailable/);
 await page.getByRole('button',{name:'New video',exact:true}).click();await page.getByRole('button',{name:'Generate video'}).click();
 assert.equal(await page.getByRole('heading',{name:'Researcher’s choice',exact:true}).count(),1);
}));
