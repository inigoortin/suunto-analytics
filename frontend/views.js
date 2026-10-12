// Screens (activities, detail, plan) and the app shell. Depends on core.js.
const byId=id=>A.find(a=>a.id===id);
const kmTxt=a=>a.km?(a.km>=1?a.km.toFixed(2):Math.round(a.km*1000)+' m'):'';
const spark=(a,w=120,h=22)=>{const D=a.spark&&a.spark.length>1?{N:a.spark.length,hr:a.spark}:null;if(!D)return'<span class="faint small">no recording</span>';const n=60,step=Math.max(1,Math.floor(D.N/n)),p=rng(Math.floor(D.N/step),i=>D.hr[i*step]),mn=Math.min(...p),mx=Math.max(...p);
 return`<svg width="${w}" height="${h}"><polyline fill="none" stroke="var(--accent)" stroke-width="1.2" points="${p.map((y,i)=>(i/(p.length-1)*w).toFixed(1)+','+(h-1-(y-mn)/(mx-mn||1)*(h-2)).toFixed(1)).join(' ')}"/></svg>`};
const actRow=a=>`<div class="r click" data-act="${a.id}" style="grid-template-columns:44px minmax(0,1fr) 90px 90px 80px 60px 130px">
 ${ico(a.s)}<div><b>${esc(a.name)}</b><div class="muted small">${SPORT[a.s][0]} · ${dlabel(a.day)}, ${esc(a.t)}</div></div>
 <div class="num">${a.km?`<b>${kmTxt(a)}</b><div class="faint small">${a.km>=1?'km':'distance'}</div>`:''}</div>
 <div class="num"><b>${mmss(a.dur)}</b><div class="faint small">time</div></div>
 <div class="num"><b>${a.hr}</b><div class="faint small">avg bpm</div></div>
 <div class="num"><b>${Math.round(a.tss)}</b><div class="faint small">TSS</div></div><div>${spark(a)}</div></div>`;
const bindActs=root=>root.querySelectorAll('[data-act]').forEach(e=>e.onclick=ev=>{ev.stopPropagation();openAct(e.dataset.act)});
const prof=(w,width=150,h=26)=>{const {F,min}=wsum(w);return`<div class="prof" style="width:${width}px;height:${h}px">${F.map(p=>`<i style="width:${Math.max(1,p.min/min*width-1)}px;height:${(p.z+1)/5*h}px;background:var(--z${p.z+1})"></i>`).join('')}</div>`};
const zdesc=w=>{const {F}=wsum(w),zs=[...new Set(F.filter(p=>!/Warm|Cool|Walk|Recover/.test(p.kind)).map(p=>p.z+1))];return zs.length?'HR zone '+zs.join('/'):'HR zone 1'};

const R={
 activities(){const f=$('#a-filter .on').dataset.f,L=A.filter(a=>!f||a.s===f||(f==='walk'&&a.s==='hike')),days=[...new Set(L.map(a=>a.day))];
  $('#a-list').innerHTML=days.map(d=>{const g=L.filter(a=>a.day===d);return`<div class="sec-h" style="margin:26px 0 4px"><span class="muted small">${dlabel(d)}</span><span class="faint small">${g.length} ${g.length>1?'activities':'activity'} · ${mmss(g.reduce((s,a)=>s+a.dur,0))}</span></div><div class="rows">${g.map(actRow).join('')}</div>`}).join('');
  if(!L.length)$('#a-list').innerHTML='<p class="muted" style="margin-top:24px">No activities yet.</p>';
  bindActs($('#a-list'))},

 detail(){detailRender()},
 plan(){planRender()}

};

