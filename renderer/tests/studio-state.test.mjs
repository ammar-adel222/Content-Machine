import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState,restore,createProject,progress,finishRuns,applyEdit,filterProjects,analytics,escapeHTML,platforms} from '../../war_studio/web/state.mjs';

test('studio storage restores valid drafts and rejects corrupt or incomplete state',()=>{
 const state=initialState();assert.deepEqual(restore(JSON.stringify(state)),state);
 for(const raw of ['',null,'{}','{"version":1,"projects":[null]}','{"version":1,"projects":{}}'])assert.deepEqual(restore(raw),initialState());
 for(const change of [p=>delete p.metadata.youtube.title,p=>p.status='unknown',p=>p.revision=0,p=>p.selectedPlatforms=['bad'],p=>p.edits=[null],p=>p.history=[null],p=>{p.status='generating';p.started='invalid';}]){
  const broken=initialState();change(broken.projects[0]);assert.deepEqual(restore(JSON.stringify(broken)),initialState());
 }
 assert.equal(escapeHTML('<img onerror="x">&'), '&lt;img onerror=&quot;x&quot;&gt;&amp;');
});
test('optional topic, formats and elapsed-time demo progress survive reloads',()=>{
 const p=createProject({},'test',1000);assert.equal(p.topic,'');assert.equal(p.title,'Researcher’s choice');assert.equal(p.format,'portrait');
 assert.equal(progress(p,999).percent,0);assert.equal(progress(p,3300).index,1);
 const state={version:1,projects:[p]};const restored=restore(JSON.stringify(state));
 assert.equal(finishRuns(restored,20000),true);assert.equal(restored.projects[0].status,'ready');assert.equal(finishRuns(restored,20001),false);
 assert.equal(createProject({topic:'  River crossing  ',kind:'war',format:'landscape'},'b',0).title,'River crossing');
 for(const input of [{kind:'bad'},{format:'square'},{topic:'x'.repeat(301)}])assert.throws(()=>createProject(input,'bad'));
});
test('edits preserve prior revisions, validate instructions and block overlapping runs',()=>{
 const p=initialState().projects[0];const metadata=structuredClone(p.metadata);
 for(const text of ['', ' ', 'x'.repeat(5001)])assert.throws(()=>applyEdit(p,'General',text));
 assert.throws(()=>applyEdit(p,'bad','hello'));
 applyEdit(p,'Map & units','  Follow the river  ',1000);
 assert.equal(p.revision,2);assert.equal(p.history[0].revision,1);assert.equal(p.edits[0].text,'Follow the river');
 assert.deepEqual(p.metadata,metadata);assert.throws(()=>applyEdit(p,'General','another edit'));
 assert.equal(progress(p,1000).index,0);
});
test('library filtering and platform/video/period analytics use consistent totals',()=>{
 const projects=initialState().projects;assert.equal(filterProjects(projects,'AUSTERLITZ','ready').length,1);assert.equal(filterProjects(projects,'missing').length,0);
 const all=analytics();assert.equal(all.views,platforms.reduce((n,platform)=>n+analytics({platform}).views,0));
 assert.equal(all.views,all.rows.reduce((n,r)=>n+r.views,0));assert.equal(analytics({video:'austerlitz'}).rows.length,1);
 assert.ok(analytics({period:7}).views<all.views);assert.ok(analytics({period:'90'}).views>all.views);
 assert.equal(analytics({video:'missing'}).engagement,0);assert.deepEqual(analytics({video:'missing'}).rows,[]);
 for(const input of [{platform:'bad'},{period:'2'}])assert.throws(()=>analytics(input));
});
