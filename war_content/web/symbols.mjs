export const palette={team:0x6a8580,ink:0x26383b,paper:0xf1e9d5,accent:0xb88a47,muted:0x9eab94};
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