// ---------- activity detail ----------
let cur='dash',actId='a1',res='10',axis='t';
async function openAct(id){actId=id;await loadRec(byId(id));show('detail')}
let zA=zi,zrA=ZR; // zones the selected workout was recorded with
function detailRender(){
 const a=byId(actId);zA=v=>zi(v,a.zb||ZT);zrA=zr(a.zb||ZT);const D=recording(a),gps=!!(D&&D.gps);
 $('#d-head').innerHTML=`${ico(a.s,'l')}<div><h1>${esc(a.name)}</h1><div class="muted">${SPORT[a.s][0]} · ${dlabel(a.day)}, ${esc(a.t)}</div></div>`;
 const pace=gps?mmss(a.dur/a.km):'';
 const M=gps?[['Distance',a.km.toFixed(2)+'<small> km</small>'],['Time',mmss(a.dur)],['Avg pace',pace+'<small> /km</small>'],['Avg HR',a.hr+'<small> bpm</small>','max '+a.mx],['Training effect',a.te??'–',a.te>=4?'highly improving':a.te>=3?'improving':'maintaining'],['Calories',a.kcal+'<small> kcal</small>']]
  :[['Time',mmss(a.dur)],['Avg HR',a.hr+'<small> bpm</small>'],['Max HR',a.mx+'<small> bpm</small>'],['Training effect',a.te??'–'],['Load',Math.round(a.tss)+'<small> TSS</small>'],['Calories',a.kcal+'<small> kcal</small>']];
 $('#d-metrics').innerHTML=M.map(([x,y,z])=>`<div><div class="m-k">${x}</div><div class="m-v">${y}</div>${z?`<div class="m-d">${z}</div>`:''}</div>`).join('');
 $('#xax').style.display=gps?'':'none';$('#d-splits-sec').style.display=gps?'':'none';
 $('#res').style.display=D?'':'none';if(!D){$('#rd').innerHTML='';$('#tracks').innerHTML='<p class="muted">No second-by-second recording for this activity: Suunto had no FIT file for it, only the summary.</p>';zonesEffort(a,D);return}
 const T=[['hr','Heart rate','bpm'],['al','Elevation','m']];if(gps)T.splice(1,0,['pace','Pace','/km']),T.push(['cd','Cadence','spm'],['pw','Power','W']);
 $('#tracks').innerHTML=T.map(([id,n],i)=>`<div class="track"><div class="lab"><b>${n}</b><span id="tl-${id}"></span></div><div class="ch ${i===T.length-1?'s':'xs'}" id="tr-${id}" style="${id==='hr'?'height:170px':''}"></div></div>`).join('');
 $('#rd').style.gridTemplateColumns=`repeat(${T.length+(gps?2:1)},1fr)`;
 const step=+res,Rg=rng(Math.ceil(D.N/step),i=>[i*step,Math.min(D.N,(i+1)*step)]),B=f=>Rg.map(([i,j])=>avg(D[f].slice(i,j)));
 const hr=B('hr').map(Math.round),al=B('al').map(v=>+v.toFixed(1)),sp=gps?(step===1?D.sp.map((_,i)=>avg(D.sp.slice(Math.max(0,i-7),i+8))):B('sp')):[],pc=sp.map(v=>Math.round(Math.min(600,1000/v)));
 const dist=gps?B('d'):[],X=Rg.map((r,i)=>axis==='d'&&gps?(dist[i]/1000).toFixed(2)+' km':mmss(r[0])),S={hr,al,pace:pc,cd:gps?B('cd').map(Math.round):[],pw:gps?B('pw').map(Math.round):[]};
 const rd=i=>{if(i==null||!Rg[i])return;const cells=[['Time',mmss(Rg[i][0])]];if(gps)cells.push(['Distance',(dist[i]/1000).toFixed(2)+' km']);
  T.forEach(([id,n,u])=>cells.push([n,(id==='pace'?mmss(S.pace[i]):Math.round(S[id][i]))+' '+u+(id==='hr'?` <span style="color:var(--z${zA(S.hr[i])+1})">Z${zA(S.hr[i])+1}</span>`:'')]));$('#rd').innerHTML=cells.map(([x,y])=>`<div><span>${x}</span><b>${y}</b></div>`).join('')};
 const fmt={pace:mmss};
 T.forEach(([id,n,u],i)=>{const last=i===T.length-1,y=S[id];
  let s=line(n,y,{hr:k.accent,pace:k.blue,al:k.muted,cd:k.purple,pw:k.warn}[id]),yo={};
  if(id==='hr'){s=[{name:'Zone',type:'bar',data:y.map(v=>({value:v,itemStyle:{color:k['z'+(zA(v)+1)]}})),barWidth:'100%',barCategoryGap:'0%',silent:true,itemStyle:{opacity:.85}},line(n,y,k.text,{lineStyle:{width:1,color:alpha(k.text,.55)}})];yo={min:Math.floor((Math.min(...y)-8)/10)*10,max:Math.ceil((Math.max(...y)+4)/10)*10,splitNumber:3}}
  if(id==='pace')yo={inverse:true,min:Math.floor((Math.min(...y)-15)/60)*60,max:600,interval:60,axisLabel:{color:k.faint,fontSize:11,formatter:mmss}};
  if(id==='al')s.areaStyle={color:grad(k.muted,.3)};
  if(id==='cd')s={name:n,type:'scatter',symbolSize:2.5,data:y,itemStyle:{color:p=>p.value<153?k.z5:p.value<164?k.z4:p.value<174?k.z3:k.z2}},yo={min:Math.floor((Math.min(...y.filter(v=>v>60))-10)/10)*10};
  const c=ec('tr-'+id,{tooltip:tt({showContent:false}),grid:G({top:6,bottom:last?24:6}),xAxis:ax({data:X,axisLabel:{show:last,color:k.faint,fontSize:11,hideOverlap:true}}),yAxis:ay(yo),dataZoom:zoomIn(),series:Array.isArray(s)?s:[s]});
  c.group='d';c.on('updateAxisPointer',e=>{const v=e.axesInfo&&e.axesInfo[0];if(v)rd(v.value)});
  const raw=id==='pace'?null:D[id];$('#tl-'+id).textContent=id==='pace'?'avg '+pace+' /km':id==='al'?`↑ ${Math.round(Math.max(...D.al)-Math.min(...D.al))} m range`:`avg ${Math.round(avg(raw.filter(v=>id!=='cd'||v>100)))} · max ${Math.max(...raw)} ${u}`});
 $('#tl-hr').innerHTML=zrA.map((r,j)=>`<span style="margin-left:12px"><i style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;background:var(--z${j+1})"></i>Z${j+1} ${r}</span>`).join('')+`<span style="margin-left:16px">${$('#tl-hr').textContent}</span>`;
 echarts.connect('d');rd(0);
 // splits
 if(gps){const L=[];let s=0;for(let i=1;i<=Math.floor(a.km);i++){const e=D.d.findIndex(v=>v>=i*1000);L.push({t:e-s,hr:avg(D.hr.slice(s,e)),cd:avg(D.cd.slice(s,e)),el:D.al[e]-D.al[s]});s=e}
  const rest=a.km%1;if(rest>.05)L.push({t:D.N-s,hr:avg(D.hr.slice(s)),cd:avg(D.cd.slice(s)),el:D.al[D.N-1]-D.al[s],part:rest});
  const pcs=L.map(l=>l.t/(l.part||1)),best=Math.min(...pcs),worst=Math.max(...pcs);
  $('#d-splits').innerHTML='<tr><th>Km</th><th>Pace</th><th style="width:45%"></th><th class="r">Time</th><th class="r">Avg HR</th><th class="r">Cadence</th><th class="r">Elev</th></tr>'+L.map((l,i)=>{const p=pcs[i],b=p===best;
   return`<tr><td class="muted">${l.part?l.part.toFixed(2):i+1}</td><td>${b?'<b>':''}${mmss(p)}${b?'</b>':''}</td><td><div class="pbar ${b?'best':''}" style="width:${35+65*(worst-p)/(worst-best||1)}%"></div></td><td class="r">${mmss(l.t)}</td><td class="r">${Math.round(l.hr)}</td><td class="r">${Math.round(l.cd)}</td><td class="r muted">${l.el>0?'+':''}${Math.round(l.el)} m</td></tr>`}).join('')+`<tr class="tot"><td>${a.km.toFixed(2)} km</td><td>${pace}</td><td></td><td class="r">${mmss(a.dur)}</td><td class="r">${a.hr}</td><td></td><td></td></tr>`}
 zonesEffort(a,D)}
