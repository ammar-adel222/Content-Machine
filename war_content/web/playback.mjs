import {clamp} from './motion.mjs';
export function connectPlayback(data,app,render) {
 let time=0,playing=false,last=performance.now();
 const seek=document.getElementById('seek'),button=document.getElementById('play');seek.max=data.duration;
 function renderAt(seconds) {
  time=clamp(seconds,0,data.duration);render(time);seek.value=time;
  document.getElementById('time').textContent=`${Math.floor(time/60)}:${String(Math.floor(time%60)).padStart(2,'0')}`;
 }
 seek.addEventListener('input',()=>{playing=false;button.textContent='Play';renderAt(Number(seek.value));});
 button.onclick=()=>{if(time>=data.duration)time=0;playing=!playing;button.textContent=playing?'Pause':'Play';};
 function tick(now){if(playing){renderAt(time+(now-last)/1000);if(time>=data.duration){playing=false;button.textContent='Play';}}last=now;requestAnimationFrame(tick);}
 globalThis.contentEngine={renderAt,data,app};renderAt(0);globalThis.contentReady=true;
 button.disabled=false;seek.disabled=false;requestAnimationFrame(tick);
}
