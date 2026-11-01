/* Same-origin transport only. Account credentials never enter this module. */
export class Backend {
 constructor(config){this.key=config.key;this.metadataQueue=Promise.resolve();}
 async request(path,{method='GET',body,timeout=180000}={}){
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-Studio-Key':this.key},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(timeout)});
  let data;try{data=await response.json();}catch{throw Error('The studio returned an invalid response.');}
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Studio request failed.');return data;
 }
 metadata(project){
  const body={revision:project.revision_id,posts:structuredClone(project.metadata),selected:[...project.selectedPlatforms],...project.publish_options};
  const next=this.metadataQueue.catch(()=>{}).then(()=>this.request(`/projects/${project.id}/metadata`,{method:'PUT',body}));
  this.metadataQueue=next;return next;
 }
}

export async function discover(){
 const response=await fetch('/api/config',{signal:AbortSignal.timeout(10000)});
 if(response.status===404)return null; // Isolated --demo server, not an API outage.
 if(!response.ok)throw Error('The studio backend is unavailable. Reload to reconnect.');
 const config=await response.json();if(config.mode!=='live'||typeof config.key!=='string')throw Error('Invalid studio configuration.');
 return new Backend(config);
}
