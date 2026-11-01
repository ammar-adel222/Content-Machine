export const platforms=['youtube','instagram','tiktok'];
export const names={youtube:'YouTube',instagram:'Instagram',tiktok:'TikTok'};
export const stages=['Research','Writing','Script review','Battle direction','Visuals & audio','Rendering','Final review'];
export const storageKey='content-machine-studio-v1';
export const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function metadata(topic){return Object.fromEntries(platforms.map(p=>[p,{title:topic,description:'The terrain. The decision. The turning point. A closer look at history’s defining battles.',hashtags:'#MilitaryHistory #BattleTactics #HistoryExplained'}]));}
export function initialState(){return {version:1,projects:[
 {id:'austerlitz',title:'The trap at Austerlitz',topic:'Battle of Austerlitz',kind:'battle',format:'portrait',status:'ready',duration:'1:16',date:'2026-11-01',revision:1,history:[],edits:[],metadata:metadata('How Napoleon turned a retreat into a trap'),selectedPlatforms:[...platforms],sample:true},
 {id:'thermopylae',title:'Why the narrow pass mattered',topic:'Battle of Thermopylae',kind:'battle',format:'portrait',status:'published',duration:'1:42',date:'2026-10-28',revision:1,history:[],edits:[],metadata:metadata('Thermopylae: the terrain was the weapon'),selectedPlatforms:[...platforms]},
 {id:'desert',title:'A war across the desert',topic:'North African campaign',kind:'war',format:'portrait',status:'draft',duration:'—',date:'2026-10-30',revision:1,history:[],edits:[],metadata:metadata('A war across the desert'),selectedPlatforms:[...platforms]}
 ]};}
export function restore(raw){
 try{const state=JSON.parse(raw);if(state?.version!==1||!Array.isArray(state.projects))throw Error();
 const ids=new Set();for(const p of state.projects){
  if(!p||typeof p.id!=='string'||ids.has(p.id)||typeof p.title!=='string'||typeof p.topic!=='string'||!['battle','war'].includes(p.kind)||!['portrait','landscape'].includes(p.format)||!['draft','generating','ready','published'].includes(p.status)||!Number.isInteger(p.revision)||p.revision<1||!Array.isArray(p.history)||!Array.isArray(p.edits)||!Array.isArray(p.selectedPlatforms)||p.selectedPlatforms.some(x=>!platforms.includes(x)))throw Error();
  if(p.history.some(x=>!x||!Number.isInteger(x.revision)||typeof x.date!=='string')||p.edits.some(x=>!x||typeof x.scope!=='string'||typeof x.text!=='string'||typeof x.date!=='string'))throw Error();
  for(const platform of platforms)for(const key of ['title','description','hashtags'])if(typeof p.metadata?.[platform]?.[key]!=='string')throw Error();
  if(p.status==='generating'&&(!Number.isFinite(p.started)||p.started<0))throw Error();ids.add(p.id);
 }return state;
 }catch{return initialState();}
}
export function createProject({topic='',kind='battle',format='portrait'},id,now=Date.now()){
 if(!['battle','war'].includes(kind)||!['portrait','landscape'].includes(format))throw Error('Choose a supported video type and format.');
 topic=topic.trim();if(topic.length>300)throw Error('Keep the topic under 300 characters.');
 const title=topic||'Researcher’s choice';
 return {id,title,topic,kind,format,status:'generating',started:now,duration:'—',date:new Date(now).toISOString().slice(0,10),revision:1,history:[],edits:[],metadata:metadata(title),selectedPlatforms:[...platforms],demo:true};
}
export function progress(project,now=Date.now()){
 if(project.status!=='generating')return {index:project.status==='draft'?-1:stages.length,percent:project.status==='draft'?0:100,done:project.status!=='draft'};
 const elapsed=Math.max(0,now-project.started),index=Math.min(stages.length,Math.floor(elapsed/2200));
 return {index,percent:Math.min(100,Math.floor(elapsed/(stages.length*22))),done:index===stages.length};
}
export function finishRuns(state,now=Date.now()){
 let changed=false;for(const p of state.projects)if(p.status==='generating'&&progress(p,now).done){p.status='ready';p.duration='Demo';changed=true;}return changed;
}
export function applyEdit(project,scope,text,now=Date.now()){
 text=text.trim();if(!text||text.length>5000)throw Error('Describe your edit in 1–5,000 characters.');
 if(project.status==='generating')throw Error('Wait for this demo run to finish before editing.');
 if(!['General','Script & voice','Map & units','Sound & music'].includes(scope))throw Error('Unknown edit scope.');
 project.history.push({revision:project.revision,title:project.title,date:new Date(now).toISOString()});
 project.edits.push({revision:project.revision+1,scope,text,date:new Date(now).toISOString()});
 project.revision++;project.status='generating';project.started=now;project.demo=true;
}
export function filterProjects(projects,query='',status='all'){
 return projects.filter(p=>(status==='all'||p.status===status)&&`${p.title} ${p.topic}`.toLowerCase().includes(query.trim().toLowerCase()));
}
const demoMetrics={
 austerlitz:{youtube:[12840,735,89,41],instagram:[9200,610,52,68],tiktok:[18600,1400,104,171]},
 thermopylae:{youtube:[24800,1340,142,97],instagram:[17300,1210,91,143],tiktok:[36900,2980,223,310]}
};
export function analytics({platform='all',video='all',period='30'}={}){
 period=String(period);
 if(!['all',...platforms].includes(platform)||!['7','30','90'].includes(String(period)))throw Error('Invalid analytics filter.');
 const factor=period==='7'?.32:period==='90'?1.7:1;
 const rows=Object.entries(demoMetrics).filter(([id])=>video==='all'||video===id).map(([id,metrics])=>{
  const selected=platform==='all'?Object.values(metrics):[metrics[platform]];
  const totals=selected.reduce((a,row)=>a.map((v,i)=>v+row[i]),[0,0,0,0]).map(v=>Math.round(v*factor));
  return {id,views:totals[0],likes:totals[1],comments:totals[2],shares:totals[3],engagement:totals[0]?100*(totals[1]+totals[2]+totals[3])/totals[0]:0};
 });
 const total=rows.reduce((a,r)=>({views:a.views+r.views,likes:a.likes+r.likes,comments:a.comments+r.comments,shares:a.shares+r.shares}),{views:0,likes:0,comments:0,shares:0});
 return {...total,engagement:total.views?100*(total.likes+total.comments+total.shares)/total.views:0,rows,
  channels:platforms.map(p=>({platform:p,views:Object.entries(demoMetrics).filter(([id])=>video==='all'||id===video).reduce((n,[id,m])=>n+Math.round(m[p][0]*factor),0)}))};
}
