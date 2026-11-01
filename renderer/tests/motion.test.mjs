import test from 'node:test';
import assert from 'node:assert/strict';
import {angleDelta,mixAngle,motionPose,travelEase,cameraAt,formationOffset,routeSample,unitState,smooth,marchProgress,engagementStates,movementTrails,dashedSegments,sceneIndex} from '../../war_content/web/motion.mjs';
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
 assert.equal(unitState(force,actions,1).alpha,0);
 assert.equal(unitState(force,actions,1.3).alpha,1);
 assert.ok(unitState(force,actions,5,0,3).x>unitState(force,actions,5,2,3).x);
 assert.equal(unitState(force,actions,10).x,.8);
 assert.equal(unitState(force,actions,14).alpha,0);
 const a=unitState(force,actions,5);unitState(force,actions,15);assert.deepEqual(unitState(force,actions,5),a);
});

test('columns follow a route bend individually, without cutting the corner as one rigid block',()=>{
 const f={id:'b',kind:'infantry',position:{x:.2,y:.8}};
 const a=[{kind:'introduce',unit_id:'b',start_sec:0},
  {kind:'move',unit_id:'b',start_sec:0,end_sec:10,route:[f.position,{x:.65,y:.8},{x:.65,y:.3}],stagger:.12,formation:'column'}];
 const head=unitState(f,a,4.4,0,3),tail=unitState(f,a,4.4,2,3);
 assert.ok(head.y<.8);assert.ok(Math.abs(head.x-.65)<1e-8);
 assert.ok(tail.x<.65);assert.ok(Math.abs(tail.y-.8)<1e-8);
 for(let time=1;time<=10;time+=.1){
  const s=unitState(f,a,time,0,1);
  assert.ok(Math.abs(s.x-.65)<1e-8||Math.abs(s.y-.8)<1e-8);
 }
});

test('formation changes and turn boundaries remain continuous for every actor',()=>{
 const f={id:'turn',position:{x:.2,y:.7}},a=[{kind:'introduce',unit_id:'turn',start_sec:0},
  {kind:'move',unit_id:'turn',start_sec:1,end_sec:6,route:[f.position,{x:.6,y:.7},{x:.6,y:.5}],stagger:.2,formation:'column'},
  {kind:'move',unit_id:'turn',start_sec:6,end_sec:11,route:[{x:.6,y:.5},{x:.4,y:.25}],stagger:.2,formation:'line'}];
 for(let index=0;index<6;index++){
  const before=unitState(f,a,6-1e-5,index,6),after=unitState(f,a,6+1e-5,index,6);
  assert.ok(Math.hypot(after.x-before.x,after.y-before.y)<1e-6);
  assert.ok(Math.abs(angleDelta(before.angle,after.angle))<1e-5);
  let previous=unitState(f,a,1,index,6);
  for(let t=1.02;t<11;t+=.02){
   const s=unitState(f,a,t,index,6);
   assert.ok(Math.abs(angleDelta(previous.angle,s.angle))<.25);
   previous=s;
  }
 }
 assert.ok(Math.abs(angleDelta(Math.PI-.1,-Math.PI+.1)-.2)<1e-8);
 assert.ok(Math.abs(mixAngle(Math.PI-.1,-Math.PI+.1,.5)-Math.PI)<1e-8);
});

test('speed ramps stop exactly, gait phases differ, and vehicles do not bounce',()=>{
 assert.equal(travelEase(-1),0);assert.equal(travelEase(2),1);assert.equal(travelEase(.5),.5);
 let previous=0;for(let t=0;t<=1;t+=.01){assert.ok(travelEase(t)>=previous);previous=travelEase(t);}
 assert.ok(Math.abs(travelEase(.00001)/.00001)<.001);
 assert.deepEqual(motionPose('artillery',3,0,1),{bob:0,roll:0});
 assert.deepEqual(motionPose('infantry',3,0,0),{bob:0,roll:0});
 assert.notEqual(motionPose('infantry',3,0,1).bob,motionPose('infantry',3,1,1).bob);
 const stop=unitState(force,actions,10),hold=unitState(force,actions,11);
 assert.equal(stop.x,hold.x);assert.equal(stop.y,hold.y);assert.equal(stop.angle,hold.angle);
 assert.equal(stop.moving,0);assert.equal(stop.bob,0);
 const zero=[actions[0],{kind:'move',unit_id:'a',start_sec:2,end_sec:2,route:[force.position,force.position],formation:'line',stagger:0}];
 assert.ok(Number.isFinite(unitState(force,zero,3).angle));
});

test('column-to-line deployment keeps neighboring ranks separated instead of crossing',()=>{
 const f={id:'deploy',position:{x:.58,y:.68}},a=[{kind:'introduce',unit_id:'deploy',start_sec:0},
  {kind:'move',unit_id:'deploy',start_sec:1,end_sec:6,route:[f.position,{x:.58,y:.61},{x:.70,y:.54},{x:.70,y:.45}],stagger:.2,formation:'column'},
  {kind:'move',unit_id:'deploy',start_sec:6,end_sec:10,route:[{x:.70,y:.45},{x:.64,y:.34}],stagger:.2,formation:'line'}];
 for(let time=.3;time<11;time+=.025){
  const positions=Array.from({length:4},(_,i)=>unitState(f,a,time,i,4));
  for(let i=0;i<4;i++)for(let j=i+1;j<4;j++)
   assert.ok(Math.hypot(positions[i].x-positions[j].x,(positions[i].y-positions[j].y)*16/9)>.012);
 }
});
test('all formations, highlights, engagement and camera interpolation',()=>{
 for(const kind of ['line','column','wedge','dispersed','campaign'])assert.ok(Number.isFinite(formationOffset(kind,2,4).x));
 for(const kind of ['highlight','engage'])assert.ok(unitState(force,[actions[0],{kind,unit_id:'a',start_sec:2,end_sec:8}],5).highlight>0);
 const scenes=[{start:0,end:5,focus:{x:.5,y:.5},view_width:1},{start:5,end:10,focus:{x:.7,y:.6},view_width:.5}];
 assert.equal(cameraAt(scenes,-1).x,.5);assert.equal(cameraAt(scenes,11).x,.7);
 assert.ok(cameraAt(scenes,5.5).width<1 && cameraAt(scenes,5.5).width>.5);
});


