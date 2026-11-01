// Pure, deterministic choreography: renders identically when seeking backwards.
export const clamp = (v,a=0,b=1) => Math.max(a,Math.min(b,v));
export const smooth = v => {const t=clamp(v);return t*t*(3-2*t);};
export function routeSample(points,progress) {
  // Match the director's normalized-distance interpolation exactly.
  const lengths=points.slice(1).map((b,i)=>Math.hypot(b.x-points[i].x,b.y-points[i].y));
  let remaining=lengths.reduce((a,b)=>a+b,0)*clamp(progress);
  for(let i=0;i<lengths.length;i++) {
    if(remaining<=lengths[i] || i===lengths.length-1) {
      const a=points[i], b=points[i+1], t=lengths[i] ? clamp(remaining/lengths[i]):1;
      return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,angle:Math.atan2((b.y-a.y)*16/9,b.x-a.x)};
    }
    remaining-=lengths[i];
  }
  return {...points[0],angle:0};
}
// Angles take the short route across -pi/pi, including deterministic U-turns.
export const angleDelta=(a,b)=>Math.atan2(Math.sin(b-a),Math.cos(b-a));
export const mixAngle=(a,b,t)=>a+angleDelta(a,b)*clamp(t);
const aspect=16/9;
const routeCache=new WeakMap();
function routeInfo(points){
 if(!routeCache.has(points)){
  const segments=[];let total=0;
  for(let i=1;i<points.length;i++){
   const a=points[i-1],b=points[i],length=Math.hypot(b.x-a.x,(b.y-a.y)*aspect);
   if(length>1e-9){segments.push({a,b,length,start:total,angle:Math.atan2((b.y-a.y)*aspect,b.x-a.x)});total+=length;}
  }
  routeCache.set(points,{segments,total});
 }
 return routeCache.get(points);
}
function travelFrame(points,progress,trail=0){
 const {segments,total}=routeInfo(points);
 if(!segments.length)return {...points[0],angle:0};
 const distance=clamp(progress)*total+trail;
 const segment=segments.find(s=>distance<=s.start+s.length)??segments.at(-1);
 const t=(distance-segment.start)/segment.length;
 const p={x:segment.a.x+(segment.b.x-segment.a.x)*t,y:segment.a.y+(segment.b.y-segment.a.y)*t,angle:segment.angle};
 // Rotate through corners without rounding the authored route into nearby terrain.
 for(let i=1;i<segments.length;i++){
  const before=segments[i-1],after=segments[i],radius=Math.min(.055,before.length*.4,after.length*.4);
  if(distance>=after.start-radius&&distance<=after.start+radius){p.angle=mixAngle(before.angle,after.angle,smooth((distance-after.start+radius)/(2*radius)));break;}
 }
 return p;
}
export function formationOffset(kind,index,count) {
 const center=index-(count-1)/2,spacing=.045*Math.min(1,8/Math.max(1,count));
 if(kind==='column')return {x:-index*.022*Math.min(1,8/Math.max(1,count)),y:0};
 if(kind==='wedge')return {x:-Math.abs(center)*spacing*.6,y:center*spacing};
 if(kind==='dispersed')return {x:(index%3-1)*.028,y:(Math.floor(index/3)-(Math.ceil(count/3)-1)/2)*spacing};
 if(kind==='campaign')return {x:0,y:0};
 // Two compact ranks keep a force recognizable as a group, rather than a string.
 const frontage=Math.ceil(count/2),rank=Math.floor(index/frontage),ranks=Math.ceil(count/frontage);
 return {x:-(rank-(ranks-1)/2)*.022,y:(index%frontage-(frontage-1)/2)*spacing};
}
export function marchProgress(progress,index) {
 const p=clamp(progress);
 // Bounded monotone variation: separate cadence, identical authored endpoints.
 return p+.012*Math.sin(Math.PI*p)**2*Math.sin(2*Math.PI*p+index*2.399);
}
// Short speed ramps with a steady marching middle, rather than constant easing.
export function travelEase(value,ramp=.12){
 const t=clamp(value),r=clamp(ramp,.001,.49),speed=1/(1-r);
 if(t<r)return speed*t*t/(2*r);
 if(t>1-r)return 1-speed*(1-t)*(1-t)/(2*r);
 return speed*(t-r/2);
}
function rotateOffset(offset,angle){
 const c=Math.cos(angle),s=Math.sin(angle);
 return {x:offset.x*c-offset.y*s,y:(offset.x*s+offset.y*c)/aspect};
}
function formationPoint(route,progress,formation,index,count){
 const offset=formationOffset(formation,index,count),p=travelFrame(route,progress,offset.x);
 const lateral=rotateOffset({x:0,y:offset.y},p.angle);
 return {x:p.x+lateral.x,y:p.y+lateral.y,angle:p.angle};
}
function formationCenter(action,progress,count){
 const center=travelFrame(action.route,progress),mean={x:0,y:0};
 for(let i=0;i<count;i++){const p=formationPoint(action.route,progress,action.formation,i,count);mean.x+=(p.x-center.x)/count;mean.y+=(p.y-center.y)/count;}
 return mean;
}
function deployOffset(from,to,oldCenter,newCenter,t){
 // Rotate ranks around the group center instead of pulling them through one
 // another when a trailing column opens into a transverse line.
 const a={x:from.x-oldCenter.x,y:(from.y-oldCenter.y)*aspect},b={x:to.x-newCenter.x,y:(to.y-newCenter.y)*aspect};
 const radius=Math.hypot(a.x,a.y)*(1-t)+Math.hypot(b.x,b.y)*t;
 const angle=mixAngle(Math.atan2(a.y,a.x),Math.atan2(b.y,b.x),t);
 return {x:oldCenter.x*(1-t)+newCenter.x*t+Math.cos(angle)*radius,
  y:oldCenter.y*(1-t)+newCenter.y*t+Math.sin(angle)*radius/aspect};
}
export function motionPose(kind,time,index,moving,seed=0){
 const phase=time*(kind==='cavalry'?3.2:2.2)*Math.PI*2+index*2.399+seed;
 const mobile=kind==='infantry'||kind==='cavalry';
 if(!mobile||moving<=0)return {bob:0,roll:0};
 return {bob:Math.sin(phase)*1.8*moving,roll:Math.sin(phase/2)*.025*moving};
}
export function unitState(force,actions,time,index=0,count=1) {
 const intro=actions.find(a=>a.kind==='introduce'&&a.unit_id===force.id);
 const initial=formationOffset('line',index,count);
 let center={...force.position},offset=rotateOffset(initial,0),angle=0,formation='line',moving=0,alpha=1,highlight=0;
 let previousMove=null;
 if(!intro||time<intro.start_sec)return {...center,angle,formation,moving,alpha:0,highlight,bob:0,roll:0};
 alpha=smooth((time-intro.start_sec)/.3);
 for(const a of actions.filter(a=>a.unit_id===force.id&&a.kind!=='introduce').sort((a,b)=>a.start_sec-b.start_sec)){
  if(time<a.start_sec)continue;
  const span=a.end_sec-a.start_sec,t=span>0?clamp((time-a.start_sec)/span):1;
  if(a.kind==='move'||a.kind==='withdraw'){
   if(!a.route?.length)continue;
   // Bounded independent departures; every actor still stops within the cue.
   const delay=Math.min((a.stagger??.15)*span,1.2)*index/Math.max(1,count-1);
   const elapsed=time-a.start_sec-delay,duration=Math.max(.001,span-delay);
   const progress=marchProgress(travelEase(elapsed/duration),index),raw=travelFrame(a.route,progress);
   const target=formationPoint(a.route,progress,a.formation,index,count);
   const blend=smooth((time-a.start_sec)/Math.min(.9,span*.3||.001));
   const before=previousMove?formationCenter(previousMove,1,count):{x:0,y:0};
   const after=formationCenter(a,progress,count);
   offset=deployOffset(offset,{x:target.x-raw.x,y:target.y-raw.y},before,after,blend);
   center=raw;angle=mixAngle(angle,target.angle,blend);formation=a.formation;
   moving=smooth(elapsed/.4)*smooth((duration-elapsed)/.4);
   previousMove=a;
  }
  if(a.kind==='fade')alpha*=1-smooth(t);
  if(a.kind==='highlight'&&time<=a.end_sec)highlight=Math.max(highlight,Math.sin(Math.PI*t));
  if(a.kind==='engage'&&time<=a.end_sec)highlight=Math.max(highlight,.8*Math.sin(Math.PI*t));
 }
 const seed=[...force.id].reduce((n,c)=>n+c.charCodeAt(0),0);
 return {x:center.x+offset.x,y:center.y+offset.y,angle,formation,moving,alpha,highlight,...motionPose(force.kind,time,index,moving,seed)};
}
export function engagementStates(forces,actions,time,scale='tactical') {
 const units=new Map(forces.map(force=>[force.id,force])),result=[];
 for(const action of actions){
  if(action.kind!=='engage'||time<action.start_sec||time>=action.end_sec)continue;
  const actor=units.get(action.unit_id),target=units.get(action.target_id);
  if(!actor||!target||actor.side===target.side)continue;
  const a=unitState(actor,actions,time),b=unitState(target,actions,time);
  if(a.alpha<=.1||b.alpha<=.1)continue;
  if(scale==='tactical'&&['infantry','cavalry','army'].includes(actor.kind)&&Math.hypot(a.x-b.x,a.y-b.y)>.080001)continue;
  const elapsed=time-action.start_sec,remaining=action.end_sec-time;
  result.push({id:action.id,actor:actor.side,target:target.side,x:(a.x+b.x)/2,y:(a.y+b.y)/2,
   strength:smooth(elapsed/.08)*smooth(remaining/.15),burst:Math.max(0,1-(elapsed%.65)/.3)});
 }
 return result;
}
export function movementTrails(forces,actions,time) {
 const result=[];
 for(const force of forces){
  const state=unitState(force,actions,time);if(state.alpha<=.1)continue;
  let points=[],latest=null;
  for(const action of actions.filter(a=>a.unit_id===force.id&&['move','withdraw'].includes(a.kind)).sort((a,b)=>a.start_sec-b.start_sec)){
   if(time<=action.start_sec)break;
   if(action.route?.length<2||action.end_sec<=action.start_sec)continue;
   const progress=marchProgress(travelEase((time-action.start_sec)/(action.end_sec-action.start_sec)),0);
   const route=action.route,info=routeInfo(route);let distance=info.total*progress,part=[route[0]];
   for(const segment of info.segments){
    if(distance>=segment.length){part.push(segment.b);distance-=segment.length;}
    else{const f=distance/segment.length;part.push({x:segment.a.x+(segment.b.x-segment.a.x)*f,y:segment.a.y+(segment.b.y-segment.a.y)*f});break;}
   }
   const last=points.at(-1);
   if(last&&Math.hypot(last.x-route[0].x,last.y-route[0].y)<1e-6)points.push(...part.slice(1));else points=part;
   latest=action;
  }
  if(!latest||time>=latest.end_sec+2||points.length<2)continue;
  const alpha=smooth((time-latest.start_sec)/.35)*(1-clamp((time-latest.end_sec)/2));
  result.push({id:force.id,side:force.side,points,alpha});
 }
 return result;
}
export function dashedSegments(points,dash=10,gap=7) {
 if(!Number.isFinite(dash)||!Number.isFinite(gap)||dash<=0||gap<=0)throw Error('Dash and gap lengths must be positive.');
 const output=[];let phase=0;
 for(let i=1;i<points.length;i++){
  const a=points[i-1],b=points[i],length=Math.hypot(b.x-a.x,b.y-a.y);if(length<1e-8)continue;
  let distance=0;
  while(distance<length-1e-8){
   const drawing=phase<dash,remaining=(drawing?dash:dash+gap)-phase;
   const step=Math.min(length-distance,remaining);
   if(drawing&&step>1e-8)output.push([{x:a.x+(b.x-a.x)*distance/length,y:a.y+(b.y-a.y)*distance/length},
    {x:a.x+(b.x-a.x)*(distance+step)/length,y:a.y+(b.y-a.y)*(distance+step)/length}]);
   distance+=step;phase=(phase+step)%(dash+gap);
  }
 }
 return output;
}
export const sceneIndex=(scenes,time)=>Math.max(0,scenes.findLastIndex(scene=>scene.start<=time));
export function cameraAt(scenes,time,pushIn=.08) {
 const index=sceneIndex(scenes,time);
 const current=scenes[index],previous=scenes[Math.max(0,index-1)];
 const progress=clamp((time-current.start)/Math.max(.001,current.end-current.start));
 const width=current.view_width/(1+pushIn*progress);
 const t=index===0?1:smooth((time-current.start)/Math.min(1.3,(current.end-current.start)/3));
 const previousWidth=previous.view_width/(1+pushIn);
 return {x:previous.focus.x+(current.focus.x-previous.focus.x)*t,y:previous.focus.y+(current.focus.y-previous.focus.y)*t,
  width:previousWidth+(width-previousWidth)*t,scene:current};
}
