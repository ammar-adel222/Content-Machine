import {clamp} from './motion.mjs';

export function videoSize(aspect='portrait') {
 if(aspect==='portrait')return {width:1080,height:1920};
 if(aspect==='landscape')return {width:1920,height:1080};
 throw Error('Choose portrait or landscape video format.');
}

export function coverCamera(bounds,width,height,focus={x:0,y:0},padding=1.03) {
 const scale=Math.max(width/bounds.width,height/bounds.height)*padding;
 const x=clamp(focus.x,bounds.x+width/(2*scale),bounds.x+bounds.width-width/(2*scale));
 const y=clamp(focus.y,bounds.y+height/(2*scale),bounds.y+bounds.height-height/(2*scale));
 return {scale,x:width/2-x*scale,y:height/2-y*scale};
}

export function filmOverlay(data,app,credits,note='') {
 const {Container,Graphics,Text}=globalThis.PIXI,W=app.screen.width,H=app.screen.height;
 const root=new Container(),captionPanel=new Graphics(),titlePanel=new Graphics();app.stage.addChild(root);
 const make=(size,color)=>new Text({text:'',style:{fontFamily:'Georgia, serif',fontSize:size,fill:color,wordWrap:true,wordWrapWidth:W-112,lineHeight:size*1.22}});
 const topic=make(34,0x263c40),phase=make(23,0x526451),caption=make(32,0x203538),credit=make(15,0x3a534c),detail=make(17,0x41574d);
 topic.text=data.topic;topic.position.set(42,30);phase.position.set(42,73);
 credit.text=credits;credit.position.set(30,H-27);
 detail.text=note;detail.position.set(32,H-56);
 root.addChild(titlePanel,topic,phase,captionPanel,caption,detail,credit);
 return {root,phase,captionTop:()=>caption.text?caption.y-14:H-74,update(time,title){
  phase.text=title;
  const cardW=Math.min(W-48,Math.max(topic.width,phase.width)+32);
  titlePanel.clear().roundRect(26,19,cardW,87,8).fill({color:0xf4efdf,alpha:.84});
  const active=data.captions.find(c=>time>=c.start&&time<c.end);
  caption.text=active?.text??'';caption.style.fontSize=caption.text.length>200?27:32;
  caption.position.set(54,H-83-caption.height);
  captionPanel.clear();
  if(caption.text)captionPanel.roundRect(34,caption.y-14,W-68,caption.height+28,9).fill({color:0xf5f0e1,alpha:.86});
 }};
}
