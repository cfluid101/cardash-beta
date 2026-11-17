// Explicit ui=5 opts into the new label and release note. Older URLs keep Viewer 4.
(() => {
 const current=new URL(window.location.href).searchParams.get('ui')==='5';
 const release=document.querySelector('#releaseInfo');if(release)release.hidden=!current;
 const script=document.createElement('script');
 script.src=current?'./assets/https3/client.351827b1b5af1686.js':'./assets/https3/client.8c4c1cd03b048e61.js';
 script.async=false;
 script.onerror=()=>{const status=document.querySelector('#status');if(status)status.textContent='Viewer files could not load. Refresh this page.';};
 document.body.appendChild(script);
})();
