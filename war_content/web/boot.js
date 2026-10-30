// Classic bootstrap also runs on file://, where browser module loading is blocked.
(() => {
  const button=document.getElementById('play'),seek=document.getElementById('seek');
  button.disabled=true;seek.disabled=true;
  function fail(message){
    globalThis.contentError=message;
    document.getElementById('screen').textContent='Preview unavailable';
    document.getElementById('error').textContent=message;
  }
  if(location.protocol==='file:'){
    fail('Open the generated map using preview.cmd in the project folder, or run:\npython -m war_content.play\n\nThis file is a player template; opening it directly does not load a generated scene.');
    return;
  }
  const script=document.createElement('script');script.src='pixi.min.js';
  script.onerror=()=>fail('The map runtime is missing. Open a ready generated build using preview.cmd or python -m war_content.play.');
  script.onload=()=>import('./player.mjs').catch(()=>fail('The map player could not load. Restart the preview using preview.cmd or python -m war_content.play.'));
  document.head.appendChild(script);
})();
