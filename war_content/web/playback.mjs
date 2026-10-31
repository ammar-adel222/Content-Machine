import {clamp} from './motion.mjs';
export function connectPlayback(data,app,render) {
 let time=0,playing=false,last=performance.now(),generation=0;
 const seek=document.getElementById('seek'),button=document.getElementById('play');seek.max=data.duration;
 const mute=document.getElementById('mute');
 let audio=null;
 if(data.soundtrack){
  if(data.soundtrack.file!=='soundtrack.wav')throw Error('Unsupported soundtrack filename.');
  audio=new Audio(data.soundtrack.file);audio.preload='auto';
  audio.addEventListener('error',()=>{document.getElementById('error').textContent='Soundtrack unavailable. Check the audio file in this bundle.';});
  if(mute){mute.hidden=false;mute.setAttribute('aria-label','Mute sound');mute.onclick=()=>{audio.muted=!audio.muted;mute.textContent=audio.muted?'Unmute':'Mute';mute.setAttribute('aria-label',audio.muted?'Unmute sound':'Mute sound');};}
  const note=document.querySelector('small');if(note)note.textContent=note.textContent.replace('silent preview',data.soundtrack.has_narration?'narration + sound effects':'sound effects');
 }
 function drawAt(seconds) {
  time=clamp(seconds,0,data.duration);render(time);seek.value=time;
  document.getElementById('time').textContent=`${Math.floor(time/60)}:${String(Math.floor(time%60)).padStart(2,'0')}`;
 }
 function pause(){generation++;playing=false;audio?.pause();button.textContent='Play';}
 function renderAt(seconds){pause();drawAt(seconds);if(audio)audio.currentTime=time;}
 seek.addEventListener('input',()=>renderAt(Number(seek.value)));
 button.onclick=async()=>{
  if(playing){pause();return;}
  if(time>=data.duration)drawAt(0);
  const pending=++generation;button.disabled=true;
  try{if(audio){audio.currentTime=time;await audio.play();}}
  catch{document.getElementById('error').textContent='Audio playback failed. You can still inspect the map.';}
  finally{button.disabled=false;}
  if(pending!==generation){audio?.pause();return;}
  last=performance.now();playing=true;button.textContent='Pause';
 };
 function tick(now){if(playing){drawAt(audio&&!audio.paused?audio.currentTime:time+(now-last)/1000);if(time>=data.duration)pause();}last=now;requestAnimationFrame(tick);}
 globalThis.contentEngine={renderAt,data,app,audio};drawAt(0);globalThis.contentReady=true;
 button.disabled=false;seek.disabled=false;requestAnimationFrame(tick);
}
