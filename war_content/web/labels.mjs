export function overlaps(a,b,gap=8) {
 return a.x<b.x+b.width+gap && a.x+a.width+gap>b.x && a.y<b.y+b.height+gap && a.y+a.height+gap>b.y;
}
export function placeLabel(anchor,width,height,occupied,bounds) {
 const candidates=[[-width/2,-height-22],[-width/2,22],[22,-height/2],[-width-22,-height/2],
  [30,-height-35],[-width-30,-height-35],[30,40],[-width-30,40],[-width/2,70],[-width/2,-height-70],[80,-height/2],[-width-80,-height/2]];
 for(const [dx,dy] of candidates) {
  const box={x:anchor.x+dx,y:anchor.y+dy,width,height};
  if(box.x>=bounds.x && box.y>=bounds.y && box.x+width<=bounds.x+bounds.width && box.y+height<=bounds.y+bounds.height &&
     !occupied.some(other=>overlaps(box,other)))return box;
 }
 return null;
}
