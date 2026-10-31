import {chromium} from 'playwright';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const [source,target]=process.argv.slice(2);
if(!source||!target)throw Error('Usage: node renderer/asset.mjs DESIGN.json PREVIEW.png');
const design=JSON.parse(await readFile(source,'utf8'));
const moduleText=await readFile(new URL('../war_content/web/symbols.mjs',import.meta.url),'utf8');
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage({viewport:{width:1000,height:820},deviceScaleFactor:1});
 await page.setContent('<style>body{margin:0}</style>');
 await page.addScriptTag({path:fileURLToPath(new URL('./node_modules/pixi.js/dist/pixi.min.js',import.meta.url))});
 await page.evaluate(async({design,moduleText})=>{
  const {drawUnit}=await import('data:text/javascript;base64,'+btoa(moduleText));
  const {Application,Text,Graphics}=PIXI,app=new Application();
  await app.init({width:1000,height:820,backgroundColor:0xeee6d1,antialias:true,autoStart:false,preserveDrawingBuffer:true});
  document.body.appendChild(app.canvas);
  const text=(value,x,y,size=20)=>{const t=new Text({text:value,style:{fontFamily:'sans-serif',fontSize:size,fill:0x26383b}});t.position.set(x,y);app.stage.addChild(t);};
  const symbol=(x,y,pixels,color,angle=0)=>{const s=drawUnit(design,color,pixels);s.position.set(x,y);s.rotation=angle;app.stage.addChild(s);};
  text(design.label,28,20,30);text('Large inspection · forward direction RIGHT →',28,66);
  symbol(180,245,260,0x477f92);symbol(430,220,100,0xb2634e);
  [0,Math.PI/2,Math.PI,Math.PI*1.5].forEach((a,i)=>symbol(560+i*110,220,64,0x477f92,a));
  text('24px                32px                40px',530,310);
  [0xe1dbbd,0xa8b495,0xb6b29c].forEach((color,row)=>{
   const y=370+row*105;
   app.stage.addChild(new Graphics().rect(25,y,950,95).fill(color));
   text(['Plain','Forest','Rock / ridge'][row],42,y+12,18);
   [0x477f92,0xb2634e].forEach((team,j)=>[24,32,40].forEach((size,i)=>symbol(565+i*140,y+27+j*43,size,team)));
   [0x477f92,0xb2634e].forEach((team,j)=>{for(let i=0;i<6;i++)symbol(200+(i%3)*40+j*160,y+28+Math.floor(i/3)*39,32,team);});
  });
  text('Actual screen pixels · two army colors · rotation · symbolic groups',28,720);
  text('1080px export shown at 360px: 32px symbol ≈ 11px. Camera scale matters.',28,758,19);
  app.renderer.render(app.stage);
 },{design,moduleText});
 await page.locator('canvas').screenshot({path:resolve(target)});
}finally{await browser.close();}
