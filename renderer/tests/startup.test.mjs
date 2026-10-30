import test from 'node:test';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

test('opening the template from disk shows actionable instructions and disabled controls',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.goto(pathToFileURL(resolve('war_content/web/index.html')).href);
  await page.waitForFunction(()=>globalThis.contentError);
  assert.match(await page.locator('#error').textContent(),/preview.cmd/);
  assert.equal(await page.getByRole('button',{name:'Play'}).isDisabled(),true);
  assert.match(await page.locator('#screen').textContent(),/unavailable/);
 }finally{await browser.close();}
});

test('missing runtime, player module and scene each show errors instead of blank playback',async()=>{
 const root=resolve('war_content/web'),browser=await chromium.launch({headless:true});
 try{
  for(const missing of ['pixi.min.js','player.mjs','scene.json']){
   const server=createServer(async(req,res)=>{
    const name=req.url==='/'?'index.html':req.url.slice(1);
    if(name===missing || name.includes('..')){res.writeHead(404).end();return;}
    try{
     const file=name==='pixi.min.js'?resolve('renderer/node_modules/pixi.js/dist/pixi.min.js'):resolve(root,name);
     res.setHeader('Content-Type',name.endsWith('.html')?'text/html':'text/javascript');res.end(await readFile(file));
    }catch{res.writeHead(404).end();}
   });
   await new Promise(r=>server.listen(0,'127.0.0.1',r));
   const page=await browser.newPage();
   try{
    await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>globalThis.contentError);
    assert.ok((await page.locator('#error').textContent()).length>20);
    assert.equal(await page.getByRole('button',{name:'Play'}).isDisabled(),true);
   }finally{await page.close();await new Promise(r=>server.close(r));}
  }
 }finally{await browser.close();}
});
