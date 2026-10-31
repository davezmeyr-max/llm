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
main{max-width:1200px;margin:0 auto;padding:20px 16px;display:grid;grid-template-columns:340px 1fr;gap:18px}
@media (max-width:860px){main{grid-template-columns:1fr}}
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

PORTAL_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lead Research</title>
<style>""" + _STYLE + r"""</style></head><body>
<header><div><h1>Lead Research</h1><div class="sub">Company background, registrations and leadership from public sources</div></div>
<div class="row"><span id="who" class="muted small"></span><a href="/logout" class="small">Sign out</a></div></header>
<main>
<div id="banner" class="banner off">Checking research engine…</div>
<section class="card">
 <h2>New research</h2>
 <label for="co">Company name</label><input id="co" placeholder="Joe Inc." maxlength="200">
 <label for="hi">Hints</label><input id="hi" placeholder="City, state, website, industry" maxlength="500">
 <label for="bulk">Or paste several, one per line: <span class="muted">Company | hints</span></label>
 <textarea id="bulk" placeholder="Acme Plumbing LLC | Naperville, IL&#10;Lakeshore Dental Group | Chicago"></textarea>
 <div class="row" style="margin-top:12px"><button id="add">Queue research</button></div>
 <div id="addmsg" class="msg"></div>
</section>
<section class="card">
 <div class="row" style="justify-content:space-between;margin-bottom:10px"><h2 style="margin:0">Leads</h2>
  <div class="row"><select id="filter" style="width:auto"><option value="">All</option><option>queued</option>
   <option>running</option><option>done</option><option>failed</option></select>
   <button class="ghost" id="csv">Export CSV</button></div></div>
 <div class="tablewrap"><table><thead><tr><th>Company</th><th>Status</th><th>Confidence</th><th>Submitted by</th>
  <th>Updated</th><th></th></tr></thead><tbody id="rows"></tbody></table></div>
 <div id="empty" class="muted small" style="padding:12px 4px;display:none">No leads yet.</div>
</section>
</main>
<div id="detail"><div class="panel" id="panel"></div></div>
<script>
const $=id=>document.getElementById(id);
const H={'X-Requested-With':'leadscout'};
function el(tag,props,...kids){const n=document.createElement(tag);
 for(const[k,v]of Object.entries(props||{})){if(k==='class')n.className=v;else if(k==='text')n.textContent=v;
  else if(k.startsWith('on'))n[k]=v;else n.setAttribute(k,v)}
 for(const k of kids.flat(Infinity)){if(k==null||k===false)continue;n.append(k instanceof Node?k:document.createTextNode(String(k)))}
 return n}
function safeUrl(u){return typeof u==='string'&&/^https?:\/\//i.test(u)?u:null}
function link(u,label){const s=safeUrl(u);return s?el('a',{href:s,target:'_blank',rel:'noopener noreferrer',text:label||s}):(u||'')}
async function api(path,opts){const r=await fetch(path,opts);
 if(r.status===401){location.href='/login';throw new Error('signed out')}
 if(!r.ok){let d='';try{d=(await r.json()).detail}catch(e){}throw new Error(d||('HTTP '+r.status))}
 return (r.headers.get('content-type')||'').includes('json')?r.json():r.text()}
function when(s){if(!s)return'';const d=new Date(s);return d.toLocaleString()}

async function loadMe(){const me=await api('/ui/api/me');$('who').textContent=me.name?`${me.name} · ${me.email}`:me.email}
async function loadStatus(){try{const s=await api('/ui/api/status');const q=s.queue||{};
 const parts=['queued','running','done','failed'].filter(k=>q[k]).map(k=>`${q[k]} ${k}`).join(' · ');
 const b=$('banner');b.className='banner '+(s.llm_online?'on':'off');
 b.textContent=(s.llm_online?'Research engine online.':'Research engine offline: new leads wait in the queue and run when it starts.')+(parts?'  '+parts:'');
 return q}catch(e){return{}}}

let busy=false;
async function loadLeads(){const f=$('filter').value;const rows=await api('/ui/api/leads'+(f?'?status='+f:''));
 const tb=$('rows');tb.replaceChildren();$('empty').style.display=rows.length?'none':'block';
 for(const r of rows){
  const retry=r.status==='failed'?el('button',{class:'ghost',text:'Retry',onclick:async e=>{e.stopPropagation();
   await api(`/ui/api/leads/${r.id}/retry`,{method:'POST',headers:H});refresh()}}):'';
  const tr=el('tr',{class:r.status==='done'?'click':''},
   el('td',{},el('div',{text:r.company_name||r.company}),r.hints?el('div',{class:'muted small',text:r.hints}):'',
     r.status==='failed'&&r.error?el('div',{class:'small err',text:r.error.slice(0,160)}):''),
   el('td',{},el('span',{class:'chip '+r.status,text:r.status})),
   el('td',{text:r.confidence||''}),el('td',{class:'small muted',text:r.submitted_by||''}),
   el('td',{class:'small muted',text:when(r.updated_at)}),el('td',{},retry));
  if(r.status==='done')tr.onclick=()=>openLead(r.id);tb.append(tr)}
 return rows}

async function refresh(){const q=await loadStatus();await loadLeads();
 clearTimeout(window._t);if(q.queued||q.running)window._t=setTimeout(refresh,15000)}

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
$('filter').onchange=loadLeads;
$('csv').onclick=()=>{location.href='/ui/api/export.csv'};

function dl(pairs){return el('dl',{},pairs.filter(([,v])=>v!=null&&v!==''&&!(Array.isArray(v)&&!v.length))
 .map(([k,v])=>[el('dt',{text:k}),el('dd',{},v)]))}
function table(cols,rows){if(!rows||!rows.length)return el('div',{class:'muted small',text:'None found.'});
 return el('div',{class:'tablewrap'},el('table',{},el('thead',{},el('tr',{},cols.map(c=>el('th',{text:c[0]})))),
  el('tbody',{},rows.map(r=>el('tr',{},cols.map(c=>el('td',{},c[1](r))))))))}
async function openLead(id){const lead=await api('/ui/api/leads/'+id);const p=lead.profile||{};const it=p.it_signals||{};
 const panel=$('panel');panel.replaceChildren(
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
$('detail').onclick=e=>{if(e.target.id==='detail')closeLead()};
document.onkeydown=e=>{if(e.key==='Escape')closeLead()};

loadMe();refresh();setInterval(loadStatus,60000);
</script></body></html>"""
