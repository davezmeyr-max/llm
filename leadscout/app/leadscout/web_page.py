"""Static HTML for the portal. All lead data is rendered with textContent (never innerHTML):
profiles contain text scraped from the open web."""

_STYLE = r"""
:root{--bg:#f6f7f9;--card:#fff;--ink:#16191d;--muted:#5d6670;--line:#e3e6ea;--accent:#1f5eff;--accent-ink:#fff;
--ok:#137a3f;--okbg:#e5f5ec;--warn:#8a5a00;--warnbg:#fff4dc;--bad:#a5231b;--badbg:#fde8e6;--chip:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--card:#171b21;--ink:#e8ebef;--muted:#9aa4af;--line:#2a3038;
--accent:#5b8cff;--accent-ink:#0b0d10;--ok:#6fd49a;--okbg:#14301f;--warn:#f0c160;--warnbg:#33280f;--bad:#ff8a80;
--badbg:#3a1714;--chip:#222831}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
a{color:var(--accent)}header{display:flex;align-items:center;justify-content:space-between;gap:12px;
padding:14px 24px;border-bottom:1px solid var(--line);background:var(--card)}
header h1{font-size:17px;margin:0;font-weight:650;letter-spacing:-.01em}header .sub{color:var(--muted);font-size:13px}
main{max-width:1280px;margin:0 auto;padding:20px 16px;display:grid;grid-template-columns:340px 1fr;gap:18px}
@media (max-width:860px){main{grid-template-columns:minmax(0,1fr)}}
main>*{min-width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h2{font-size:14px;margin:0 0 12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
label{display:block;font-size:13px;color:var(--muted);margin:10px 0 4px}
input,textarea,select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);
color:var(--ink);font:inherit}textarea{min-height:110px;resize:vertical}
button{padding:9px 14px;border:0;border-radius:8px;background:var(--accent);color:var(--accent-ink);font:inherit;
font-weight:600;cursor:pointer}button.ghost{background:transparent;color:var(--accent);border:1px solid var(--line)}
button:disabled{opacity:.5;cursor:default}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.banner{grid-column:1/-1;padding:10px 14px;border-radius:10px;font-size:14px}
.banner.on{background:var(--okbg);color:var(--ok)}.banner.off{background:var(--warnbg);color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:var(--muted);font-weight:600;
font-size:12px;text-transform:uppercase;letter-spacing:.05em;padding:8px;border-bottom:1px solid var(--line)}
td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}tr.click{cursor:pointer}
tr.click:hover td{background:var(--chip)}.chip{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;
background:var(--chip);color:var(--muted);font-weight:600}.chip.done{background:var(--okbg);color:var(--ok)}
.chip.failed{background:var(--badbg);color:var(--bad)}.chip.running{background:var(--warnbg);color:var(--warn)}
.muted{color:var(--muted)}.small{font-size:12px}.msg{font-size:13px;margin-top:8px;min-height:18px}
.err{color:var(--bad)}.tablewrap{overflow-x:auto}
#detail{position:fixed;inset:0;background:rgba(0,0,0,.35);display:none;align-items:flex-start;justify-content:center;
padding:40px 16px;overflow:auto}#detail .panel{background:var(--card);border-radius:14px;max-width:860px;width:100%;
padding:22px;border:1px solid var(--line)}#detail h3{margin:0 0 4px;font-size:20px}
#detail h4{margin:20px 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
dl{display:grid;grid-template-columns:170px 1fr;gap:6px 14px;margin:0}dt{color:var(--muted)}dd{margin:0;word-break:break-word}
ul{margin:0;padding-left:18px}.login{max-width:360px;margin:12vh auto}
"""

LOGIN_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lead Research – Sign in</title>
<style>""" + _STYLE + r"""</style></head><body>
<div class="card login"><h2>Lead Research</h2>
<p class="muted small">Open Lead Research from the CIS portal to sign in automatically. Administrators can sign in
with the server password.</p>
<label for="pw">Admin password</label><input id="pw" type="password" autocomplete="current-password">
<div class="row" style="margin-top:12px"><button id="go">Sign in</button></div><div id="m" class="msg err"></div></div>
<script>
const go=document.getElementById('go'),pw=document.getElementById('pw'),m=document.getElementById('m');
async function signin(){go.disabled=true;m.textContent='';
 const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'leadscout'},
  body:JSON.stringify({password:pw.value})});
 if(r.ok){location.href='/';return}
 m.textContent=r.status===429?'Too many attempts. Try again later.':'Sign-in failed.';go.disabled=false}
