import {factionRoster} from './symbols.mjs';
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

// Imported word times follow the voice; missing imports use explicit local estimates.
export function captionState(captions,time,groupSize=5) {
 const phrase=captions.find(c=>time>=c.start&&time<c.end);
 if(!phrase)return {text:'',words:[],active:-1};
 const tokens=phrase.text.trim().split(/\s+/);
 const timed=phrase.words?.length===tokens.length?phrase.words:tokens.map((text,i)=>({text,start:phrase.start+(phrase.end-phrase.start)*i/tokens.length,end:phrase.start+(phrase.end-phrase.start)*(i+1)/tokens.length}));
 let index=0;for(let i=0;i<timed.length;i++){if(time<timed[i].start)break;index=i;}
 const start=Math.floor(index/groupSize)*groupSize,words=tokens.slice(start,start+groupSize);
 const active=time>=timed[index].start&&time<timed[index].end+.08?index-start:-1;
 return {text:words.join(' '),words,active};
}
export const captionAt=(captions,time,groupSize=5)=>captionState(captions,time,groupSize).text;
export function wordLayout(widths,maxWidth,gap=9,lineHeight=51) {
 const rows=[[]];let width=0;
 widths.forEach((size,index)=>{
  size=Math.min(size,maxWidth);
  if(rows.at(-1).length&&width+gap+size>maxWidth){rows.push([]);width=0;}
  rows.at(-1).push({index,width:size});width+=(width?gap:0)+size;
 });
 const output=[];
 rows.forEach((row,line)=>{
  let x=-(row.reduce((n,item)=>n+item.width,0)+gap*Math.max(0,row.length-1))/2;
  for(const item of row){output[item.index]={x,y:line*lineHeight};x+=item.width+gap;}
 });
 return output;
}
// Keep every caption above the bottom platform UI and away from the right rail.
export function captionY(height) {return Math.round(height*.72);}

export function filmOverlay(data,app,credits,note='') {
 const {Container,Graphics,Text}=globalThis.PIXI,W=app.screen.width,H=app.screen.height;
 const root=new Container(),captionPanel=new Graphics(),titlePanel=new Graphics();app.stage.addChild(root);
 const make=(size,color)=>new Text({text:'',style:{fontFamily:'Georgia, serif',fontSize:size,fill:color,wordWrap:true,wordWrapWidth:W-112,lineHeight:size*1.22}});
 const topic=make(34,0x263c40),phase=make(23,0x526451),caption=new Container(),credit=make(15,0x3a534c),detail=make(17,0x41574d);
 topic.text=data.topic;topic.position.set(42,30);phase.position.set(42,73);
 credit.text=credits;credit.position.set(30,H-27);
 detail.text=note;detail.position.set(32,H-56);
 caption.text='';caption.label='captions';
 const wordNodes=Array.from({length:5},(_,index)=>{
  const word=make(42,0xf9f4e7);word.style.stroke={color:0x080b0d,width:data.presentation?.caption_stroke_px??10,join:'round'};
  word.style.fontWeight='bold';word.style.wordWrap=false;word.label='caption-word:'+index;word.visible=false;caption.addChild(word);return word;
 });
 caption.position.set(W/2-60,captionY(H));
 root.addChild(titlePanel,topic,phase,captionPanel,caption,detail,credit);
 const clashPanel=new Graphics(),clashText=make(28,0x26383b);clashText.label='hud:clash';clashText.position.set(42,168);root.addChild(clashPanel,clashText);
 const factions=new Map(factionRoster(data.blueprint?.forces).map(f=>[f.id,f.label]));
 let legendX=42;
 for(const faction of factionRoster(data.blueprint?.forces)){
  const swatch=new Graphics().roundRect(legendX,124,20,20,4).fill(faction.color);root.addChild(swatch);
  const label=make(23,0x263c40);label.text=faction.label;label.position.set(legendX+30,120);root.addChild(label);
  legendX+=label.width+70;
 }

 return {root,phase,captionBounds:()=>caption.text?{x:caption.x-caption.width/2-6,y:caption.y-8,width:caption.width+12,height:caption.height+16}:null,captionTop:()=>caption.text&&caption.y>H/2?caption.y-14:H-74,update(time,title,occupied=[],engagements=[]){
  clashText.text=engagements.length?'CLASH  '+[...new Set(engagements.flatMap(e=>[factions.get(e.actor)??e.actor,factions.get(e.target)??e.target]))].join(' vs '):'';
  clashPanel.clear();if(clashText.text)clashPanel.roundRect(30,160,clashText.width+24,42,7).fill({color:0xf4e2b8,alpha:.94});
  phase.text=title;
  const cardW=Math.min(W-48,Math.max(topic.width,phase.width)+32);
  titlePanel.clear().roundRect(26,19,cardW,87,8).fill({color:0xf4efdf,alpha:.84});
  const state=captionState(data.captions,time);
  if(caption.text!==state.text){
   caption.text=state.text;
   wordNodes.forEach((word,index)=>{word.text=state.words[index]??'';word.visible=index<state.words.length;word.scale.set(1);});
   const widths=wordNodes.slice(0,state.words.length).map(word=>Math.min(W-240,word.width));
   const layout=wordLayout(widths,W-240);
   wordNodes.forEach((word,index)=>{if(layout[index]){word.scale.x=Math.min(1,(W-240)/Math.max(1,word.width));word.position.set(layout[index].x,layout[index].y);}});
  }
  wordNodes.forEach((word,index)=>{
   const color=index===state.active?0xf5c542:0xf9f4e7;
   if(word.currentFill!==color){word.style.fill=color;word.currentFill=color;}
  });
  caption.activeWord=state.active;captionPanel.clear();

 }};
}
