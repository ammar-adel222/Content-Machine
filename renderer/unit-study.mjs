// Appearance study only: approved generated units on an illustrative vertical map.
import {chromium} from 'playwright';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
const [source,target]=process.argv.slice(2);
if(!source||!target)throw Error('Usage: node renderer/unit-study.mjs RESULTS.json OUTPUT.png');
const files=JSON.parse(await readFile(source,'utf8'));
const assets=[];
for(const file of files){
 const result=JSON.parse(await readFile(file,'utf8'));
 if(!result.asset?.review?.recognizable||!result.asset.review.consistent_style||
    !result.asset.review.supported_by_brief||result.asset.review.issues.length)throw Error('Study requires reviewed assets.');
 assets.push(result.asset);
}
if(!assets.length||assets.length>3)throw Error('Study needs 1–3 approved units.');
const moduleText=await readFile(new URL('../war_content/web/symbols.mjs',import.meta.url),'utf8');
await mkdir(dirname(resolve(target)),{recursive:true});
const browser=await chromium.launch({headless:true,args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
 await page.setContent('<style>body{margin:0}</style>');
 await page.addScriptTag({path:fileURLToPath(new URL('./node_modules/pixi.js/dist/pixi.min.js',import.meta.url))});
 await page.evaluate(async({assets,moduleText})=>{
  const {drawUnit}=await import('data:text/javascript;base64,'+btoa(moduleText));
  const {Application,Graphics,Text}=PIXI,app=new Application();
  await app.init({width:1080,height:1920,backgroundColor:0xded9b9,antialias:true,autoStart:false,preserveDrawingBuffer:true});
  document.body.appendChild(app.canvas);
  const terrain=new Graphics();
  for(let i=0;i<9;i++){
   terrain.ellipse(920,750,150+i*80,180+i*110).stroke({color:0x8e997d,width:2,alpha:.3});
   terrain.ellipse(70,1740,120+i*75,80+i*45).stroke({color:0x8e997d,width:2,alpha:.25});
  }
  terrain.moveTo(510,-80).bezierCurveTo(250,500,880,800,600,1120).bezierCurveTo(410,1460,720,1640,540,2000).stroke({color:0xf1e9d5,width:42});
  terrain.moveTo(510,-80).bezierCurveTo(250,500,880,800,600,1120).bezierCurveTo(410,1460,720,1640,540,2000).stroke({color:0x77a6b2,width:27});
  app.stage.addChild(terrain);
  const text=(value,x,y,size=34)=>{const t=new Text({text:value,style:{fontFamily:'Georgia, serif',fontSize:size,fill:0x26383b}});t.position.set(x,y);app.stage.addChild(t);};
  text('UNIT DESIGN STUDY',65,80,48);text('Generated silhouettes · vertical first',65,150,32);
  assets.forEach((asset,index)=>{
   const y=330+index*(1380/assets.length);
   text(asset.design.label,65,y,49);
   [0x477f92,0xb2634e].forEach((color,side)=>{
    const large=drawUnit(asset.design,color,200);large.position.set(220+side*610,y+190);large.rotation=side?Math.PI:0;app.stage.addChild(large);
    for(let i=0;i<6;i++){
     const marker=drawUnit(asset.design,color,90);marker.position.set(140+side*580+(i%3)*108,y+410+Math.floor(i/3)*115);marker.rotation=side?Math.PI:0;app.stage.addChild(marker);
    }
   });
  });
  text('Illustrative terrain · appearance study',65,1800,31);
  text('Groups are symbols, not literal troop counts',65,1850,28);
  app.renderer.render(app.stage);
 },{assets,moduleText});
 await page.locator('canvas').screenshot({path:resolve(target)});
 await page.evaluate(()=>{const source=document.querySelector('canvas'),c=document.createElement('canvas');c.width=360;c.height=640;c.getContext('2d').drawImage(source,0,0,360,640);source.replaceWith(c);});
 await page.setViewportSize({width:360,height:640});
 await page.locator('canvas').screenshot({path:resolve(target.slice(0,-extname(target).length)+'-phone.png')});
}finally{await browser.close();}
