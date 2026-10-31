import {clamp} from './motion.mjs';
import {projectGeo} from './geography.mjs';
import {coverCamera,filmOverlay} from './video.mjs';
import {createUnits} from './units.mjs';
const terrainMetrics=new WeakMap();

export function heightAt(grid,u,v) {
 const x=clamp(u)*(grid.columns-1),y=clamp(v)*(grid.rows-1),ix=Math.floor(x),iy=Math.floor(y);
 const ax=Math.min(grid.columns-1,ix+1),ay=Math.min(grid.rows-1,iy+1),fx=x-ix,fy=y-iy;
 return (grid.values[iy*grid.columns+ix]*(1-fx)+grid.values[iy*grid.columns+ax]*fx)*(1-fy)+
        (grid.values[ay*grid.columns+ix]*(1-fx)+grid.values[ay*grid.columns+ax]*fx)*fy;
}

export function terrainPoint(field,u,v,height=heightAt(field.heights,u,v)) {
 if(!terrainMetrics.has(field)){
  const b=field.layer.bounds,meters=(b.east-b.west)*Math.cos((b.north+b.south)/2*Math.PI/180)*111320;
  terrainMetrics.set(field,{base:Math.min(...field.heights.values),meters,depth:850*(b.north-b.south)*111320/meters});
 }
 const {base,meters,depth}=terrainMetrics.get(field);
 return {x:(u-.5)*850+(v-.5)*75,y:(v-.5)*depth*.68-(height-base)*850/meters*field.exaggeration};
}

export function meshData(field) {
 const {columns,rows}=field.heights,vertices=[],uvs=[],indices=[],b=field.layer.bounds;
 for(let y=0;y<rows;y++)for(let x=0;x<columns;x++){
  const u=x/(columns-1),v=y/(rows-1),p=terrainPoint(field,u,v);
  vertices.push(p.x,p.y);
  const projected=projectGeo(b.west+(b.east-b.west)*u,b.north-(b.north-b.south)*v,field.layer,{x:0,y:0,width:field.layer.width,height:field.layer.height});
  uvs.push(projected.x/field.layer.width,projected.y/field.layer.height);
  if(x<columns-1 && y<rows-1){const a=y*columns+x;indices.push(a,a+1,a+columns,a+1,a+columns+1,a+columns);}
 }
 return {vertices:new Float32Array(vertices),uvs:new Float32Array(uvs),indices:new Uint32Array(indices)};
}

export function terrainBounds(field) {
 const north=[],south=[],west=[],east=[];
 for(let i=0;i<=128;i++){north.push(terrainPoint(field,i/128,0));south.push(terrainPoint(field,i/128,1));west.push(terrainPoint(field,0,i/128));east.push(terrainPoint(field,1,i/128));}
 const x=Math.max(...west.map(p=>p.x)),right=Math.min(...east.map(p=>p.x));
 const y=Math.max(...north.map(p=>p.y)),bottom=Math.min(...south.map(p=>p.y));
 return {x,y,width:right-x,height:bottom-y};
}

