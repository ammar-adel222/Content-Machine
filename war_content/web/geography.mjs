import {drawUnit} from './symbols.mjs';
import {placeLabel} from './labels.mjs';
import {clamp,smooth} from './motion.mjs';
import {coverCamera,filmOverlay} from './video.mjs';

export function projectGeo(lon,lat,layer,frame) {
 const b=layer.bounds,cos=Math.cos((b.north+b.south)/2*Math.PI/180);
 const sx=(b.east-b.west)*cos,sy=b.north-b.south,scale=Math.min(layer.width/sx,layer.height/sy);
 const px=(layer.width-sx*scale)/2+(lon-b.west)*cos*scale;
 const py=(layer.height-sy*scale)/2+(b.north-lat)*scale;
 return {x:frame.x+px/layer.width*frame.width,y:frame.y+py/layer.height*frame.height};
}

export function scalePixels(km,layer,frame) {
 const b=layer.bounds,cos=Math.cos((b.north+b.south)/2*Math.PI/180);
 const scale=Math.min(layer.width/((b.east-b.west)*cos),layer.height/(b.north-b.south));
 return km/111.32*scale*frame.width/layer.width;
}

export function geographicFrame(layer,width,height,detail=false) {
 const original={x:0,y:0,width:layer.width,height:layer.height},b=layer.bounds;
 const nw=projectGeo(b.west,b.north,layer,original),se=projectGeo(b.east,b.south,layer,original);
 let scale,x,y;
 if(detail){
  const place=layer.places.find(p=>p.kind==='settlement');
  const focus=place?projectGeo(place.lon,place.lat,layer,original):{x:(nw.x+se.x)/2,y:(nw.y+se.y)/2};
  const camera=coverCamera({x:nw.x,y:nw.y,width:se.x-nw.x,height:se.y-nw.y},width,height,focus);
  ({scale,x,y}=camera);
 }else{
  scale=Math.min(width/(se.x-nw.x),height/(se.y-nw.y))*.95;
  x=width/2-(nw.x+se.x)/2*scale;y=height/2-(nw.y+se.y)/2*scale;
 }
 return {x,y,width:layer.width*scale,height:layer.height*scale};
}

