import test from 'node:test';
import assert from 'node:assert/strict';
import {cameraAt,formationOffset,routeSample,unitState,smooth} from '../../war_content/web/motion.mjs';
const force={id:'a',position:{x:0.1,y:0.3}};
const actions=[{kind:'introduce',unit_id:'a',start_sec:1,end_sec:1},
 {kind:'move',unit_id:'a',start_sec:2,end_sec:10,route:[force.position,{x:.8,y:.3}],stagger:.2,formation:'column'},
 {kind:'fade',unit_id:'a',start_sec:12,end_sec:14}];
test('path distance, corners, repeated points and bounded easing',()=>{
 assert.deepEqual(routeSample([{x:0,y:0},{x:0,y:0}],.5),{x:0,y:0,angle:0});
 assert.equal(routeSample([{x:0,y:0},{x:1,y:0},{x:1,y:1}],1).y,1);
 assert.equal(routeSample([{x:0,y:0},{x:1,y:0},{x:1,y:1}],.5).y,0);
 assert.deepEqual(routeSample([{x:.2,y:.3}],0),{x:.2,y:.3,angle:0});
 assert.equal(smooth(-1),0);assert.equal(smooth(2),1);
});
test('introductions, stagger, endpoint, fade and deterministic backwards seeking',()=>{
 assert.equal(unitState(force,actions,0).alpha,0);
 assert.equal(unitState(force,actions,1).alpha,1);
 assert.ok(unitState(force,actions,5,0,3).x>unitState(force,actions,5,2,3).x);
 assert.equal(unitState(force,actions,10).x,.8);
 assert.equal(unitState(force,actions,14).alpha,0);
 const a=unitState(force,actions,5);unitState(force,actions,15);assert.deepEqual(unitState(force,actions,5),a);
});
test('all formations, highlights, engagement and camera interpolation',()=>{
 for(const kind of ['line','column','wedge','dispersed','campaign'])assert.ok(Number.isFinite(formationOffset(kind,2,4).x));
 for(const kind of ['highlight','engage'])assert.ok(unitState(force,[actions[0],{kind,unit_id:'a',start_sec:2,end_sec:8}],5).highlight>0);
 const scenes=[{start:0,end:5,focus:{x:.5,y:.5},view_width:1},{start:5,end:10,focus:{x:.7,y:.6},view_width:.5}];
 assert.equal(cameraAt(scenes,-1).x,.5);assert.equal(cameraAt(scenes,11).x,.7);
 assert.ok(cameraAt(scenes,5.5).width<1 && cameraAt(scenes,5.5).width>.5);
});
