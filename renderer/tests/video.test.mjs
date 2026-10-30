import test from 'node:test';
import assert from 'node:assert/strict';
import {videoSize,coverCamera} from '../../war_content/web/video.mjs';
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
