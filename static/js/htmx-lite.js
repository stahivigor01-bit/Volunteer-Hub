(function(){
  let latestRequest=0;
  function serialize(form){return new URLSearchParams(new FormData(form)).toString()}
  async function submit(el){
    const target=document.querySelector(el.getAttribute('hx-target'));
    if(!target)return;
    const requestId=++latestRequest;
    const url=el.getAttribute('hx-get')+'?'+serialize(el);
    target.setAttribute('aria-busy','true');
    try{
      const res=await fetch(url,{headers:{'HX-Request':'true'}});
      const html=await res.text();
      if(window.volunteerHubImages && window.volunteerHubImages.primeHtmlImages){
        await window.volunteerHubImages.primeHtmlImages(html,{limit:18});
      }
      if(requestId!==latestRequest)return;
      target.innerHTML=html;
      target.dispatchEvent(new CustomEvent('htmx:afterSwap',{bubbles:true}));
    }catch(e){
      if(requestId===latestRequest)target.removeAttribute('aria-busy');
      return;
    }
    target.removeAttribute('aria-busy');
  }
  document.addEventListener('submit',e=>{const f=e.target.closest('[hx-get]');if(f){e.preventDefault();submit(f)}});
  document.addEventListener('change',e=>{const f=e.target.closest('form[hx-get]');if(f)submit(f)});
  let timer;document.addEventListener('keyup',e=>{const f=e.target.closest('form[hx-get]');if(f&&e.target.matches('input[name="q"]')){clearTimeout(timer);timer=setTimeout(()=>submit(f),450)}});
})();
