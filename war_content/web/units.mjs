export const unitRotation=(presentation,angle)=>presentation==='upright'?0:angle;
import {unitState,engagementStates,movementTrails,dashedSegments} from './motion.mjs';
import {drawUnit,factionRoster} from './symbols.mjs';

// Shared presentation of deterministic choreography on flat or projected terrain.
export function createUnits(data,world,project,worldScale=()=>1) {
 const {Container,Graphics}=globalThis.PIXI;
 const factions=new Map(factionRoster(data.blueprint.forces).map(f=>[f.id,f.color])),actors=[];
 const trails=new Graphics();trails.label='movement-trails';world.addChildAt(trails,Math.min(1,world.children.length));
 const definitions=new Map(data.blueprint.scenes.flatMap(s=>s.actions.map(a=>[a.id,a])));
 const actions=data.timeline.map(row=>({...definitions.get(row.action_id),...row}));
 for(const force of data.blueprint.forces){
  const count=data.blueprint.scale==='campaign'?1:force.subgroups,color=factions.get(force.side);
  for(let index=0;index<count;index++){
   const holder=new Container(),halo=new Graphics().poly([-12,-43,0,-35,12,-43],false).stroke({color:0xb88a47,width:4});
   holder.label=`unit:${force.id}:${index}`;
   const body=drawUnit(data.assets[data.bindings.unit[force.id]],color,count===1?80:52);
   holder.addChild(halo,body);world.addChild(holder);actors.push({force,index,count,holder,halo,body,presentation:data.unit_presentations?.[force.id]??'heading'});
  }
 }
 const clashes=new Map();
 for(const action of actions.filter(a=>a.kind==='engage')){
  const marker=new Container(),rays=new Graphics(),ink=new Graphics(),label=new globalThis.PIXI.Text({text:'CLASH',style:{fontFamily:'sans-serif',fontSize:18,fontWeight:'bold',fill:0x26383b,stroke:{color:0xf8f0dd,width:4}}});
  marker.label='clash:'+action.id;
  for(let i=0;i<8;i++){const angle=i*Math.PI/4;rays.moveTo(Math.cos(angle)*23,Math.sin(angle)*23).lineTo(Math.cos(angle)*36,Math.sin(angle)*36);}
  rays.stroke({color:0xb88a47,width:4});
  ink.moveTo(-19,20).lineTo(19,-20).moveTo(19,20).lineTo(-19,-20).stroke({color:0x26383b,width:9});
  ink.moveTo(-19,20).lineTo(19,-20).moveTo(19,20).lineTo(-19,-20).stroke({color:0xf8f0dd,width:4});
  ink.moveTo(-23,10).lineTo(-9,23).moveTo(23,10).lineTo(9,23).stroke({color:0xb88a47,width:5});
  label.anchor.set(.5,1);label.position.set(0,-41);marker.addChild(rays,ink,label);marker.visible=false;world.addChild(marker);
  clashes.set(action.id,{marker,rays});
 }
 let activeEngagements=[];
 const render=time=>{
  const visible=[];trails.clear();
  if(data.presentation?.movement_trails!==false){
   const scale=Math.max(.001,worldScale());
   for(const trail of movementTrails(data.blueprint.forces,actions,time)){
    for(const [a,b] of dashedSegments(trail.points.map(project),10/scale,7/scale))trails.moveTo(a.x,a.y).lineTo(b.x,b.y);
    trails.stroke({color:factions.get(trail.side),width:2.5/scale,alpha:.28*trail.alpha,cap:'round'});
   }
  }

  for(const actor of actors){
   const {force,index,count,holder,body,halo}=actor,state=unitState(force,actions,time,index,count),p=project(state);
   const ahead=project({x:state.x+Math.cos(state.angle)*.001,y:state.y+Math.sin(state.angle)*.001*9/16});
   holder.position.set(p.x,p.y);holder.rotation=unitRotation(actor.presentation,Math.atan2(ahead.y-p.y,ahead.x-p.x));
   holder.alpha=state.alpha;holder.visible=state.alpha>0;holder.scale.set(1/Math.max(.001,worldScale()));
   body.position.y=state.bob;body.rotation=actor.presentation==='upright'?0:state.roll;halo.alpha=state.highlight;
   if(state.alpha>.2)visible.push({point:p,diameter:count===1?86:58});
  }
  for(const {marker} of clashes.values())marker.visible=false;
  activeEngagements=engagementStates(data.blueprint.forces,actions,time,data.blueprint.scale);
  for(const event of activeEngagements){
   const {marker,rays}=clashes.get(event.id),point=project(event);
   marker.visible=true;marker.alpha=event.strength;marker.position.set(point.x,point.y);marker.scale.set(1/Math.max(.001,worldScale()));
   rays.alpha=event.burst;visible.push({point,diameter:100});
  }
  return visible;
 };
 return {render,actors,get engagements(){return activeEngagements;}};
}