export async function createGeography(data,app) {
 const {Container,Graphics,Text,Sprite,Assets}=globalThis.PIXI;
 const W=app.screen.width,H=app.screen.height,ink=0x263c40,water=0xaac6ca;
 const colors=[0x477f92,0xb2634e,0x8b7eae,0x5b8866];
 const sides=[...new Set(data.blueprint.forces.map(f=>f.side))],maps=[],markers=[];
 for(let index=0;index<data.geography.layers.length;index++){
  const layer=data.geography.layers[index],frame=geographicFrame(layer,W,H,index>0),group=new Container();
  app.stage.addChild(group);maps.push({group,layer,frame});
  group.addChild(new Graphics().rect(0,0,W,H).fill(water));
  const mask=new Graphics(),coast=new Graphics();
  for(const polygon of layer.land){
   const rings=polygon.rings.map(ring=>ring.flatMap(([lon,lat])=>{const p=projectGeo(lon,lat,layer,frame);return [p.x,p.y];}));
   mask.poly(rings[0],true).fill(0xffffff);
   for(const hole of rings.slice(1))mask.poly(hole,true).cut();
   for(const ring of rings)coast.poly(ring,true).stroke({color:0x526f65,width:1.7,alpha:.9});
  }
  const texture=await Assets.load(layer.relief),relief=new Sprite(texture);
  relief.position.set(frame.x,frame.y);relief.width=frame.width;relief.height=frame.height;
  group.addChild(relief,mask);relief.mask=mask;group.addChild(coast);
  const grid=new Graphics(),b=layer.bounds,step=index?.1:.5;
  for(let lon=Math.ceil(b.west/step)*step;lon<b.east;lon+=step){const p=projectGeo(lon,b.south,layer,frame),q=projectGeo(lon,b.north,layer,frame);grid.moveTo(p.x,p.y).lineTo(q.x,q.y);}
  for(let lat=Math.ceil(b.south/step)*step;lat<b.north;lat+=step){const p=projectGeo(b.west,lat,layer,frame),q=projectGeo(b.east,lat,layer,frame);grid.moveTo(p.x,p.y).lineTo(q.x,q.y);}
  grid.stroke({color:0x4f7477,width:1,alpha:.13});group.addChild(grid);
  const occupied=[],bounds={x:28,y:140,width:W-56,height:H-390};
  for(const place of [...layer.places].sort((a,b)=>(a.kind==='settlement'?-1:0)-(b.kind==='settlement'?-1:0))){
   const p=projectGeo(place.lon,place.lat,layer,frame);
   if(p.x<0||p.y<0||p.x>W||p.y>H)continue;
   const dot=new Graphics();
   if(place.kind==='peak')dot.poly([p.x,p.y-6,p.x-5,p.y+4,p.x+5,p.y+4],true).fill(0x637160);
   if(place.kind==='settlement')dot.circle(p.x,p.y,5).fill(ink).stroke({color:0xf4efdf,width:2});
   group.addChild(dot);
   const label=new Text({text:place.name,style:{fontFamily:'Georgia, serif',fontSize:28,fill:place.kind==='water'?0x537b83:ink}});
   const box=placeLabel(p,label.width,label.height,occupied,bounds);
   if(box){label.position.set(box.x,box.y);group.addChild(label);occupied.push(box);
    group.addChild(new Graphics().moveTo(p.x,p.y).lineTo(box.x+box.width/2,box.y+box.height/2).stroke({color:0x536c63,width:1,alpha:.6}));}
  }
  for(const binding of data.geography.placements){
   const force=data.blueprint.forces.find(f=>f.id===binding.unit_id),place=layer.places.find(p=>p.id===binding.place_id);
   if(!force||!place)continue;
   const color=colors[sides.indexOf(force.side)%colors.length],p=projectGeo(place.lon,place.lat,layer,frame);
   const peers=data.geography.placements.filter(b=>b.place_id===binding.place_id),order=peers.indexOf(binding);
   const holder=new Container(),shape=drawUnit(data.assets[data.bindings.unit[force.id]],color,48);
   shape.position.set(p.x-60+order*55,p.y+53);
   holder.addChild(new Graphics().moveTo(p.x,p.y).lineTo(shape.x,shape.y).stroke({color,width:1,alpha:.45}),shape);group.addChild(holder);
   const intro=(data.timeline??[]).find(a=>a.kind==='introduce'&&a.unit_id===force.id);
   markers.push({binding,holder,intro:intro?.start_sec??Infinity,fades:(data.timeline??[]).filter(a=>a.kind==='fade'&&a.unit_id===force.id)});
  }
 }
 const hud=filmOverlay(data,app,'Natural Earth · GeoNames · Mapzen / USGS / NOAA','Geographic context · area-level force callouts');
 const bar=new Graphics();app.stage.addChild(bar);
 const scaleLabel=new Text({text:'',style:{fontFamily:'Georgia, serif',fontSize:20,fill:ink}});scaleLabel.position.set(W-230,28);app.stage.addChild(scaleLabel);
 const north=new Text({text:'N',style:{fontFamily:'Georgia, serif',fontSize:23,fill:ink}});north.position.set(W-61,112);app.stage.addChild(north);
 app.stage.addChild(new Graphics().poly([W-53,143,W-63,167,W-43,167],true).fill(ink));
 const mapIndex=scene=>maps.length>1&&scene.labels.some(label=>/terrain|heights|roads|ridge|hills/i.test(label))?1:0;
 return time=>{
  let index=data.scenes.findIndex(s=>time>=s.start&&time<s.end);if(index<0)index=data.scenes.length-1;
  const scene=data.scenes[index],active=mapIndex(scene),previous=mapIndex(data.scenes[Math.max(0,index-1)]);
  const fade=smooth((time-scene.start)/.7);
  for(let i=0;i<maps.length;i++){maps[i].group.visible=i===active||(i===previous&&fade<1);maps[i].group.alpha=active===previous?1:i===active?fade:1-fade;}
  for(const marker of markers){
   let alpha=1;for(const a of marker.fades)if(time>=a.start_sec)alpha=1-smooth(clamp((time-a.start_sec)/(a.end_sec-a.start_sec)));
   marker.holder.visible=marker.binding.scene_ids.includes(scene.scene_id)&&time>=marker.intro&&alpha>0;marker.holder.alpha=alpha;
  }
  const map=maps[active],units=[.25,.5,1,2,5,10,20,50,100],km=units.filter(k=>scalePixels(k,map.layer,map.frame)<=170).pop()??.1;
  const length=scalePixels(km,map.layer,map.frame);scaleLabel.text=km+' km';
  bar.clear().moveTo(W-230,59).lineTo(W-230+length,59).stroke({color:ink,width:3});
  hud.update(time,scene.labels.join(' · '));
  app.renderer.render(app.stage);
 };
}