export async function createBattlefield(data,app) {
 const {Container,Graphics,Text,MeshSimple,Assets}=globalThis.PIXI,field=data.battlefield;
 const paper=0xeee8d8,ink=0x2b3d3e,b=field.layer.bounds,W=app.screen.width,H=app.screen.height;
 const study=data.purpose==='unit_animation_study';
 function text(value,x,y,size=25,color=ink,width=950) {
  const t=new Text({text:value,style:{fontFamily:'Georgia, serif',fontSize:size,fill:color,wordWrap:true,wordWrapWidth:width,lineHeight:size*1.24}});
  t.position.set(x,y);app.stage.addChild(t);return t;
 }
 app.stage.addChild(new Graphics().rect(0,0,W,H).fill(paper));
 const world=new Container();
 const clip=new Graphics().rect(0,0,W,H).fill(0xffffff);app.stage.addChild(world,clip);world.mask=clip;
 const projected=(lon,lat)=>terrainPoint(field,(lon-b.west)/(b.east-b.west),(b.north-lat)/(b.north-b.south));
 const texture=await Assets.load(field.layer.relief),geometry=meshData(field);
 const surface=new MeshSimple({texture,...geometry});surface.autoUpdate=false;world.addChild(surface);
 const contours=new Graphics(),grid=field.heights;
 const min=Math.min(...grid.values),max=Math.max(...grid.values);
 for(let elevation=Math.ceil(min/40)*40;elevation<max;elevation+=40){
  for(let y=0;y<grid.rows-2;y+=2)for(let x=0;x<grid.columns-2;x+=2){
   const corners=[[x,y],[x+2,y],[x+2,y+2],[x,y+2]],crossings=[];
   for(let e=0;e<4;e++){
    const a=corners[e],c=corners[(e+1)%4],ha=grid.values[a[1]*grid.columns+a[0]],hc=grid.values[c[1]*grid.columns+c[0]];
    if((ha<elevation)===(hc<elevation))continue;
    const t=(elevation-ha)/(hc-ha);
    crossings.push(terrainPoint(field,(a[0]+(c[0]-a[0])*t)/(grid.columns-1),(a[1]+(c[1]-a[1])*t)/(grid.rows-1),elevation));
   }
   for(let i=0;i+1<crossings.length;i+=2)contours.moveTo(crossings[i].x,crossings[i].y).lineTo(crossings[i+1].x,crossings[i+1].y);
  }
 }
 contours.stroke({color:0x5b654c,width:.7,alpha:.35});world.addChild(contours);
 const streams=new Graphics(),streamUnderlay=new Graphics();
 for(const feature of field.features.filter(f=>f.kind==='stream')){
  feature.points.forEach(([lon,lat],i)=>{const p=projected(lon,lat);for(const target of [streamUnderlay,streams])i?target.lineTo(p.x,p.y):target.moveTo(p.x,p.y);});
 }
 streamUnderlay.stroke({color:0xf2edda,width:8,alpha:.8,cap:'round',join:'round'});streams.stroke({color:0x438dba,width:4,cap:'round',join:'round'});world.addChild(streamUnderlay,streams);
 const villages=[],ridge=[],mapText=[];
 for(const feature of field.features.filter(f=>f.kind!=='stream')){
  const [lon,lat]=feature.points[0],p=projected(lon,lat),holder=new Container();holder.position.set(p.x,p.y);
  if(feature.kind==='village'){
   for(let i=0;i<6;i++){
    const x=(i%3-1)*12,y=(Math.floor(i/3)-.5)*12;
    holder.addChild(new Graphics().rect(x-4,y-3,8,7).fill(0xc9b99a).stroke({color:0x5a5448,width:1})
      .poly([x-5,y-3,x,y-8,x+5,y-3],true).fill(0x80674e));
   }
   villages.push(holder);
  }else{
   const ring=new Graphics().ellipse(0,0,115,60).stroke({color:0xa67635,width:3,alpha:.55});holder.addChild(ring);ridge.push(ring);
  }
  const label=new Text({text:feature.name,style:{fontFamily:'Georgia, serif',fontSize:feature.kind==='ridge'?29:25,fontWeight:feature.kind==='ridge'?'bold':'normal',fill:ink}});
  const offset={x:feature.kind==='ridge'?40:0,y:feature.kind==='ridge'?35:-17};
  label.anchor.set(.5,1);label.position.set(offset.x,offset.y);holder.addChild(label);world.addChild(holder);mapText.push({label,anchor:p,offset,holder});
 }
 // Elevation badges make the surface's height differences readable without guessing.
 for(const [u,v] of (study?[]:[[.18,.38],[.64,.62]])){
  const p=terrainPoint(field,u,v),h=Math.round(heightAt(grid,u,v));
  const dx=u>.5?75:0;
  const stick=new Graphics().moveTo(p.x,p.y).lineTo(p.x+dx,p.y-47).stroke({color:0x5f6e58,width:1});world.addChild(stick);
  const tag=new Text({text:'~'+h+' m',style:{fontFamily:'sans-serif',fontSize:20,fill:0x47583e}});tag.anchor.set(.5,1);tag.position.set(p.x+dx,p.y-49);world.addChild(tag);mapText.push({label:tag,anchor:p,offset:{x:dx,y:-49}});
 }
 const units=study?createUnits(data,world,p=>terrainPoint(field,p.x,p.y),()=>world.scale.x):null;
 const hud=filmOverlay(data,app,'Mapzen / USGS / Copernicus · GeoNames · © OSM contributors · openstreetmap.org/copyright',
  study?'Animation study · illustrative deployments · '+(data.soundtrack?'sound effects':'silent'):'Terrain study · modern stream course · '+field.exaggeration+'× height emphasis');
 const bounds=terrainBounds(field);
 const center=kind=>{
  const points=field.features.filter(f=>f.kind===kind).flatMap(f=>f.points).map(([lon,lat])=>projected(lon,lat));
  return points.length?{x:points.reduce((n,p)=>n+p.x,0)/points.length,y:points.reduce((n,p)=>n+p.y,0)/points.length}:{x:0,y:0};
 };
 const focuses=[center('ridge'),center('stream'),center('village'),{x:0,y:0}];
 const villageY=field.features.filter(f=>f.kind==='village').map(f=>projected(...f.points[0]).y);
 const annotationLeaders=new Graphics();world.addChild(annotationLeaders);
 const bar=new Graphics();app.stage.addChild(bar);const scaleText=text('',W-242,28,20);
 text('N',W-64,114,22);app.stage.addChild(new Graphics().poly([W-55,141,W-65,165,W-43,165],true).fill(ink));
 return time=>{
  let index=data.scenes.findIndex(s=>time>=s.start&&time<s.end);if(index<0)index=time<data.scenes[0].start?0:data.scenes.length-1;
  const target={...focuses[Math.min(index,focuses.length-1)]},previous={...focuses[Math.max(0,Math.min(index-1,focuses.length-1))]};
  if(index===3&&W>H&&villageY.length)previous.y=Math.max(...villageY);
  if(index===2&&W>H&&villageY.length){const p=clamp((time-data.scenes[index].start)/(data.scenes[index].end-data.scenes[index].start));target.y=Math.min(...villageY)+(Math.max(...villageY)-Math.min(...villageY))*p;}
  if(study){const p=terrainPoint(field,data.animation_camera.x,data.animation_camera.y);Object.assign(target,p);Object.assign(previous,p);}
  const t=clamp((time-data.scenes[index].start)/1.2),ease=t*t*(3-2*t);
  const camera=coverCamera(bounds,W,H,{x:previous.x+(target.x-previous.x)*ease,y:previous.y+(target.y-previous.y)*ease});
  world.scale.set(camera.scale);world.position.set(camera.x,camera.y);
  const occupied=units?.render(time)??[];
  hud.update(time,data.scenes[index].labels.join(' · '));
  const bottom=hud.captionTop()-12;annotationLeaders.clear();
  for(const item of mapText){
   const {label,anchor,offset}=item;label.scale.set(1/camera.scale);
   const px=camera.x+anchor.x*camera.scale,py=camera.y+anchor.y*camera.scale;
   const sx=camera.x+(anchor.x+offset.x)*camera.scale,sy=camera.y+(anchor.y+offset.y)*camera.scale;
   const width=label.width*camera.scale,height=label.height*camera.scale;
   label.visible=px>=10&&px<=W-10&&py>=10&&py<=H-10;
   if(study&&occupied.some(unit=>Math.hypot((unit.point.x-anchor.x)*camera.scale,(unit.point.y-anchor.y)*camera.scale)<95))label.visible=false;
   if(label.visible){
    const x=clamp(sx,18+width/2,W-18-width/2),y=clamp(sy,120+height,bottom);
    label.position.set((x-camera.x)/camera.scale-(item.holder?anchor.x:0),(y-camera.y)/camera.scale-(item.holder?anchor.y:0));
    if(Math.abs(x-sx)+Math.abs(y-sy)>8)annotationLeaders.moveTo(anchor.x,anchor.y).lineTo((x-camera.x)/camera.scale,(y-camera.y)/camera.scale);
   }
  }
  annotationLeaders.stroke({color:0x53654e,width:1/camera.scale,alpha:.6});
  const scaleKm=(b.east-b.west)*Math.cos((b.north+b.south)/2*Math.PI/180)*111.32;
  const km=[.25,.5,1,2,5].filter(k=>850/scaleKm*camera.scale*k<=180).pop()??.1,length=850/scaleKm*camera.scale*km;
  scaleText.text=km+' km';bar.clear().moveTo(W-242,59).lineTo(W-242+length,59).stroke({color:ink,width:3});
  streams.alpha=index===1?1:.65;
  for(const shape of ridge)shape.alpha=!study&&index===0?.9:0;
  for(const shape of villages)shape.alpha=index===2?1:.8;
  app.renderer.render(app.stage);
 };
}
