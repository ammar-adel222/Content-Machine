// Ground-truth image fixtures are rendered without sending scene data to the models.
import {chromium} from 'playwright';
import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
const root=resolve(process.argv[2]??'output/benchmarks/probes');await mkdir(root,{recursive:true});
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1000,height:700},deviceScaleFactor:1});
 for(const dirty of [false,true]) {
  await page.setContent('<canvas width="1000" height="700"></canvas>');
  await page.evaluate(dirty=>{
   const c=document.querySelector('canvas').getContext('2d');
   c.fillStyle='#ded9b9';c.fillRect(0,0,1000,700);
   c.fillStyle='#93b8c7';c.fillRect(420,0,160,700);
   c.font='bold 28px sans-serif';c.fillStyle='#223638';c.fillText('MAP INSPECTION',35,50);
   c.font='24px sans-serif';c.fillText('EAST RIDGE',dirty?310:650,160);c.fillText('RIVER CROSSING',dirty?340:30,dirty?170:220);
   if(!dirty){c.fillStyle='#796d55';c.fillRect(395,330,210,38);c.strokeStyle='#29363b';c.lineWidth=3;c.strokeRect(395,330,210,38);}
   function tank(x,y,color){c.fillStyle='#26383b';c.fillRect(x-39,y-32,78,16);c.fillRect(x-39,y+16,78,16);c.fillStyle=color;c.fillRect(x-32,y-20,65,40);c.beginPath();c.arc(x,y,18,0,Math.PI*2);c.fill();c.strokeStyle='#26383b';c.lineWidth=3;c.stroke();c.fillRect(x,y-5,68,10);}
   tank(dirty?495:260,dirty?300:300,'#bb5d4b');tank(740,440,'#3b7293');
   c.fillStyle='#26383b';c.font='20px sans-serif';c.fillText('Symbolic units · top-down view',35,660);
  },dirty);
  await page.locator('canvas').screenshot({path:resolve(root,dirty?'problem.png':'control.png')});
 }
}finally{await browser.close();}
console.log(root);