function zonesEffort(a,D){
 const Z=a.zone_s?a.zone_s.map(Math.round):[0,0,0,0,0];if(!a.zone_s&&D)D.hr.forEach(v=>Z[zA(v)]++);const tot=Z.reduce((s,v)=>s+v,0)||1;
 $('#d-zones').innerHTML='<div class="rows">'+Z.map((s,i)=>`<div class="r" style="grid-template-columns:170px 1fr 110px;padding:10px 0"><span class="st"><i style="width:10px;height:10px;border-radius:2px;background:var(--z${i+1})"></i>Zone ${i+1} <span class="faint small">${zrA[i]}</span></span><div class="hbar" style="height:8px"><i style="width:${s/tot*100}%;background:var(--z${i+1})"></i></div><span class="num">${mmss(s)} <span class="muted small">${Math.round(s/tot*100)}%</span></span></div>`).join('')+'</div>'+(a.zone_s?'<p class="faint small">Seconds per zone as recorded by your watch.</p>':'');
 $('#d-effort').innerHTML='<div class="rows">'+[['Training effect',a.te!=null?a.te+' aerobic':'–'],['Load',Math.round(a.tss)+' TSS'],['Peak EPOC',a.epoc!=null?a.epoc+' ml/kg':'–'],['Recovery time',a.rec_h!=null?a.rec_h+' h':'–'],['VO2max estimate',a.vo2??'–'],['Calories',a.kcal!=null?a.kcal+' kcal':'–']].map(([x,y])=>`<div class="r" style="grid-template-columns:1fr auto;padding:10px 0"><span class="muted">${x}</span><b>${y}</b></div>`).join('')+'</div>'}

