import test from 'node:test';
import assert from 'node:assert/strict';
import {videoSize,coverCamera,captionAt,captionY,captionState,wordLayout} from '../../war_content/web/video.mjs';
import {terrainBounds,terrainPoint} from '../../war_content/web/battlefield.mjs';

test('video format presets and full-frame cameras preserve aspect and stay inside source data',()=>{
 assert.deepEqual(videoSize(),{width:1080,height:1920});assert.deepEqual(videoSize('landscape'),{width:1920,height:1080});
 assert.throws(()=>videoSize('invalid'));
 const bounds={x:-400,y:-500,width:800,height:1000};
 for(const size of [videoSize(),videoSize('landscape')])for(const focus of [{x:0,y:0},{x:-10000,y:10000}]){
  const c=coverCamera(bounds,size.width,size.height,focus);
  assert.ok(bounds.x*c.scale+c.x<=0);assert.ok((bounds.x+bounds.width)*c.scale+c.x>=size.width);
  assert.ok(bounds.y*c.scale+c.y<=0);assert.ok((bounds.y+bounds.height)*c.scale+c.y>=size.height);
 }
});

test('battlefield framing excludes the cutaway edges in both formats',()=>{
 const field={layer:{bounds:{west:0,south:0,east:.1,north:.2}},heights:{columns:2,rows:2,values:[200,230,220,250]},exaggeration:5};
 const bounds=terrainBounds(field);assert.ok(bounds.width>0&&bounds.height>0);
 for(const size of [videoSize(),videoSize('landscape')]){
  const c=coverCamera(bounds,size.width,size.height,terrainPoint(field,.7,.6));
  assert.ok(bounds.x*c.scale+c.x<=0);assert.ok(bounds.y*c.scale+c.y<=0);
  assert.ok((bounds.x+bounds.width)*c.scale+c.x>=size.width);assert.ok((bounds.y+bounds.height)*c.scale+c.y>=size.height);
 }
});


test('short word groups retain the transcript and remain in one platform-safe band',()=>{
 const captions=[{start:1,end:5,text:'one two three four five six seven eight nine ten eleven twelve'}];
 assert.equal(captionAt(captions,0),'');assert.equal(captionAt(captions,1),'one two three four five');
 assert.equal(captionAt(captions,4.5),'eleven twelve');assert.equal(captionAt(captions,5),'');
 for(const height of [1920,1080]){
  const y=captionY(height);assert.ok(y>height*.65&&y+100<height*.85);
  assert.equal(captionY(height,80,[{y},{y:100}]),y);
 }
});


test('active word uses supplied narration times and no word remains active through a long pause',()=>{
 const captions=[{start:0,end:4,text:'Hold the ridge.',words:[{text:'Hold',start:.2,end:.7},{text:'the',start:1,end:1.2},{text:'ridge.',start:2,end:3}]}];
 assert.equal(captionState(captions,0).active,-1);assert.equal(captionState(captions,.4).active,0);
 assert.equal(captionState(captions,1.1).active,1);assert.equal(captionState(captions,1.7).active,-1);
 assert.equal(captionState(captions,2.5).active,2);assert.equal(captionState(captions,4).text,'');
});

test('caption words wrap inside the fixed safe width with centered rows',()=>{
 const layout=wordLayout([100,110,140,90],260);
 assert.equal(layout[0].y,0);assert.equal(layout[1].y,0);assert.equal(layout[2].y,51);
 assert.ok(layout.every((p,i)=>p.x>=-130&&p.x+[100,110,140,90][i]<=130));
});