go.onclick=signin;pw.onkeydown=e=>{if(e.key==='Enter')signin()};
</script></body></html>"""

_DASH_STYLE = r"""
:root{--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--track:#e7e9ed}
@media (prefers-color-scheme:dark){:root{--track:#2a3038}}
.gauges{grid-column:1/-1;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}
@media (max-width:1100px){.gauges{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:640px){.gauges{grid-template-columns:repeat(2,minmax(0,1fr))}}
.gauge{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px 10px}
.gauge .t{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}
.gauge svg{display:block;width:100%;max-width:170px;margin:6px auto 0}
.gauge .v{font-size:22px;font-weight:650;text-align:center;margin-top:-30px;font-variant-numeric:tabular-nums}
.gauge .s{font-size:12px;color:var(--muted);text-align:center;margin-top:6px;min-height:32px}
.gauge .st{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.working{grid-column:1/-1;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;
font-size:14px;display:none}.working .w{display:flex;gap:10px;align-items:baseline;padding:3px 0}
.working .w b{font-weight:600}.side{display:flex;flex-direction:column;gap:18px}
.drop{border:1.5px dashed var(--line);border-radius:10px;padding:14px;text-align:center;color:var(--muted);font-size:13px}
.drop.over{border-color:var(--accent);color:var(--ink)}.step{font-size:12px;color:var(--muted);margin-top:3px}
"""

PORTAL_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lead Research</title>
<style>""" + _STYLE + _DASH_STYLE + r"""</style></head><body>
<header><div><h1>Lead Research</h1><div class="sub">Company background, registrations and leadership from public sources</div></div>
<div class="row"><span id="who" class="muted small"></span><a href="/logout" class="small">Sign out</a></div></header>
<main>
<div id="banner" class="banner off">Checking research engine…</div>
<div class="gauges" id="gauges"></div>
<div class="working" id="working"></div>
<div class="side">
<section class="card">
 <h2>Import a list</h2>
 <div class="drop" id="drop">Drop a CSV or Excel file here, or <a href="#" id="pick">choose a file</a>.<br>
  <span class="small">Needs a company column. City, state, website and industry columns are used as hints.</span></div>
 <input type="file" id="file" accept=".csv,.txt,.tsv,.xlsx,.xlsm" style="display:none">
 <label for="bname">Batch name (optional)</label><input id="bname" maxlength="100" placeholder="Defaults to the file name and date">
 <div class="row" style="margin-top:12px"><button id="upload" disabled>Import</button><span id="fname" class="small muted"></span></div>
 <div id="impmsg" class="msg"></div>
</section>
<section class="card">
 <h2>Add one or a few</h2>
 <label for="co">Company name</label><input id="co" placeholder="Joe Inc." maxlength="200">
 <label for="hi">Hints</label><input id="hi" placeholder="City, state, website, industry" maxlength="500">
 <label for="bulk">Or paste several, one per line: <span class="muted">Company | hints</span></label>
 <textarea id="bulk" placeholder="Acme Plumbing LLC | Naperville, IL&#10;Lakeshore Dental Group | Chicago"></textarea>
 <div class="row" style="margin-top:12px"><button id="add">Queue research</button></div>
 <div id="addmsg" class="msg"></div>
</section>
</div>
<section class="card">
 <div class="row" style="justify-content:space-between;margin-bottom:10px"><h2 style="margin:0">Leads</h2>
  <div class="row"><select id="batch" style="width:auto;max-width:240px"><option value="">All batches</option></select>
   <select id="filter" style="width:auto"><option value="">All statuses</option><option>queued</option>
   <option>running</option><option>done</option><option>failed</option></select>
   <button class="ghost" id="csv">Export CSV</button><button class="ghost" id="xlsx">Export Excel</button></div></div>
 <div class="small muted" style="margin:-4px 0 8px">Exports contain finished results only, for the selected batch.</div>
 <div class="tablewrap"><table><thead><tr><th>Company</th><th>Status</th><th>Confidence</th><th>Batch</th>
  <th>Updated</th><th></th></tr></thead><tbody id="rows"></tbody></table></div>
 <div id="empty" class="muted small" style="padding:12px 4px;display:none">No leads yet.</div>
</section>
</main>
<div id="detail"><div class="panel" id="panel"></div></div>
<script>
const $=id=>document.getElementById(id);
const H={'X-Requested-With':'leadscout'};
const SVG='http://www.w3.org/2000/svg';
function el(tag,props,...kids){const n=document.createElement(tag);
 for(const[k,v]of Object.entries(props||{})){if(k==='class')n.className=v;else if(k==='text')n.textContent=v;
  else if(k.startsWith('on'))n[k]=v;else n.setAttribute(k,v)}
 for(const k of kids.flat(Infinity)){if(k==null||k===false)continue;n.append(k instanceof Node?k:document.createTextNode(String(k)))}
 return n}
function sv(tag,attrs){const n=document.createElementNS(SVG,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n}
function safeUrl(u){return typeof u==='string'&&/^https?:\/\//i.test(u)?u:null}
function link(u,label){const s=safeUrl(u);return s?el('a',{href:s,target:'_blank',rel:'noopener noreferrer',text:label||s}):(u||'')}
async function api(path,opts){const r=await fetch(path,opts);
 if(r.status===401){location.href='/login';throw new Error('signed out')}
 if(!r.ok){let d='';try{d=(await r.json()).detail}catch(e){}throw new Error(typeof d==='string'&&d?d:('HTTP '+r.status))}
 return (r.headers.get('content-type')||'').includes('json')?r.json():r.text()}
function when(s){if(!s)return'';return new Date(s).toLocaleString()}
function dur(s){if(s==null)return'–';s=Math.round(s);if(s<60)return s+'s';const m=Math.floor(s/60);
 if(m<60)return m+'m '+(s%60)+'s';return Math.floor(m/60)+'h '+(m%60)+'m'}
function money(cur,v){if(v==null)return'–';return cur+(v<0.1?v.toFixed(3):v.toFixed(2))}

/* ---------- gauges: semicircular meter, same-hue track; status always shown as text + dot ---------- */
const STATUS={good:['var(--good)','Good'],warning:['var(--warning)','High'],serious:['var(--serious)','Slower'],critical:['var(--critical)','Critical']};
function arc(frac0,frac1){const r=70,cx=85,cy=82;const p=f=>{const a=Math.PI*(1-f);return[cx+r*Math.cos(a),cy-r*Math.sin(a)]};
 const[a,b]=[p(frac0),p(frac1)];return `M ${a[0]} ${a[1]} A ${r} ${r} 0 0 1 ${b[0]} ${b[1]}`}
function gauge(title,value,sub,opts){const o=Object.assign({frac:0,from:0,color:'var(--accent)',status:null},opts||{});
 const svg=sv('svg',{viewBox:'0 0 170 92','aria-hidden':'true'});
 svg.append(sv('path',{d:arc(0,1),fill:'none',stroke:'var(--track)','stroke-width':12,'stroke-linecap':'round'}));
 const lo=Math.max(0,Math.min(1,Math.min(o.from,o.frac))),hi=Math.max(0,Math.min(1,Math.max(o.from,o.frac)));
 if(hi-lo>0.004)svg.append(sv('path',{d:arc(lo,hi),fill:'none',stroke:o.color,'stroke-width':12,'stroke-linecap':'round'}));
 if(o.from>0)svg.append(sv('line',{x1:85,y1:6,x2:85,y2:20,stroke:'var(--muted)','stroke-width':2}));
 const st=o.status?el('div',{style:'text-align:center;margin-top:4px'},el('span',{class:'st'},
  el('span',{class:'dot',style:'background:'+STATUS[o.status[0]][0]}),o.status[1])):'';
 return el('div',{class:'gauge',title:title},el('div',{class:'t',text:title}),svg,el('div',{class:'v',text:value}),st,
  el('div',{class:'s',text:sub}))}

let dash=null;
async function loadDashboard(){const b=$('batch').value;
 try{dash=await api('/ui/api/dashboard'+(b?'?batch='+encodeURIComponent(b):''))}catch(e){return null}
 const d=dash,g=[],p=d.progress,e=d.engine,sv_=d.server,sp=d.speed,c=d.cost;
 // 1 progress
 const left=p.queued+p.running;
 g.push(gauge('Batch progress',p.total?Math.round(p.pct)+'%':'–',
  p.total?`${p.done} done · ${p.failed} failed · ${left} to go${sp.eta_s?' · ETA '+dur(sp.eta_s):''}`:'No batch yet',
  {frac:p.pct/100}));
 // 2 engine load (KV cache in use on the GPU)
 if(e.online){const kv=e.kv_cache_pct??0;
  g.push(gauge('Engine load',(e.kv_cache_pct==null?'–':Math.round(kv)+'%'),
   `${e.running??0} running · ${e.waiting??0} waiting · ${e.tokens_per_s??0} tok/s`,
   {frac:kv/100,color:kv>90?'var(--warning)':'var(--accent)',status:kv>90?['warning','Near capacity']:['good','Online']}))}
 else g.push(gauge('Engine load','Off','GPU model is not running',{frac:0,status:['critical','Offline']}));
 // 3 server load
 const cpu=sv_.cpu_pct??0;
 g.push(gauge('Server load',sv_.cpu_pct==null?'–':Math.round(cpu)+'%',
  `CPU load ${sv_.load1??'–'} on ${sv_.cpus??'–'} cores · memory ${sv_.mem_pct??'–'}%`,
  {frac:Math.min(cpu,100)/100,color:cpu>100?'var(--critical)':cpu>85?'var(--warning)':'var(--accent)',
   status:cpu>100?['critical','Overloaded']:cpu>85?['warning','Busy']:null}));
 // 4 speed vs normal (diverging around 0, clamped to ±100%)
 if(sp.deviation_pct!=null){const dv=sp.deviation_pct,f=0.5+Math.max(-100,Math.min(100,dv))/200;
  const st=dv>50?['critical','Much slower']:dv>20?['serious','Slower']:dv<-20?['good','Faster']:['good','Normal'];
  g.push(gauge('Speed vs normal',(dv>0?'+':'')+Math.round(dv)+'%',
   `last ${Math.min(5,sp.samples)} avg ${dur(sp.recent_s)} · normal ${dur(sp.normal_s)} · ${sp.per_hour}/hr`,
   {from:0.5,frac:f,color:dv>20?'var(--serious)':'var(--accent)',status:st}))}
 else g.push(gauge('Speed vs normal','–',sp.samples?`Learning normal speed: ${sp.need} more lead${sp.need>1?'s':''}`:'Needs finished leads',{from:0.5,frac:0.5}));
 // 5 cost estimate
 if(c.per_lead!=null){const frac=c.batch_estimate?c.batch_spent/c.batch_estimate:0;
  g.push(gauge('Est. cost',money(c.currency,c.per_lead),
   `per lead · batch ≈ ${money(c.currency,c.batch_estimate)} (${money(c.currency,c.batch_spent)} so far)`+
   (c.session_s!=null?` · GPU on ${dur(c.session_s)} ≈ ${money(c.currency,c.session_cost)}`:''),{frac:frac}))}
 else g.push(gauge('Est. cost','–',`GPU ${money(c.currency,c.rate_per_hour)}/hr`+
   (c.session_s!=null?` · on ${dur(c.session_s)} ≈ ${money(c.currency,c.session_cost)}`:'')+' · per-lead cost after first results',{frac:0}));
 $('gauges').replaceChildren(...g);
 // banner + working strip
 const bn=$('banner');bn.className='banner '+(e.online?'on':'off');
 bn.textContent=e.online?'Research engine online.':'Research engine offline: new leads wait in the queue and run when it starts.';
 const w=$('working');
 if(d.working.length){w.style.display='block';w.replaceChildren(...d.working.map(x=>el('div',{class:'w'},
   el('span',{class:'dot',style:'background:var(--accent)'}),el('b',{text:x.company}),
   el('span',{class:'muted',text:(x.step||'starting')+(x.elapsed_s!=null?' · '+dur(x.elapsed_s):'')}))))}
 else w.style.display='none';
 // batch options
 const sel=$('batch'),cur=sel.value,names=d.batches.map(x=>x.batch);
 if(sel.options.length-1!==names.length||names.some((n,i)=>sel.options[i+1].value!==n)){
  sel.replaceChildren(el('option',{value:'',text:'All batches'}),...d.batches.map(x=>el('option',{value:x.batch,
   text:`${x.batch} (${x.done}/${x.total})`})));sel.value=names.includes(cur)?cur:''}
 else d.batches.forEach((x,i)=>{sel.options[i+1].textContent=`${x.batch} (${x.done}/${x.total})`});
 return d}

async function loadMe(){const me=await api('/ui/api/me');$('who').textContent=me.name?`${me.name} · ${me.email}`:me.email}

async function loadLeads(){const f=$('filter').value,b=$('batch').value;const q=new URLSearchParams();
 if(f)q.set('status',f);if(b)q.set('batch',b);
 const rows=await api('/ui/api/leads'+(q.toString()?'?'+q:''));
 const tb=$('rows');tb.replaceChildren();$('empty').style.display=rows.length?'none':'block';
 for(const r of rows){
  const retry=r.status==='failed'?el('button',{class:'ghost',text:'Retry',onclick:async ev=>{ev.stopPropagation();
   await api(`/ui/api/leads/${r.id}/retry`,{method:'POST',headers:H});refresh()}}):'';
  const tr=el('tr',{class:r.status==='done'?'click':''},
   el('td',{},el('div',{text:r.company_name||r.company}),r.hints?el('div',{class:'muted small',text:r.hints}):'',
     r.status==='failed'&&r.error?el('div',{class:'small err',text:r.error.slice(0,160)}):''),
   el('td',{},el('span',{class:'chip '+r.status,text:r.status}),r.status==='running'&&r.step?el('div',{class:'step',text:r.step}):''),
   el('td',{text:r.confidence||''}),el('td',{class:'small muted',text:r.batch||''}),
   el('td',{class:'small muted',text:when(r.updated_at)}),el('td',{},retry));
  if(r.status==='done')tr.onclick=()=>openLead(r.id);tb.append(tr)}}

async function refresh(){const d=await loadDashboard();await loadLeads();
 clearTimeout(window._t);const busy=d&&((d.queue.queued||0)+(d.queue.running||0)>0);
 window._t=setTimeout(refresh,busy?5000:30000)}

/* ---------- import ---------- */
let picked=null;
function pickFile(f){picked=f;$('fname').textContent=f?`${f.name} · ${Math.max(1,Math.round(f.size/1024))} KB`:'';$('upload').disabled=!f;if(f)$('impmsg').textContent=''}
$('pick').onclick=ev=>{ev.preventDefault();$('file').click()};
$('file').onchange=()=>pickFile($('file').files[0]||null);
const drop=$('drop');
drop.ondragover=ev=>{ev.preventDefault();drop.classList.add('over')};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=ev=>{ev.preventDefault();drop.classList.remove('over');if(ev.dataTransfer.files[0])pickFile(ev.dataTransfer.files[0])};
function b64(buf){const u=new Uint8Array(buf);let s='';for(let i=0;i<u.length;i+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000));return btoa(s)}
$('upload').onclick=async()=>{if(!picked)return;const m=$('impmsg');m.className='msg';
 if(picked.size>5e6){m.className='msg err';m.textContent='File is larger than 5 MB.';return}
 $('upload').disabled=true;m.textContent='Importing…';
 try{const data=b64(await picked.arrayBuffer());
  const r=await api('/ui/api/import',{method:'POST',headers:{...H,'Content-Type':'application/json'},
   body:JSON.stringify({filename:picked.name,data_b64:data,batch:$('bname').value.trim()})});
  const notes=[];if(r.skipped)notes.push(`${r.skipped} row${r.skipped===1?'':'s'} without a company name`);
  if(r.duplicates)notes.push(`${r.duplicates} duplicate${r.duplicates===1?'':'s'}`);
  m.textContent=`Added ${r.added} lead${r.added===1?'':'s'} to “${r.batch}”. Company column: ${r.company_column}`+
   (r.hint_columns.length?`; hints from ${r.hint_columns.join(', ')}.`:'.')+
   (notes.length?` Skipped ${notes.join(' and ')}.`:'')+(r.truncated?' Only the first 5,000 rows were imported.':'');
  pickFile(null);$('file').value='';$('bname').value='';await loadDashboard();$('batch').value=r.batch;refresh()}
 catch(e){m.className='msg err';m.textContent=e.message;$('upload').disabled=false}};

/* ---------- manual add ---------- */
$('add').onclick=async()=>{const leads=[];const co=$('co').value.trim();
 if(co)leads.push({company:co,hints:$('hi').value.trim()});
 for(const line of $('bulk').value.split('\n')){const [c,...h]=line.split('|');
  if(c&&c.trim().length>=2)leads.push({company:c.trim().slice(0,200),hints:h.join('|').trim().slice(0,500)})}
 const m=$('addmsg');m.className='msg';
 if(!leads.length){m.className='msg err';m.textContent='Enter a company name.';return}
 $('add').disabled=true;
 try{const r=await api('/ui/api/leads',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify({leads})});
  m.textContent=`Queued ${r.ids.length} lead${r.ids.length>1?'s':''}.`;$('co').value='';$('hi').value='';$('bulk').value='';refresh()}
 catch(e){m.className='msg err';m.textContent=e.message}finally{$('add').disabled=false}};

$('filter').onchange=loadLeads;$('batch').onchange=refresh;
function exportUrl(ext){const b=$('batch').value;return '/ui/api/export.'+ext+(b?'?batch='+encodeURIComponent(b):'')}
$('csv').onclick=()=>{location.href=exportUrl('csv')};$('xlsx').onclick=()=>{location.href=exportUrl('xlsx')};

/* ---------- detail ---------- */
function dl(pairs){return el('dl',{},pairs.filter(([,v])=>v!=null&&v!==''&&!(Array.isArray(v)&&!v.length))
 .map(([k,v])=>[el('dt',{text:k}),el('dd',{},v)]))}
function table(cols,rows){if(!rows||!rows.length)return el('div',{class:'muted small',text:'None found.'});
 return el('div',{class:'tablewrap'},el('table',{},el('thead',{},el('tr',{},cols.map(c=>el('th',{text:c[0]})))),
  el('tbody',{},rows.map(r=>el('tr',{},cols.map(c=>el('td',{},c[1](r))))))))}
async function openLead(id){const lead=await api('/ui/api/leads/'+id);const p=lead.profile||{};const it=p.it_signals||{};
 $('panel').replaceChildren(
  el('div',{class:'row',style:'justify-content:space-between'},
   el('div',{},el('h3',{text:p.company_name||lead.company}),el('div',{class:'muted small',text:`Researched as “${lead.company}”${lead.hints?' · '+lead.hints:''}`})),
   el('button',{class:'ghost',text:'Close',onclick:closeLead})),
  p.summary?el('p',{text:p.summary}):'',
  el('h4',{text:'Company'}),dl([['Website',link(p.website)],['Industry',p.industry],['Employees',p.employee_estimate],
   ['Business address',p.business_address],['Business phone',p.business_phone],['Confidence',p.confidence]]),
  el('h4',{text:'Registrations'}),table([['Jurisdiction',r=>r.jurisdiction],['Entity #',r=>r.entity_number||''],
   ['Status',r=>r.status||''],['Type',r=>r.entity_type||''],['Formed',r=>r.formation_date||''],
   ['Registered agent',r=>r.registered_agent||''],['Source',r=>link(r.source_url,'source')]],p.registrations),
  el('h4',{text:'People'}),table([['Name',r=>r.name],['Role',r=>r.role],['Source',r=>link(r.source_url,'source')],
   ['',r=>safeUrl(r.linkedin_search_url)?el('a',{href:r.linkedin_search_url,target:'_blank',rel:'noopener noreferrer',text:'Search LinkedIn'}):'']],p.people),
  el('h4',{text:'IT signals'}),dl([['Email platform',it.email_provider],['MX records',(it.mx_records||[]).join(', ')],['Notes',it.notes]]),
  p.open_questions&&p.open_questions.length?[el('h4',{text:'Open questions'}),el('ul',{},p.open_questions.map(q=>el('li',{text:q})))]:'',
  el('h4',{text:'Sources'}),el('ul',{},(p.sources||[]).map(s=>el('li',{},link(s)))));
 $('detail').style.display='flex'}
function closeLead(){$('detail').style.display='none'}
$('detail').onclick=ev=>{if(ev.target.id==='detail')closeLead()};
document.onkeydown=ev=>{if(ev.key==='Escape')closeLead()};

loadMe();refresh();
</script></body></html>"""