// ---------- plan (saved in this browser; nothing is sent anywhere) ----------
let openDay=null,planWeek=null,PLAN=[];
const PKEY='plan.v1',store={get(){try{return JSON.parse(localStorage.getItem(PKEY))||{}}catch{return{}}},set(o){try{localStorage.setItem(PKEY,JSON.stringify(o))}catch{}}};
const weekStart=d=>{const x=new Date(d+'T12:00:00');x.setDate(x.getDate()-(x.getDay()+6)%7);return x.toISOString().slice(0,10)};
const shift=(d,n)=>{const x=new Date(d+'T12:00:00');x.setDate(x.getDate()+n);return x.toISOString().slice(0,10)};
function planLoad(){const all=store.get();PLAN=rng(7,i=>{const d=shift(planWeek,i);return{d,w:all[d]||null}})}
function planSave(){const all=store.get();PLAN.forEach(p=>{if(p.w)all[p.d]=p.w;else delete all[p.d]});store.set(all)}
function planRender(){
 if(!planWeek){const t=new Date();planWeek=weekStart(new Date(t-t.getTimezoneOffset()*6e4).toISOString().slice(0,10));planLoad()}
 planSave();
 const end=shift(planWeek,6),ws=PLAN.filter(p=>p.w),S=ws.map(p=>wsum(p.w)),tss=S.reduce((s,x)=>s+x.tss,0),min=S.reduce((s,x)=>s+x.min,0);
 const done=A.filter(a=>a.day>=planWeek&&a.day<=end),doneT=done.reduce((s,a)=>s+a.tss,0),doneM=done.reduce((s,a)=>s+a.dur,0)/60;
 $('#p-lead').textContent=`${dlabel(planWeek).slice(0,-4)} – ${dlabel(end)}`;
 $('#p-metrics').innerHTML=`<div><div class="m-k">Planned</div><div class="m-v">${ws.length}<small> workouts</small></div><div class="m-d">${7-ws.length} rest days</div></div><div><div class="m-k">Planned time</div><div class="m-v">${Math.floor(min/60)}:${pad(Math.round(min%60))}<small> h</small></div><div class="m-d">done this week ${Math.floor(doneM/60)}:${pad(Math.round(doneM%60))} h</div></div>
  <div><div class="m-k">Estimated load</div><div class="m-v">${Math.round(tss)}<small> TSS</small></div><div class="m-d">done this week ${Math.round(doneT)} TSS</div></div>`;
 const c='grid-template-columns:96px 34px minmax(0,1fr) 160px 70px';
 $('#p-days').innerHTML=PLAN.map((p,i)=>{const l=dlabel(p.d),dh=`<div class="day"><b>${l.slice(0,3)}</b><span>${l.slice(4)}</span></div>`;
  if(!p.w)return`<div class="r" style="${c}">${dh}<span></span><span class="muted">Rest</span><span></span><a class="link small" data-add="${i}">+ Add workout</a></div>`;
  const s=wsum(p.w);return`<div class="r click" data-day="${i}" style="${c}">${dh}${ico(p.w.s,'s')}<div><b>${esc(p.w.name)}</b><div class="muted small">${SPORT[p.w.s][0]} · ${mmss(s.min*60)}${s.km?' · ~'+s.km.toFixed(1)+' km':''} · ${zdesc(p.w)}</div></div>${prof(p.w)}<div class="num"><b>${Math.round(s.tss)}</b><div class="faint small">TSS</div></div></div>`+(openDay===i?'<div class="editor" id="editor"></div>':'')}).join('');
 $$('#p-days [data-day]').forEach(e=>e.onclick=()=>{const i=+e.dataset.day;openDay=openDay===i?null:i;planRender()});
 $$('#p-days [data-add]').forEach(e=>e.onclick=()=>{const i=+e.dataset.add;PLAN[i].w=mkW('easy30');openDay=i;planRender()});
 if(openDay!=null)editor(PLAN[openDay])}
