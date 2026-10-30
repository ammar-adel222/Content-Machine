import {cameraAt,unitState,clamp} from './motion.mjs';
import {drawDesign as ink,palette as roles} from './symbols.mjs';
import {placeLabel} from './labels.mjs';
const {Application,Container,Graphics,Text}=globalThis.PIXI;
const W=1080,H=1920,TOP=230,MAP_H=1330;
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
  const app=new Application();await app.init({width:W,height:H,backgroundColor:0xeee6d1,antialias:true,autoStart:false,preserveDrawingBuffer:true,preference:'webgl'});
  document.getElementById('screen').appendChild(app.canvas);
  const bg=new Graphics().rect(0,0,W,H).fill(0xeee6d1);app.stage.addChild(bg);
  const world=new Container(),clip=new Graphics().rect(40,TOP,W-80,MAP_H).fill(0xffffff);
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
  // Headline and caption stay in screen space while the map camera moves.
  app.stage.addChild(label('CONTENT MACHINE  /  WAR TACTICS',60,55,21,0x78816e));
  const title=label(data.topic,60,102,50,roles.ink,950);if(title.height>106)title.style.fontSize=38;app.stage.addChild(title);
  app.stage.addChild(new Graphics().moveTo(60,211).lineTo(1020,211).stroke({color:0x9a9f85,width:2}));
  const sceneLabel=label('',70,TOP+35,25,roles.ink,900);app.stage.addChild(sceneLabel);
  const leaders=new Graphics();app.stage.addChild(leaders);
  for(const item of terrainLabels)app.stage.addChild(item.text);
  app.stage.addChild(new Graphics().rect(40,TOP+MAP_H+15,W-80,H-TOP-MAP_H-65).fill(0xeee6d1));
  const caption=label('',70,TOP+MAP_H+50,35,roles.ink,940);app.stage.addChild(caption);
  let legendX=70;
  sides.forEach((side,i)=>{app.stage.addChild(new Graphics().circle(legendX+7,H-70,7).fill(sideColors[i%sideColors.length]));
    const legend=label(side,legendX+25,H-84,21,0x647363,250);app.stage.addChild(legend);legendX+=legend.width+65;});
  const progress=new Graphics();app.stage.addChild(progress);
  let time=0,playing=false,last=performance.now();
  const seek=document.getElementById('seek');seek.max=data.duration;
  function renderAt(seconds) {
    time=clamp(seconds,0,data.duration);
    const camera=cameraAt(data.scenes,time),scale=Math.min((W-80)/W,MAP_H/H)/camera.width;
    world.scale.set(scale);world.position.set(W/2-camera.x*W*scale,TOP+MAP_H/2-camera.y*H*scale);
    // Camera remains 9:16; viewport is cropped by the caption/header safe area.
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
      const inView=anchor.x>=40 && anchor.x<=W-40 && anchor.y>=TOP+90 && anchor.y<=TOP+MAP_H-20;
      const box=inView && visibleLabels<3 ? placeLabel(anchor,item.text.width,item.text.height,occupied,{x:60,y:TOP+95,width:W-120,height:MAP_H-115}):null;
      item.text.visible=Boolean(box);
      if(box){item.text.position.set(box.x,box.y);occupied.push(box);visibleLabels++;
        leaders.moveTo(anchor.x,anchor.y).lineTo(box.x+box.width/2,box.y+box.height/2).stroke({color:0x667767,width:1,alpha:.5});}
    }
    const active=data.captions.find(c=>time>=c.start && time<c.end);
    caption.text=active?.text??'';caption.style.fontSize=caption.text.length>220?29:35;
    sceneLabel.text=camera.scene.labels.join('  ·  ');
    progress.clear().rect(40,H-25,(W-80)*time/data.duration,4).fill(0xa67f43);
    app.renderer.render(app.stage);seek.value=time;
    document.getElementById('time').textContent=`${Math.floor(time/60)}:${String(Math.floor(time%60)).padStart(2,'0')}`;
  }
  seek.addEventListener('input',()=>{playing=false;document.getElementById('play').textContent='Play';renderAt(Number(seek.value));});
  document.getElementById('play').onclick=()=>{if(time>=data.duration)time=0;playing=!playing;document.getElementById('play').textContent=playing?'Pause':'Play';};
  function tick(now){if(playing){renderAt(time+(now-last)/1000);if(time>=data.duration){playing=false;document.getElementById('play').textContent='Play';}}last=now;requestAnimationFrame(tick);}
  globalThis.contentEngine={renderAt,data,app};renderAt(0);globalThis.contentReady=true;requestAnimationFrame(tick);
}
start().catch(error=>{document.getElementById('error').textContent=error.message;globalThis.contentError=error.message;});
