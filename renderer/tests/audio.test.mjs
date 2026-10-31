import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';

function waveFixture(){
 const rate=8000,frames=rate*2,b=Buffer.alloc(44+frames*2);
 b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);
 b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(rate,24);b.writeUInt32LE(rate*2,28);
 b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(frames*2,40);
 for(let i=0;i<frames;i++)b.writeInt16LE(Math.round(Math.sin(i*2*Math.PI*120/rate)*1000),44+i*2);
 return b;
}

test('real browser sound follows play, pause, seek, mute and deterministic frame inspection',async()=>{
 const wav=waveFixture();let available=true;
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://localhost').pathname;
  try{
   if(path==='/soundtrack.wav'){
    if(!available){res.writeHead(404).end();return;}
    const range=/bytes=(\d+)-(\d*)/.exec(req.headers.range??''),start=range?Number(range[1]):0,end=range&&range[2]?Number(range[2]):wav.length-1;
    res.setHeader('Content-Type','audio/wav');res.setHeader('Accept-Ranges','bytes');res.setHeader('Cache-Control','no-store');
    if(range){res.statusCode=206;res.setHeader('Content-Range',`bytes ${start}-${end}/${wav.length}`);}
    res.setHeader('Content-Length',end-start+1);res.end(wav.subarray(start,end+1));return;
   }
   if(path.endsWith('.mjs')){res.setHeader('Content-Type','text/javascript');res.end(await readFile(new URL('../../war_content/web'+path,import.meta.url)));return;}
   res.setHeader('Content-Type','text/html');
   res.end(`<button id="play">Play</button><input id="seek" type="range" min="0" max="2" step=".01"><span id="time"></span><button id="mute" hidden>Mute</button><small>silent preview</small><div id="error"></div>
    <script type="module">import {connectPlayback} from './playback.mjs';connectPlayback({duration:2,soundtrack:{file:'soundtrack.wav'}},{},t=>globalThis.visualTime=t);</script>`);
  }catch{res.writeHead(404).end();}
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(()=>globalThis.contentReady);
  assert.equal(await page.getByRole('button',{name:'Mute sound'}).isVisible(),true);
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await page.waitForFunction(()=>contentEngine.audio.currentTime>.12);
  const drift=await page.evaluate(()=>Math.abs(visualTime-contentEngine.audio.currentTime));assert.ok(drift<.12);
  await page.getByRole('button',{name:'Pause',exact:true}).click();
  assert.equal(await page.evaluate(()=>contentEngine.audio.paused),true);
  await page.locator('#seek').fill('1');await page.locator('#seek').dispatchEvent('input');
  assert.equal(await page.evaluate(()=>visualTime),1);await page.waitForFunction(()=>Math.abs(contentEngine.audio.currentTime-1)<.01&&!contentEngine.audio.seeking);
  await page.getByRole('button',{name:'Mute sound'}).click();assert.equal(await page.evaluate(()=>contentEngine.audio.muted),true);
  await page.getByRole('button',{name:'Unmute sound'}).click();assert.equal(await page.evaluate(()=>contentEngine.audio.muted),false);
  await page.evaluate(()=>contentEngine.renderAt(.3));assert.equal(await page.evaluate(()=>contentEngine.audio.paused),true);
  assert.equal(await page.evaluate(()=>visualTime),.3);
  available=false;await page.goto(`http://127.0.0.1:${server.address().port}/?missing=1`);
  await page.waitForFunction(()=>document.getElementById('error').textContent.includes('unavailable'));
  assert.equal(await page.evaluate(()=>globalThis.contentReady),true);
 }finally{await browser.close();await new Promise(r=>server.close(r));}
});
