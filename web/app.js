'use strict';
const $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const names={ready:'Ready',planned:'Plan ready',applied:'Copies created',undone:'Recovered'};
function render(data){
 $('phase').textContent=names[data.phase];$('plan').disabled=data.phase==='applied';$('apply').disabled=data.phase!=='planned';$('undo').disabled=data.phase!=='applied';
 $('inbox').replaceChildren();
 for(const f of data.files){const row=el('article',undefined,'file');row.append(el('span',f.name,'file-name'),el('p',f.excerpt),el('span',f.duplicate_of?'duplicate → '+f.duplicate_of:f.topic,'folder'));const details=el('details');details.append(el('summary',f.reason+' · inspect scores'),el('p','Nearest topic: '+f.suggestion+' / cosine '+f.score+' / top-two gap '+f.gap+'. These values are not probabilities.'));row.append(details);$('inbox').append(row);}
 const copies=data.files.filter(f=>!f.duplicate_of);const review=copies.filter(f=>f.topic==='_review');$('summary').hidden=!data.files.length;$('summary').replaceChildren();
 for(const text of [data.files.length+' originals unchanged',copies.length+' unique copies planned',review.length+' copies need a look',data.files.filter(f=>f.duplicate_of).length+' exact duplicate references'])$('summary').append(el('span',text));
 if(data.phase==='planned')$('status').textContent='Plan ready in '+data.elapsed_ms+' ms. Inspect the proposed folders, then choose whether to create copies.';
 if(data.phase==='applied')$('status').textContent='Created '+data.result.copied+' copies. '+data.result.duplicates+' duplicates reference their canonical copies. Original files are unchanged.';
 if(data.phase==='undone')$('status').textContent='Run moved to recovery. Zero files deleted; the originals and organized copies are both retained.';
}
async function act(action){for(const id of ['plan','apply','undo'])$(id).disabled=true;$('status').textContent='Working locally…';try{const res=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await res.json();if(!res.ok)throw new Error(data.error);render(data);}catch(e){$('status').textContent=e.message;try{const state=await(await fetch('/api/state')).json();render(state);$('status').textContent=e.message;}catch{$('plan').disabled=false;}}}
for(const id of ['plan','apply','undo'])$(id).onclick=()=>act(id);
fetch('/api/state').then(r=>r.json()).then(render).catch(()=>{$('status').textContent='The local demo is unavailable. Start server.py and reload.';});
