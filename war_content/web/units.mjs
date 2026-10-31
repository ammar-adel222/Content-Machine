import {unitState} from './motion.mjs';
import {drawUnit} from './symbols.mjs';

// Shared presentation of deterministic choreography on flat or projected terrain.
export function createUnits(data,world,project,worldScale=()=>1) {
 const {Container,Graphics}=globalThis.PIXI,colors=[0x477f92,0xb2634e,0x8b7eae,0x5b8866];
 const sides=[...new Set(data.blueprint.forces.map(f=>f.side))],actors=[];
 const definitions=new Map(data.blueprint.scenes.flatMap(s=>s.actions.map(a=>[a.id,a])));
 const actions=data.timeline.map(row=>({...definitions.get(row.action_id),...row}));
 for(const force of data.blueprint.forces){
  const count=data.blueprint.scale==='campaign'?1:force.subgroups,color=colors[sides.indexOf(force.side)%colors.length];
  for(let index=0;index<count;index++){
   const holder=new Container(),halo=new Graphics().circle(0,0,37).stroke({color,width:3,alpha:.7});
   holder.label=`unit:${force.id}:${index}`;
   const body=drawUnit(data.assets[data.bindings.unit[force.id]],color,count===1?72:54);
   holder.addChild(halo,body);world.addChild(holder);actors.push({force,index,count,holder,halo,body});
  }
 }
 const render=time=>{
  const visible=[];
  for(const actor of actors){
   const {force,index,count,holder,body,halo}=actor,state=unitState(force,actions,time,index,count),p=project(state);
   const ahead=project({x:state.x+Math.cos(state.angle)*.001,y:state.y+Math.sin(state.angle)*.001*9/16});
   holder.position.set(p.x,p.y);holder.rotation=Math.atan2(ahead.y-p.y,ahead.x-p.x);
   holder.alpha=state.alpha;holder.visible=state.alpha>0;holder.scale.set(1/Math.max(.001,worldScale()));
   body.position.y=state.bob;body.rotation=state.roll;halo.alpha=state.highlight;
   if(state.alpha>.2)visible.push({point:p,diameter:count===1?78:60});
  }
  return visible;
 };
 return {render,actors};
}
