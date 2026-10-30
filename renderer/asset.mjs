import {chromium} from 'playwright';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const [source,target]=process.argv.slice(2);
if(!source||!target)throw Error('Usage: node renderer/asset.mjs DESIGN.json PREVIEW.png');
const design=JSON.parse(await readFile(source,'utf8'));
const moduleText=await readFile(new URL('../war_content/web/symbols.mjs',import.meta.url),'utf8');
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
 const page=await browser.newPage({viewport:{width:700,height:400},deviceScaleFactor:1});
 await page.setContent('<style>body{margin:0}</style>');
 await page.addScriptTag({path:resolve('renderer/node_modules/pixi.js/dist/pixi.min.js')});
 await page.evaluate(async({design,moduleText})=>{
  const {drawDesign}=await import('data:text/javascript;base64,'+btoa(moduleText));
  const {Application,Text}=PIXI,app=new Application();
  await app.init({width:700,height:400,backgroundColor:0xeee6d1,antialias:true,autoStart:false,preserveDrawingBuffer:true});
  document.body.appendChild(app.canvas);
  for(const [size,x] of [[120,190],[16,500]]){const shape=drawDesign(design,0x527d87,size);shape.position.set(x,200);app.stage.addChild(shape);}
  for(const [text,x,y] of [['Large inspection',70,25],['32px map symbol',420,25],['Unit forward direction: RIGHT →',70,350]]){
    const label=new Text({text,style:{fontFamily:'sans-serif',fontSize:22,fill:0x26383b}});label.position.set(x,y);app.stage.addChild(label);
  }
  app.renderer.render(app.stage);
 },{design,moduleText});
 await page.locator('canvas').screenshot({path:resolve(target)});
}finally{await browser.close();}
