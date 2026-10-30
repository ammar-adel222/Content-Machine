import {chromium} from 'playwright';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
const input=resolve(process.argv[2]??'output/benchmarks/visual/results.json');
const target=resolve(process.argv[3]??'output/benchmarks/visual/gallery.png');
const results=JSON.parse(await readFile(input,'utf8')).results.filter(r=>!r.skip).sort((a,b)=>(a.provider+a.model).localeCompare(b.provider+b.model));
const moduleText=await readFile(new URL('../war_content/web/symbols.mjs',import.meta.url),'utf8');
await mkdir(resolve(target,'..'),{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage({viewport:{width:1200,height:200+results.length*240},deviceScaleFactor:1});
 await page.setContent('<style>body{margin:0}</style>');
 await page.addScriptTag({path:resolve('renderer/node_modules/pixi.js/dist/pixi.min.js')});
 await page.evaluate(async({results,moduleText})=>{
  const {drawDesign}=await import('data:text/javascript;base64,'+btoa(moduleText));
  const {Application,Graphics,Text}=PIXI;
  const app=new Application();await app.init({width:1200,height:200+results.length*240,backgroundColor:0xeee6d1,antialias:true,autoStart:false,preserveDrawingBuffer:true});
  document.body.appendChild(app.canvas);
  function text(value,x,y,size=24,color=0x26383b){const t=new Text({text:value,style:{fontFamily:'system-ui',fontSize:size,fill:color}});t.position.set(x,y);app.stage.addChild(t);}
  text('VISUAL DESIGN COMPARISON',40,30,36);text('Same briefs · first attempt · shared PixiJS drawing language',40,83,22);
  text('TANK',670,145,22);text('CLIFF MOTIF',935,145,22);
  results.forEach((r,i)=>{
   const y=200+i*240;
   app.stage.addChild(new Graphics().rect(30,y,1140,225).fill(i%2?0xe3ddc7:0xeae2cc));
   text(r.model.replace(':free',''),50,y+30,21);text(r.provider,50,y+65,18,0x6a796b);
   text('Small map scale →',385,y+148,16,0x6a796b);
   ['tank','cliff'].forEach((concept,j)=>{
    const x=710+j*270,task=r.designs.find(d=>d.concept===concept);
    if(task?.status==='valid'){
     const big=drawDesign(task.design,0x527d87,75);big.position.set(x,y+105);app.stage.addChild(big);
     const small=drawDesign(task.design,0x527d87,16);small.position.set(x,y+185);app.stage.addChild(small);
    }else text('No valid design',x-80,y+100,18,0xa05e4d);
   });
  });
  app.renderer.render(app.stage);
 },{results,moduleText});
 await page.locator('canvas').screenshot({path:target});
}finally{await browser.close();}
console.log(target);
