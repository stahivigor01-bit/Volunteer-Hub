(function(){
  function openModal(id){
    const modal=document.getElementById(id);
    if(modal){
      if(modal.parentElement!==document.body){
        document.body.appendChild(modal);
      }
      modal.classList.add('is-open');
      modal.setAttribute('aria-hidden','false');
      document.body.classList.add('modal-open');
      const first=modal.querySelector('input,textarea,select,button');
      if(first)first.focus();
    }
  }

  function closeModal(modal){
    if(!modal)return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden','true');
    if(!document.querySelector('.modal.is-open')){
      document.body.classList.remove('modal-open');
    }
  }

  let pendingConfirmForm=null;

  function openConfirm(form){
    const dialog=document.getElementById('confirm-dialog');
    if(!dialog)return false;
    pendingConfirmForm=form;
    const title=dialog.querySelector('#confirm-title');
    const message=dialog.querySelector('#confirm-message');
    const accept=dialog.querySelector('[data-confirm-accept]');
    if(title)title.textContent=form.dataset.confirmTitle || 'Підтвердити дію';
    if(message)message.textContent=form.dataset.confirmMessage || 'Цю дію буде виконано одразу після підтвердження.';
    if(accept)accept.textContent=form.dataset.confirmAction || 'Підтвердити';
    dialog.classList.add('is-open');
    dialog.setAttribute('aria-hidden','false');
    if(accept)accept.focus();
    return true;
  }

  function closeConfirm(){
    const dialog=document.getElementById('confirm-dialog');
    if(!dialog)return;
    dialog.classList.remove('is-open');
    dialog.setAttribute('aria-hidden','true');
    pendingConfirmForm=null;
  }

  function syncNativeSelect(wrapper){
    const select=wrapper.querySelector('select');
    const trigger=wrapper.querySelector('.custom-select-trigger');
    const selected=select.options[select.selectedIndex];
    trigger.textContent=selected ? selected.textContent : 'Оберіть значення';
    wrapper.querySelectorAll('.custom-select-option').forEach(function(option){
      option.classList.toggle('is-selected', option.dataset.value === select.value);
      option.setAttribute('aria-selected', option.dataset.value === select.value ? 'true' : 'false');
    });
  }

  function buildCustomSelect(select){
    if(select.multiple || select.closest('.custom-select') || select.dataset.nativeSelect === '1')return;
    select.dataset.nativeSelect='1';
    const wrapper=document.createElement('div');
    wrapper.className='custom-select';
    const trigger=document.createElement('button');
    trigger.className='custom-select-trigger';
    trigger.type='button';
    trigger.setAttribute('aria-haspopup','listbox');
    const menu=document.createElement('div');
    menu.className='custom-select-menu';
    menu.setAttribute('role','listbox');

    Array.from(select.options).forEach(function(option){
      const button=document.createElement('button');
      button.type='button';
      button.className='custom-select-option';
      button.dataset.value=option.value;
      button.textContent=option.textContent;
      button.disabled=option.disabled;
      button.setAttribute('role','option');
      button.addEventListener('click',function(){
        select.value=option.value;
        select.dispatchEvent(new Event('change',{bubbles:true}));
        wrapper.classList.remove('is-open');
        syncNativeSelect(wrapper);
        trigger.focus();
      });
      menu.appendChild(button);
    });

    select.parentNode.insertBefore(wrapper,select);
    wrapper.appendChild(select);
    wrapper.appendChild(trigger);
    wrapper.appendChild(menu);
    select.classList.add('custom-select-native');
    trigger.addEventListener('click',function(){
      document.querySelectorAll('.custom-select.is-open').forEach(function(open){
        if(open!==wrapper)open.classList.remove('is-open');
      });
      wrapper.classList.toggle('is-open');
    });
    select.addEventListener('change',function(){syncNativeSelect(wrapper);});
    syncNativeSelect(wrapper);
  }

  function initCustomSelects(root){
    root.querySelectorAll('select.form-control:not([multiple])').forEach(buildCustomSelect);
  }

  function createPhotoCard(label,text){
    const figure=document.createElement('figure');
    figure.className='photo-preview-card is-empty';
    const img=document.createElement('img');
    img.alt=label;
    const empty=document.createElement('div');
    empty.className='photo-preview-empty';
    empty.textContent=text;
    const caption=document.createElement('figcaption');
    caption.textContent=label;
    figure.appendChild(img);
    figure.appendChild(empty);
    figure.appendChild(caption);
    return {figure,img,empty};
  }

  function setPhotoPreview(card,url){
    if(!url)return;
    card.img.decoding='async';
    card.img.loading='eager';
    warmImage(url);
    card.img.src=url;
    card.figure.classList.remove('is-empty');
  }

  function buildPhotoUpload(input){
    if(input.dataset.photoWidget==='1')return;
    input.dataset.photoWidget='1';
    const field=input.closest('.field-block') || input.parentNode;
    field.classList.add('photo-field');
    const form=field.closest('form');

    const widget=document.createElement('div');
    widget.className='photo-upload-widget';
    const grid=document.createElement('div');
    grid.className='photo-preview-grid';
    const hasCurrentPhoto=!!input.dataset.currentUrl;
    const currentCard=hasCurrentPhoto ? createPhotoCard('Поточне фото','') : null;
    const nextCard=createPhotoCard(hasCurrentPhoto ? 'Нове фото' : 'Фото','Оберіть фотографію');
    const controls=document.createElement('div');
    controls.className='photo-upload-controls';
    const button=document.createElement('button');
    button.type='button';
    button.className='btn btn-ghost photo-upload-button';
    button.textContent='Обрати фото';
    const filename=document.createElement('span');
    filename.className='photo-upload-filename';
    filename.textContent='Файл не вибрано';
    const removeInput=form ? form.querySelector('[data-photo-remove-for="'+input.name+'"]') : null;

    if(currentCard){
      setPhotoPreview(currentCard,input.dataset.currentUrl);
      grid.appendChild(currentCard.figure);
    }
    grid.appendChild(nextCard.figure);
    controls.appendChild(button);
    controls.appendChild(filename);
    if(removeInput){
      const removeField=removeInput.closest('.field-block');
      const removeLabel=document.createElement('label');
      removeLabel.className='photo-remove-control';
      removeLabel.appendChild(removeInput);
      removeLabel.appendChild(document.createTextNode('Видалити поточне фото'));
      controls.appendChild(removeLabel);
      if(removeField)removeField.classList.add('is-relocated-field');
    }
    widget.appendChild(grid);
    widget.appendChild(controls);
    input.parentNode.insertBefore(widget,input);

    button.addEventListener('click',function(e){
      e.preventDefault();
      input.click();
    });
    input.addEventListener('change',function(){
      const file=input.files && input.files[0];
      if(!file)return;
      if(input.dataset.previewUrl)URL.revokeObjectURL(input.dataset.previewUrl);
      const previewUrl=URL.createObjectURL(file);
      input.dataset.previewUrl=previewUrl;
      setPhotoPreview(nextCard,previewUrl);
      filename.textContent=file.name;
    });
  }

  function initPhotoUploads(root){
    root.querySelectorAll('input[type="file"][data-photo-upload="1"]').forEach(buildPhotoUpload);
  }

  function buildFileUpload(input){
    if(input.dataset.fileWidget==='1')return;
    input.dataset.fileWidget='1';
    const field=input.closest('.field-block') || input.parentNode;
    field.classList.add('file-field');

    const widget=document.createElement('div');
    widget.className='file-upload-widget';
    const button=document.createElement('button');
    button.type='button';
    button.className='btn btn-ghost file-upload-button';
    button.textContent='Обрати файл';
    const filename=document.createElement('span');
    filename.className='file-upload-filename';
    filename.textContent='Файл не вибрано';

    widget.appendChild(button);
    widget.appendChild(filename);
    input.parentNode.insertBefore(widget,input);

    button.addEventListener('click',function(e){
      e.preventDefault();
      input.click();
    });
    input.addEventListener('change',function(){
      const file=input.files && input.files[0];
      filename.textContent=file ? file.name : 'Файл не вибрано';
    });
  }

  function initFileUploads(root){
    root.querySelectorAll('input[type="file"][data-file-upload="1"]').forEach(buildFileUpload);
  }

  function readShiftAvailabilityData(){
    const script=document.getElementById('shift-availability-data');
    if(!script)return {};
    try{return JSON.parse(script.textContent || '{}');}catch(e){return {};}
  }

  function initShiftAvailability(root){
    const panel=document.querySelector('[data-shift-availability]');
    const list=panel ? panel.querySelector('[data-shift-availability-list]') : null;
    const select=document.querySelector('select[name="initiative"]');
    const dateInput=document.querySelector('input[name="shift_date"]');
    if(!panel || !list || !select || panel.dataset.shiftAvailabilityReady==='1')return;
    panel.dataset.shiftAvailabilityReady='1';
    const data=readShiftAvailabilityData();

    function formatDateValue(value){
      if(!value)return '';
      const parts=String(value).split('-');
      if(parts.length!==3)return value;
      return parts[2]+'.'+parts[1]+'.'+parts[0];
    }

    function render(){
      const initiativeId=select.value;
      list.innerHTML='';
      if(!initiativeId){
        panel.hidden=true;
        return;
      }
      panel.hidden=false;
      const selectedDate=formatDateValue(dateInput ? dateInput.value : '');
      const allRows=data[initiativeId] || [];
      const rows=selectedDate ? allRows.filter(function(item){return item.date===selectedDate;}) : allRows;
      if(!rows.length){
        const empty=document.createElement('div');
        empty.className='shift-availability-empty';
        empty.textContent=selectedDate ? 'На цю дату для ініціативи ще немає зайнятих годин.' : 'Для цієї ініціативи ще немає запланованих змін.';
        list.appendChild(empty);
        return;
      }
      rows.forEach(function(item){
        const row=document.createElement('div');
        row.className='shift-availability-row';

        const main=document.createElement('span');
        const title=document.createElement('b');
        title.textContent=item.title || 'Зміна';
        const meta=document.createElement('small');
        meta.textContent=[item.date,item.location].filter(Boolean).join(' · ');
        main.appendChild(title);
        main.appendChild(meta);

        const time=document.createElement('strong');
        time.textContent=(item.start || '--:--') + '–' + (item.end || '--:--');

        const status=document.createElement('em');
        status.textContent=item.status || '';

        row.appendChild(main);
        row.appendChild(time);
        row.appendChild(status);
        list.appendChild(row);
      });
    }

    select.addEventListener('change',render);
    if(dateInput)dateInput.addEventListener('change',render);
    render();
  }

  const imageCache=new Map();
  const pageImageCache=new Map();

  function normalizeImageUrl(value){
    if(!value)return '';
    const raw=String(value).trim().replace(/^['"]|['"]$/g,'');
    if(!raw || raw.startsWith('data:') || raw.startsWith('blob:') || raw==='#')return '';
    try{return new URL(raw,window.location.href).href;}catch(e){return '';}
  }

  function extractStyleImageUrls(styleText){
    const urls=[];
    if(!styleText)return urls;
    const pattern=/url\(([^)]+)\)/g;
    let match;
    while((match=pattern.exec(styleText))!==null){
      const url=normalizeImageUrl(match[1]);
      if(url)urls.push(url);
    }
    return urls;
  }

  function collectImageUrls(root){
    const urls=[];
    root.querySelectorAll('img[src]').forEach(function(img){
      const url=normalizeImageUrl(img.currentSrc || img.getAttribute('src'));
      if(url)urls.push(url);
    });
    root.querySelectorAll('[style*="url("]').forEach(function(node){
      extractStyleImageUrls(node.getAttribute('style')).forEach(function(url){urls.push(url);});
    });
    return Array.from(new Set(urls));
  }

  function hintImages(root){
    root.querySelectorAll('img[src]').forEach(function(img,index){
      if(!img.hasAttribute('decoding'))img.setAttribute('decoding','async');
      if(!img.hasAttribute('loading'))img.setAttribute('loading','eager');
      if(index<4 && !img.hasAttribute('fetchpriority'))img.setAttribute('fetchpriority','high');
      if(img.complete && img.naturalWidth>0){
        img.dataset.imageReady='1';
      }else{
        img.addEventListener('load',function(){img.dataset.imageReady='1';},{once:true});
      }
    });
  }

  function warmImage(value){
    const url=normalizeImageUrl(value);
    if(!url)return Promise.resolve();
    if(imageCache.has(url))return imageCache.get(url);
    const img=new Image();
    img.decoding='async';
    img.loading='eager';
    const promise=new Promise(function(resolve){
      let settled=false;
      const finish=function(){
        if(settled)return;
        settled=true;
        window.clearTimeout(timer);
        resolve();
      };
      const timer=window.setTimeout(finish,4500);
      img.onload=function(){
        if(img.decode){
          img.decode().catch(function(){}).finally(finish);
        }else{
          finish();
        }
      };
      img.onerror=finish;
    });
    img.src=url;
    imageCache.set(url,promise);
    return promise;
  }

  function primeImages(root,options){
    const opts=options || {};
    hintImages(root);
    let urls=collectImageUrls(root);
    if(typeof opts.limit==='number')urls=urls.slice(0,opts.limit);
    return Promise.allSettled(urls.map(warmImage));
  }

  function primeHtmlImages(html,options){
    if(!html || typeof DOMParser==='undefined')return Promise.resolve();
    const doc=new DOMParser().parseFromString(html,'text/html');
    return primeImages(doc,options);
  }

  function isImagePageLink(anchor){
    if(!anchor || !anchor.href || anchor.target || anchor.hasAttribute('download'))return false;
    let url;
    try{url=new URL(anchor.href,window.location.href);}catch(e){return false;}
    if(url.origin!==window.location.origin)return false;
    const path=url.pathname;
    return path==='/' || path==='/initiatives/' || path.startsWith('/initiatives/') || path==='/organizations/' || path.startsWith('/organizations/');
  }

  function primeLinkedPage(anchor){
    if(!isImagePageLink(anchor))return;
    const url=new URL(anchor.href,window.location.href);
    const key=url.pathname + url.search;
    if(pageImageCache.has(key))return pageImageCache.get(key);
    const promise=fetch(url.href,{credentials:'same-origin',headers:{'X-Image-Prefetch':'1'}})
      .then(function(response){
        const type=response.headers.get('content-type') || '';
        if(!response.ok || !type.includes('text/html'))return;
        return response.text();
      })
      .then(function(html){
        if(html)return primeHtmlImages(html,{limit:18});
      })
      .catch(function(){});
    pageImageCache.set(key,promise);
    return promise;
  }

  function scheduleImageWarmup(root){
    primeImages(root,{limit:18});
    const idle=window.requestIdleCallback || function(callback){return setTimeout(callback,120);};
    idle(function(){primeImages(root);});
  }

  function targetElement(target){
    if(!target)return null;
    if(target.nodeType===1)return target;
    return target.parentElement || null;
  }

  function closestFromTarget(target,selector){
    const element=targetElement(target);
    return element && element.closest ? element.closest(selector) : null;
  }

  function matchesTarget(target,selector){
    const element=targetElement(target);
    return !!(element && element.matches && element.matches(selector));
  }

  document.addEventListener('click',function(e){
    const clickTarget=targetElement(e.target);
    const opener=closestFromTarget(e.target,'[data-open-modal]');
    if(opener){
      e.preventDefault();
      openModal(opener.dataset.openModal);
    }
    if(matchesTarget(e.target,'[data-close-modal]'))closeModal(closestFromTarget(e.target,'.modal'));
    if(clickTarget && clickTarget.classList.contains('modal'))closeModal(clickTarget);
    if(matchesTarget(e.target,'[data-confirm-cancel]') || (clickTarget && clickTarget.id==='confirm-dialog')){
      e.preventDefault();
      closeConfirm();
    }
    if(matchesTarget(e.target,'[data-confirm-accept]')){
      e.preventDefault();
      const form=pendingConfirmForm;
      closeConfirm();
      if(form){
        form.dataset.confirmed='1';
        form.submit();
      }
    }
    if(!closestFromTarget(e.target,'.custom-select')){
      document.querySelectorAll('.custom-select.is-open').forEach(function(select){select.classList.remove('is-open');});
    }
    const imageLink=closestFromTarget(e.target,'a');
    if(imageLink)primeLinkedPage(imageLink);
  });

  document.addEventListener('pointerenter',function(e){
    primeLinkedPage(closestFromTarget(e.target,'a'));
  },true);

  document.addEventListener('focusin',function(e){
    primeLinkedPage(closestFromTarget(e.target,'a'));
  });

  document.addEventListener('touchstart',function(e){
    primeLinkedPage(closestFromTarget(e.target,'a'));
  },{passive:true});

  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
      document.querySelectorAll('.modal.is-open').forEach(closeModal);
      document.querySelectorAll('.custom-select.is-open').forEach(function(select){select.classList.remove('is-open');});
      closeConfirm();
    }
  });

  document.addEventListener('submit',function(e){
    const form=closestFromTarget(e.target,'form[data-confirm]');
    if(!form || form.dataset.confirmed==='1')return;
    if(openConfirm(form))e.preventDefault();
  });

  document.addEventListener('DOMContentLoaded',function(){
    initCustomSelects(document);
    initPhotoUploads(document);
    initFileUploads(document);
    initShiftAvailability(document);
    scheduleImageWarmup(document);
    setTimeout(function(){document.querySelectorAll('.toast').forEach(function(t){t.style.display='none';});},5200);
  });

  document.addEventListener('htmx:afterSwap',function(e){
    initCustomSelects(e.target);
    initPhotoUploads(e.target);
    initFileUploads(e.target);
    initShiftAvailability(e.target);
    scheduleImageWarmup(e.target);
  });
  window.volunteerHubImages={primeImages:primeImages,primeHtmlImages:primeHtmlImages,warmImage:warmImage};
  window.syncNativeSelect=syncNativeSelect;
})();
