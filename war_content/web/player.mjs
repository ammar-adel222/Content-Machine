import {cameraAt,unitState,clamp} from './motion.mjs';
import {drawDesign as ink,palette as roles} from './symbols.mjs';
import {placeLabel} from './labels.mjs';
import {connectPlayback} from './playback.mjs';
import {videoSize,filmOverlay,coverCamera} from './video.mjs';
const {Application,Container,Graphics,Text}=globalThis.PIXI;
const W=1080,H=1920;
const sideColors=[0x477f92,0xb2634e,0x8b7eae,0x5b8866];
const terrainColors={sea:0xa6c2c5,river:0x9ebec1,plain:0xe1dbbd,forest:0xa8b495,mountain:0xb6b29c,ridge:0xc6bd9f,marsh:0xb6c2a1,rocky_ground:0xc7c0a9};
function label(text,x,y,size,color=roles.ink,width=900) {
  const t=new Text({text,style:{fontFamily:'Georgia, serif',fontSize:size,fill:color,wordWrap:true,wordWrapWidth:width,lineHeight:size*1.24}});
  t.position.set(x,y);return t;
}
function contains(p,polygon) {
  let hit=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
    const a=polygon[i],b=polygon[j];
    if((a.y>p.y)!==(b.y>p.y) && p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x)hit=!hit;
  }
  return hit;
}
async function start() {
  if(new URLSearchParams(location.search).has('export'))document.body.classList.add('export');
  const response=await fetch('scene.json');if(!response.ok)throw Error('Cannot load scene.json. Serve this bundle over HTTP.');
  const data=await response.json();
  const aspect=new URLSearchParams(location.search).get('aspect')||'portrait',size=videoSize(aspect);
  document.documentElement.style.setProperty('--video-aspect',size.width/size.height);
  document.documentElement.style.setProperty('--video-width',size.width+'px');
  document.getElementById('format').value=aspect;
  document.getElementById('format').onchange=event=>{const url=new URL(location.href);url.searchParams.set('aspect',event.target.value);location.href=url.href;};
  const app=new Application();await app.init({...size,backgroundColor:0xeee6d1,antialias:true,autoStart:false,preserveDrawingBuffer:true,preference:'webgl'});
  document.getElementById('screen').replaceChildren(app.canvas);
  if(data.battlefield) {
    document.querySelector('small').textContent='Tactical terrain study · measured heights · silent preview';
    const {createBattlefield}=await import('./battlefield.mjs');
    connectPlayback(data,app,await createBattlefield(data,app));return;
  }
  if(data.geography) {
    document.querySelector('small').textContent='Geographic map · area callouts · silent preview';
    const {createGeography}=await import('./geography.mjs');
    connectPlayback(data,app,await createGeography(data,app));return;
  }
  const SW=size.width,SH=size.height;
  const bg=new Graphics().rect(0,0,SW,SH).fill(0xded9bb);app.stage.addChild(bg);
  const world=new Container(),clip=new Graphics().rect(0,0,SW,SH).fill(0xffffff);
  app.stage.addChild(world,clip);world.mask=clip;
  world.addChild(new Graphics().rect(0,0,W,H).fill(0xded9bb));
  // Sparse contour grid gives distance cues without claiming real survey contours.
  const grid=new Graphics();for(let x=0;x<W;x+=90)grid.moveTo(x,0).lineTo(x,H);for(let y=0;y<H;y+=90)grid.moveTo(0,y).lineTo(W,y);
  grid.stroke({color:0x7b876d,width:1,alpha:0.13});world.addChild(grid);
  const terrainLabels=[];
  for(const terrain of data.blueprint.terrain) {
    const color=terrainColors[terrain.kind]??0xc2bda0;
    const points=terrain.points.flatMap(p=>[p.x*W,p.y*H]);
    const shape=new Graphics();
    if(terrain.shape==='polygon')shape.poly(points,true).fill(color).stroke({color:0x718174,width:2,alpha:0.7});
    else {shape.moveTo(points[0],points[1]);for(let i=2;i<points.length;i+=2)shape.lineTo(points[i],points[i+1]);shape.stroke({color:terrain.kind==='road'?0xa79369:color,width:terrain.kind==='river'?14:6,cap:'round',join:'round'});}
    world.addChild(shape);
    const motif=data.assets[data.bindings.terrain[terrain.id]];
    const motifs=new Container();world.addChild(motifs);
    if(terrain.shape==='polygon') {
      const mask=new Graphics().poly(points,true).fill(0xffffff);world.addChild(mask);motifs.mask=mask;
    }
    if(terrain.shape==='polygon') {
      let n=0;
      for(let y=60;y<H;y+=105)for(let x=55;x<W;x+=105) {
        const p={x:(x+(Math.floor(y/105)%2)*30)/W,y:y/H};
        if(contains(p,terrain.points) && n++<150) {const symbol=ink(motif,0x71816d,15);symbol.alpha=0.45;symbol.position.set(p.x*W,p.y*H);motifs.addChild(symbol);}
      }
    } else {
      for(const p of terrain.points.slice(1,-1)){const symbol=ink(motif,0x71816d,12);symbol.position.set(p.x*W,p.y*H);motifs.addChild(symbol);}
    }
    const p=terrain.points.reduce((a,b)=>({x:a.x+b.x/terrain.points.length,y:a.y+b.y/terrain.points.length}),{x:0,y:0});
    const t=label(terrain.label,0,0,23,0x47594e,220);
    terrainLabels.push({point:p,text:t});
  }
  const sides=[...new Set(data.blueprint.forces.map(f=>f.side))],units=[];
  const actionDefs=new Map(data.blueprint.scenes.flatMap(s=>s.actions.map(a=>[a.id,a])));
  const actions=data.timeline.map(row=>({...actionDefs.get(row.action_id),...row}));
  for(const force of data.blueprint.forces) {
    const count=data.blueprint.scale==='campaign'?1:force.subgroups,color=sideColors[sides.indexOf(force.side)%sideColors.length];
    for(let i=0;i<count;i++) {
      const holder=new Container(),halo=new Graphics().circle(0,0,28).fill({color,alpha:.16}).stroke({color,width:2,alpha:.55});
      const body=ink(data.assets[data.bindings.unit[force.id]],color,count===1?22:15);
      holder.addChild(halo,body);world.addChild(holder);units.push({force,i,count,holder,halo});
    }
  }
  const leaders=new Graphics();app.stage.addChild(leaders);
  for(const item of terrainLabels)app.stage.addChild(item.text);
  const hud=filmOverlay(data,app,'Schematic geography · symbolic force groups',sides.join(' / '));
  function renderAt(seconds) {
    const time=clamp(seconds,0,data.duration);
    const camera=cameraAt(data.scenes,time),framing=coverCamera({x:(camera.x-camera.width/2)*W,y:(camera.y-camera.width/2)*H,width:camera.width*W,height:camera.width*H},SW,SH,{x:camera.x*W,y:camera.y*H});
    const scale=framing.scale;world.scale.set(scale);world.position.set(framing.x,framing.y);
    const occupied=[];
    for(const unit of units) {
      const state=unitState(unit.force,actions,time,unit.i,unit.count);
      unit.holder.position.set(state.x*W,state.y*H);unit.holder.rotation=state.angle;
      unit.holder.alpha=state.alpha;unit.halo.alpha=.25+state.highlight*.75;
      // Keep markers legible under camera zoom without inflating subgroup spacing.
      unit.holder.scale.set(1/Math.sqrt(scale));
      if(state.alpha>.2)occupied.push({x:world.x+state.x*W*scale-25,y:world.y+state.y*H*scale-25,width:50,height:50});
    }
    leaders.clear();let visibleLabels=0;
    for(const item of terrainLabels) {
      const anchor={x:world.x+item.point.x*W*scale,y:world.y+item.point.y*H*scale};
      const inView=anchor.x>=28 && anchor.x<=SW-28 && anchor.y>=130 && anchor.y<=SH-240;
      const box=inView && visibleLabels<3 ? placeLabel(anchor,item.text.width,item.text.height,occupied,{x:28,y:130,width:SW-56,height:SH-370}):null;
      item.text.visible=Boolean(box);
      if(box){item.text.position.set(box.x,box.y);occupied.push(box);visibleLabels++;
        leaders.moveTo(anchor.x,anchor.y).lineTo(box.x+box.width/2,box.y+box.height/2).stroke({color:0x667767,width:1,alpha:.5});}
    }
    hud.update(time,camera.scene.labels.join(' · '));
    app.renderer.render(app.stage);
  }
  connectPlayback(data,app,renderAt);
}
start().catch(error=>{document.getElementById('error').textContent=error.message;document.getElementById('screen').textContent='Preview unavailable';globalThis.contentError=error.message;});
