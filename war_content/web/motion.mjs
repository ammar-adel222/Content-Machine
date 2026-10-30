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
export function formationOffset(kind,index,count) {
  const center=index-(count-1)/2;
  if(kind==='column') return {x:-index*0.021,y:0};
  if(kind==='wedge') return {x:-Math.abs(center)*0.019,y:center*0.018};
  if(kind==='dispersed') return {x:(index%3-1)*0.026,y:(Math.floor(index/3)-(Math.ceil(count/3)-1)/2)*0.023};
  if(kind==='campaign') return {x:0,y:0};
  return {x:0,y:center*0.022};
}
export function unitState(force,actions,time,index=0,count=1) {
  let result={...force.position,angle:0,alpha:1,highlight:0,formation:'line'};
  let intro=actions.find(a=>a.kind==='introduce' && a.unit_id===force.id);
  if(!intro || time<intro.start_sec) return {...result,alpha:0};
  let formation='line';
  for(const a of actions.filter(a=>a.unit_id===force.id && a.kind!=='introduce').sort((a,b)=>a.start_sec-b.start_sec)) {
    if(time<a.start_sec) continue;
    const span=a.end_sec-a.start_sec;
    let t=clamp((time-a.start_sec)/span);
    if(a.kind==='move' || a.kind==='withdraw') {
      // All followers finish at the authored endpoint, despite staggered departure.
      const delay=(index/Math.max(1,count-1))*a.stagger;
      t=smooth((t-delay)/(1-delay));
      result={...result,...routeSample(a.route,t)};
      formation=a.formation;
    }
    if(a.kind==='fade') result.alpha=1-smooth(t);
    if(a.kind==='highlight' && time<=a.end_sec) result.highlight=Math.sin(Math.PI*t);
    if(a.kind==='engage' && time<=a.end_sec) result.highlight=0.8;
  }
  const offset=formationOffset(formation,index,count), c=Math.cos(result.angle),s=Math.sin(result.angle);
  return {...result,x:result.x+offset.x*c-offset.y*s,y:result.y+(offset.x*s+offset.y*c)*9/16,formation};
}
export function cameraAt(scenes,time) {
  let index=scenes.findIndex(s=>time>=s.start && time<s.end);
  if(index<0) index=time<scenes[0].start?0:scenes.length-1;
  const current=scenes[index], previous=scenes[Math.max(0,index-1)];
  const t=smooth((time-current.start)/Math.min(1.3,(current.end-current.start)/3));
  return {x:previous.focus.x+(current.focus.x-previous.focus.x)*t,y:previous.focus.y+(current.focus.y-previous.focus.y)*t,
          width:previous.view_width+(current.view_width-previous.view_width)*t,scene:current};
}