const planGo=n=>{planWeek=shift(planWeek,7*n);openDay=null;planLoad();planRender()};
function editor(p){const w=p.w,el=$('#editor'),s=wsum(w);
 const ksel=v=>`<select data-f="kind">${['Warm-up','Run','Interval','Recover','Tempo','Stride','Walk','Hike','Mobility','Cool-down'].map(o=>`<option ${o==v?'selected':''}>${o}</option>`).join('')}</select>`;
 const zsel=z=>`<select data-f="z">${ZR.map((r,i)=>`<option value="${i}" ${i==z?'selected':''}>Zone ${i+1} · ${r} bpm</option>`).join('')}</select>`;
 let st_='';w.blocks.forEach((b,bi)=>{if(b.reps>1)st_+=`<div class="step rep"><span>Repeat <input type="number" min="2" max="20" value="${b.reps}" data-b="${bi}" data-f="reps"> times</span><button class="x" data-del="${bi}">✕</button></div>`;
  b.parts.forEach((q,pi)=>st_+=`<div class="step ${b.reps>1?'in':''}" data-b="${bi}" data-p="${pi}"><span class="sw" style="background:var(--z${q.z+1})"></span>${ksel(q.kind)}<span><input type="number" min="0.5" step="0.5" max="240" value="${q.min}" data-f="min"> min</span>${zsel(q.z)}${b.reps>1?'<span></span>':`<button class="x" data-del="${bi}">✕</button>`}</div>`)});
 el.innerHTML=`<div class="sec-h" style="margin:0"><input id="wname" value="${esc(w.name)}" style="font-size:17px;font-weight:650;border-color:transparent;background:transparent;padding-left:0;width:320px"><div class="seg" id="tplsel"><button data-k="easy35">Easy</button><button data-k="strides">Strides</button><button data-k="tempo">Tempo</button><button data-k="int">4 × 4 min</button></div></div>
  <div class="ch xs" id="c-prof" style="height:110px;margin-top:8px"></div>
  <div class="muted small" style="margin-top:2px">${mmss(s.min*60)}${s.km?' · ~'+s.km.toFixed(1)+' km':''} · est. ${Math.round(s.tss)} TSS · zones from your Suunto profile (max HR ${REAL.max_hr||'–'})</div>
  <div class="steps">${st_}</div>
  <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap;align-items:center"><button class="btn" id="addstep">+ Step</button><button class="btn" id="addrep">+ Repeat</button><span style="flex:1"></span><button class="btn" id="exp">Export</button><button class="btn" id="delw">Remove</button></div>`;
 let t=0;const data=s.F.map(q=>{const v=[t,t+q.min,q.z+1,q.z,q.kind+(q.r?' '+q.r:'')];t+=q.min;return v});
 ec('c-prof',{grid:G({top:4,bottom:20,left:4,right:30}),tooltip:{...tt({trigger:'item'}),formatter:q=>`<b>${q.value[4]}</b> · ${q.value[1]-q.value[0]} min<br>Zone ${q.value[3]+1} · ${ZR[q.value[3]]} bpm`},
  xAxis:{type:'value',min:0,max:s.min,axisLabel:{color:k.faint,fontSize:11,formatter:v=>Math.round(v)+'′'},splitLine:{show:false},axisLine:{lineStyle:{color:k.line}}},yAxis:ay({min:0,max:5,interval:1,axisLabel:{color:k.faint,fontSize:10,formatter:v=>v?'Z'+v:''}}),
  series:[{type:'custom',data,encode:{x:[0,1],y:2},renderItem:(q,api)=>{const a=api.coord([api.value(0),api.value(2)]),b=api.coord([api.value(1),0]);return{type:'rect',shape:{x:a[0],y:a[1],width:Math.max(1,b[0]-a[0]-1.5),height:b[1]-a[1],r:[2,2,0,0]},style:{fill:k['z'+(api.value(3)+1)]}}}}]});
 el.onclick=e=>e.stopPropagation();
 el.onchange=e=>{const x=e.target,f=x.dataset.f;if(!f)return;if(f==='reps')w.blocks[+x.dataset.b].reps=Math.max(2,+x.value);else{const r=x.closest('.step'),q=w.blocks[+r.dataset.b].parts[+r.dataset.p];q[f]=f==='kind'?x.value:Math.max(f==='z'?0:.5,+x.value)}planRender()};
 $$('#editor [data-del]').forEach(b=>b.onclick=()=>{w.blocks.splice(+b.dataset.del,1);if(!w.blocks.length){p.w=null;openDay=null}planRender()});
 $('#addstep').onclick=()=>{w.blocks.splice(Math.max(0,w.blocks.length-1),0,{reps:1,parts:[{kind:'Run',min:10,z:1}]});planRender()};
 $('#addrep').onclick=()=>{w.blocks.splice(Math.max(0,w.blocks.length-1),0,{reps:3,parts:[{kind:'Interval',min:3,z:3},{kind:'Recover',min:2,z:0}]});planRender()};
 $$('#tplsel button').forEach(b=>b.onclick=()=>{const n=mkW(b.dataset.k);p.w=n;planRender()});
 $('#wname').oninput=e=>w.name=e.target.value;$('#wname').onchange=()=>planRender();
 $('#exp').onclick=()=>{const b=new Blob([JSON.stringify({date:p.d,...w,...wsum(w),F:undefined},null,1)],{type:'application/json'}),u=URL.createObjectURL(b),l=document.createElement('a');
  l.href=u;l.download=`workout-${p.d}.json`;l.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
 $('#delw').onclick=()=>{p.w=null;openDay=null;planRender()}}

// ---------- shell ----------
const seg=b=>[...b.parentNode.children].forEach(x=>x.classList.toggle('on',x===b));
function show(id){$$('.screen').forEach(e=>e.classList.toggle('on',e.id===id));$$('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.s===id||(id==='detail'&&b.dataset.s==='activities')));cur=id;theme();R[id]();scrollTo(0,0)}
$$('.tabs button').forEach(b=>b.onclick=()=>show(b.dataset.s));
document.addEventListener('click',e=>{const g=e.target.closest('[data-go]');if(g){e.preventDefault();show(g.dataset.go)}});
$$('#a-filter button').forEach(b=>b.onclick=()=>{seg(b);R.activities()});
$$('#res button').forEach(b=>b.onclick=()=>{seg(b);res=b.dataset.r;detailRender()});$$('#xax button').forEach(b=>b.onclick=()=>{seg(b);axis=b.dataset.x;detailRender()});
const setTheme=t=>{const r=document.documentElement;t==='system'?r.removeAttribute('data-theme'):r.dataset.theme=t;try{localStorage.setItem('theme',t)}catch{}};
$$('#theme button').forEach(b=>b.onclick=()=>{seg(b);setTheme(b.dataset.t)});
{let t='system';try{t=localStorage.getItem('theme')||'system'}catch{}const b=$(`#theme [data-t="${t}"]`);if(b){seg(b);setTheme(t)}}
$('#p-prev').onclick=()=>planGo(-1);$('#p-next').onclick=()=>planGo(1);
// sync: one polite run on click (server enforces one at a time + a 15-min gap); we only watch our own local server
const syncTxt=t=>$('#sync-txt').textContent=t;
syncTxt(REAL.data_until?'Data to '+dlabel(REAL.data_until.slice(0,10)).slice(4)+' '+REAL.data_until.slice(11):'No data yet');
async function syncWatch(){const s=await (await fetch('api/sync')).json();
 if(s.running){$('#sync').textContent='Syncing…';return setTimeout(syncWatch,3000)}
 $('#sync').textContent='Sync';if(s.error)return syncTxt(s.error);location.reload()}
$('#sync').onclick=async()=>{if($('#sync').textContent!=='Sync')return;const r=await fetch('api/sync',{method:'POST'}),s=await r.json();
 if(!s.started)return syncTxt(s.reason);syncWatch()};
const redraw=()=>{theme();R[cur]()};new MutationObserver(redraw).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});matchMedia('(prefers-color-scheme: dark)').addEventListener('change',redraw);
addEventListener('resize',()=>$$('.ch').forEach(el=>echarts.getInstanceByDom(el)?.resize()));
// first render happens in wf-dash.js once R.dash exists
