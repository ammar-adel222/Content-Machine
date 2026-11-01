// Stable faction identity is independent of scene order and the selected action.
export function factionRoster(forces=[]) {
 const sides=[...new Set(forces.map(f=>f.side))].sort();
 return sides.map(side=>{
  const name=side.toLowerCase();
  const french=/^(france|french)$/.test(name),allied=/^(allied|allies|coalition)$/.test(name);
  let hash=0;for(const c of name)hash=(hash*31+c.charCodeAt(0))>>>0;
  const color=french?0x477f92:allied?0xb2634e:[0x8b7eae,0x5b8866,0xad8444,0x667f9c][hash%4];
  return {id:side,label:french?'France':allied?'Allies':side,color};
 });
}
export const palette={team:0x6a8580,ink:0x26383b,paper:0xf1e9d5,accent:0xb88a47,muted:0x9eab94};
export function designBounds(design) {
  let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
  for(const p of design.primitives) {
    const stroke=p.stroke!=='none'?p.stroke_width/2:0;
    const xs=p.kind==='line'||p.kind==='polygon'?p.points.map(v=>v.x):[p.x-p.width/2,p.x+p.width/2];
    const ys=p.kind==='line'||p.kind==='polygon'?p.points.map(v=>v.y):[p.y-p.height/2,p.y+p.height/2];
    left=Math.min(left,...xs.map(x=>x-stroke));right=Math.max(right,...xs.map(x=>x+stroke));
    top=Math.min(top,...ys.map(y=>y-stroke));bottom=Math.max(bottom,...ys.map(y=>y+stroke));
  }
  return {x:left,y:top,width:right-left,height:bottom-top};
}

// Fit the actual artwork, including its outline, to a consistent screen size.
export function drawUnit(design,team=palette.team,pixels=48) {
  // Build curves at a useful local size before scaling; tiny local geometry
  // makes Pixi tessellate circles into visibly coarse polygons when enlarged.
  const local=64,bounds=designBounds(design),c=new globalThis.PIXI.Container(),shape=drawDesign(design,team,local);
  shape.position.set((-bounds.x-bounds.width/2)*local,(-bounds.y-bounds.height/2)*local);
  c.addChild(shape);c.scale.set(pixels/(local*Math.max(bounds.width,bounds.height)));
  return c;
}

export function drawDesign(design,team=palette.team,size=24) {
  const {Container,Graphics}=globalThis.PIXI,c=new Container();
  for(const p of design.primitives) {
    const g=new Graphics();
    if(p.kind==='rect')g.roundRect((p.x-p.width/2)*size,(p.y-p.height/2)*size,p.width*size,p.height*size,Math.min(2,size*p.height/5));
    if(p.kind==='ellipse')g.ellipse(p.x*size,p.y*size,p.width*size/2,p.height*size/2);
    if(p.kind==='polygon')g.poly(p.points.flatMap(v=>[v.x*size,v.y*size]),true);
    if(p.kind==='line'){g.moveTo(p.points[0].x*size,p.points[0].y*size);for(const v of p.points.slice(1))g.lineTo(v.x*size,v.y*size);}
    if(p.fill!=='none' && p.kind!=='line')g.fill(p.fill==='team'?team:palette[p.fill]);
    if(p.stroke!=='none' && p.stroke_width)g.stroke({color:p.stroke==='team'?team:palette[p.stroke],width:p.stroke_width*size,join:'round',cap:'round'});
    c.addChild(g);
  }
  return c;
}