test('six subgroups form compact ranks and a shorter column rather than a long loose string',()=>{
 const ranks=Array.from({length:6},(_,i)=>formationOffset('line',i,6));
 assert.equal(new Set(ranks.map(p=>p.x)).size,2);assert.equal(new Set(ranks.map(p=>p.y)).size,3);
 assert.ok(Math.max(...ranks.map(p=>p.y))-Math.min(...ranks.map(p=>p.y))<.1);
 const column=Array.from({length:6},(_,i)=>formationOffset('column',i,6));
 assert.ok(Math.abs(column.at(-1).x-column[0].x)<.12);
});

test('independent marching progress remains monotone and reaches the authored endpoints',()=>{
 const mid=new Set();
 for(let i=0;i<8;i++){
  assert.equal(marchProgress(0,i),0);assert.equal(marchProgress(1,i),1);mid.add(marchProgress(.35,i));
  let previous=0;for(let p=0;p<=1;p+=.005){const next=marchProgress(p,i);assert.ok(next>=previous);assert.ok(next>=0&&next<=1);previous=next;}
 }
 assert.equal(mid.size,8);
});

test('clash indicators require live opposing forces in contact and share engagement boundaries',()=>{
 const forces=[{id:'left',side:'Blue',kind:'infantry',position:{x:.4,y:.5}},{id:'right',side:'Red',kind:'infantry',position:{x:.45,y:.5}}];
 const rows=forces.map(f=>({kind:'introduce',unit_id:f.id,start_sec:0}));
 const contact={id:'fight',kind:'engage',unit_id:'left',target_id:'right',start_sec:2,end_sec:4};rows.push(contact);
 assert.equal(engagementStates(forces,rows,1).length,0);assert.equal(engagementStates(forces,rows,4).length,0);
 const current=engagementStates(forces,rows,2.2);assert.equal(current.length,1);assert.equal(current[0].x,.42500000000000004);
 assert.deepEqual(current,engagementStates(forces,rows,2.2));
 assert.equal(engagementStates([forces[0],{...forces[1],side:'Blue'}],rows,2.2).length,0);
 assert.equal(engagementStates([forces[0],{...forces[1],position:{x:.9,y:.9}}],rows,2.2).length,0);
 assert.equal(engagementStates(forces,[...rows,{kind:'fade',unit_id:'right',start_sec:.2,end_sec:1}],2.2).length,0);
 assert.equal(engagementStates(forces,[{...contact,target_id:'unknown'}],2.2).length,0);
});


test('each static sector gets a continuous eight-percent push with no cut at its transition',()=>{
 const scenes=[{start:0,end:10,focus:{x:.5,y:.5},view_width:1},{start:10.2,end:20,focus:{x:.6,y:.6},view_width:.8},{start:21,end:30,focus:{x:.3,y:.3},view_width:.6}];
 const early=cameraAt(scenes,2),later=cameraAt(scenes,8);
 assert.ok(later.width<early.width);assert.ok(Math.abs(cameraAt(scenes,10).width-1/1.08)<1e-9);
 assert.equal(sceneIndex(scenes,10.1),0);assert.equal(cameraAt(scenes,10.1).scene,scenes[0]);
 assert.ok(Math.abs(cameraAt(scenes,10.2).width-cameraAt(scenes,10.2-1e-6).width)<1e-6);
 assert.ok(cameraAt(scenes,29).width<cameraAt(scenes,23).width);
 assert.equal(cameraAt(scenes,8,0).width,1);
});

test('trails stop at traveled corners, retain their origin and fade after a halt',()=>{
 const f={id:'a',side:'Blue',kind:'infantry',position:{x:0,y:0}},rows=[{kind:'introduce',unit_id:'a',start_sec:0},
 {kind:'move',unit_id:'a',start_sec:1,end_sec:5,formation:'column',route:[{x:0,y:0},{x:.5,y:0},{x:.5,y:.5}]},
 {kind:'move',unit_id:'a',start_sec:6,end_sec:10,formation:'line',route:[{x:.5,y:.5},{x:.8,y:.5}]}];
 assert.deepEqual(movementTrails([f],rows,.5),[]);
 const during=movementTrails([f],rows,4)[0];assert.deepEqual(during.points[0],f.position);
 assert.ok(during.points.at(-1).y<.5);assert.ok(during.points.every(p=>p.y===0||p.x===.5));
 assert.deepEqual(movementTrails([f],rows,12),[]);
 const second=movementTrails([f],rows,8)[0];assert.deepEqual(second.points[0],f.position);
 assert.deepEqual(second,movementTrails([f],rows,8)[0]);
 const broken=[...rows.slice(0,2),{...rows[2],route:[{x:.7,y:.7},{x:.8,y:.8}]}];
 assert.deepEqual(movementTrails([f],broken,8)[0].points[0],{x:.7,y:.7});
 const dashes=dashedSegments([{x:0,y:0},{x:10,y:0},{x:10,y:20}],6,4);
 assert.ok(dashes.length>1);assert.ok(dashes.every(([a,b])=>a.x===b.x||a.y===b.y));
 assert.throws(()=>dashedSegments([],0,4));assert.throws(()=>dashedSegments([],4,-1));
});
