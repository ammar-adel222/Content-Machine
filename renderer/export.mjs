// Deterministic screenshots/MP4: no recording at wall-clock speed, no remote assets.
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {createReadStream} from 'node:fs';
import {mkdir,stat} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {spawn} from 'node:child_process';
const [bundle,output='preview.mp4',durationArg,fpsArg='30']=process.argv.slice(2);
if(!bundle)throw Error('Usage: node renderer/export.mjs BUNDLE OUTPUT.mp4|png [SECONDS] [FPS]');
const root=resolve(bundle),target=resolve(output),fps=Number(fpsArg);
if(!Number.isInteger(fps)||fps<1||fps>60)throw Error('FPS must be 1–60.');
await mkdir(resolve(target,'..'),{recursive:true});
const server=createServer(async(req,res)=>{
  try {
    const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
    if(!path.startsWith(root+sep) && path!==root){res.writeHead(403).end();return;}
    const file=path===root?resolve(root,'index.html'):path;
    if(!(await stat(file)).isFile()){res.writeHead(404).end();return;}
    res.setHeader('Content-Type',({'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript','.json':'application/json'})[extname(file)]??'application/octet-stream');
    createReadStream(file).pipe(res);
  }catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser,encoder;
try {
  browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
  await page.goto(`http://127.0.0.1:${server.address().port}/index.html?export`);
  await page.waitForFunction(()=>globalThis.contentReady||globalThis.contentError,{},{timeout:60000});
  const error=await page.evaluate(()=>globalThis.contentError);if(error)throw Error(error);
  const total=await page.evaluate(()=>contentEngine.data.duration);
  const duration=durationArg===undefined?total:Number(durationArg);
  if(!Number.isFinite(duration)||duration<0||duration>total)throw Error('Duration/time must be within the storyboard.');
  if(target.endsWith('.png')) {
    await page.evaluate(t=>contentEngine.renderAt(t),durationArg===undefined?0:duration);
    await page.locator('canvas').screenshot({path:target});
  } else {
    if(!target.endsWith('.mp4')||duration<=0)throw Error('Use .png or .mp4, with positive video duration.');
    encoder=spawn('ffmpeg',['-y','-loglevel','error','-f','image2pipe','-vcodec','png','-r',String(fps),'-i','pipe:0','-an','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',target],{stdio:['pipe','ignore','pipe'],windowsHide:true});
    let failure='';encoder.stderr.on('data',chunk=>failure=(failure+chunk.toString()).slice(0,2000));
    const completed=new Promise((r,j)=>{encoder.on('error',j);encoder.on('close',code=>code===0?r():j(Error('FFmpeg failed: '+failure)));});
    // Attach a handler immediately, even if the encoder exits before frame capture.
    completed.catch(()=>{});encoder.stdin.on('error',()=>{});
    for(let frame=0;frame<Math.ceil(duration*fps);frame++) {
      await page.evaluate(t=>contentEngine.renderAt(t),frame/fps);
      const png=await page.locator('canvas').screenshot();
      if(encoder.exitCode!==null)throw Error('FFmpeg exited during capture.');
      if(!encoder.stdin.write(png))await new Promise((r,j)=>{
        const done=()=>{encoder.stdin.removeListener('error',failed);r();};
        const failed=error=>{encoder.stdin.removeListener('drain',done);j(error);};
        encoder.stdin.once('drain',done);encoder.stdin.once('error',failed);
      });
    }
    encoder.stdin.end();await completed;
  }
  console.log(target);
}finally{if(encoder && encoder.exitCode===null)encoder.kill();await browser?.close();await new Promise(r=>server.close(r));}
