// Shared layer: helpers, icons, chart style and the data loaded by boot.js from the local API.
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const pad=n=>String(n).padStart(2,'0'),mmss=s=>{s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return(h?h+':'+pad(m):m)+':'+pad(s%60)},hm=m=>pad(Math.floor(m/60)%24)+':'+pad(Math.floor(m%60));
const avg=a=>a.reduce((s,v)=>s+v,0)/a.length,sd=a=>{const m=avg(a);return Math.sqrt(avg(a.map(v=>(v-m)**2)))},rng=(n,f)=>Array.from({length:n},(_,i)=>f(i));
// text from the DB goes through esc() before it is put into HTML
const esc=t=>String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let k={};const theme=()=>k=Object.fromEntries(['text','muted','faint','line','soft','bg','accent','good','warn','bad','blue','purple','deep','rem','light','awake','z1','z2','z3','z4','z5','run','walk','gym','hike','c1','c2','c3','c4','c5','ink'].map(n=>[n,css('--'+n)]));
const REAL=window.REAL; // set by boot.js from /api/summary
// current zones = Suunto profile (default zones at profile max HR); each workout also carries the zones it was recorded with (a.zb)
const ZT=REAL.zones.every(Boolean)?REAL.zones:[137,146,156,165],zi=(v,b=ZT)=>b.filter(t=>v>=t).length;
const zr=b=>[`below ${b[0]}`,`${b[0]}–${b[1]-1}`,`${b[1]}–${b[2]-1}`,`${b[2]}–${b[3]-1}`,`${b[3]}+`],ZR=zr(ZT);

// ---------- icons ----------
const SPORT={run:['Running','M13.5 5.5a1.8 1.8 0 1 0 0-.01M10 21l2.4-5.4 2.8 2.4V22M12.4 15.6l1-5.1-3.6 1.4-1.3 3M13.4 10.5l2.1 2.6 3 .6'],
 walk:['Walking','M12.5 4.5a1.8 1.8 0 1 0 0-.01M11 21l1.6-6.2 2.4 2.7V21M12.6 14.8l.6-5.3-2.8 1.8-.9 3.5M13.2 9.5l1.6 3 2.4 1'],
 gym:['Weight training','M6.5 7v10M3.5 9.5v5M17.5 7v10M20.5 9.5v5M6.5 12h11'],
 stretch:['Stretching','M12 4.5a1.8 1.8 0 1 0 0-.01M5 9.5l7 1.5 7-1.5M12 11v4.5M12 15.5l-4.5 5M12 15.5l4.5 5'],
 hike:['Hiking','M11.5 4.5a1.8 1.8 0 1 0 0-.01M10 21l1.6-6.2 2.4 2.7V21M11.6 14.8l.6-5.3-2.8 1.8-.9 3.5M12.2 9.5l1.6 3 2.4 1M17.5 10l1.2 11'],
 other:['Other','M12 8v8M8 12h8']};
const ico=(s,cls='')=>`<span class="ico ${cls}" style="background:var(--${s==='other'?'other':s})" title="${SPORT[s][0]}"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${SPORT[s][1]}"/></svg></span>`;
const ST={good:['good','M7.5 12.5l3 3 6-6.5'],warn:['warn','M12 7.5v5.5M12 16.5v.1'],bad:['bad','M12 7.5v5.5M12 16.5v.1'],info:['muted','M12 11v5.5M12 7.6v.1']};
const st=(t,txt)=>`<span class="st"><svg width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="var(--${ST[t][0]})"/><path d="${ST[t][1]}" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>${txt}</span>`;

// ---------- chart style (ECharts) ----------
const alpha=(c,a)=>{if(c.startsWith('#')){const n=parseInt(c.slice(1),16);return`rgba(${n>>16},${n>>8&255},${n&255},${a})`}return c};
const grad=(c,a=.28)=>alpha(c,a*.45); // flat fills (reference style: solid, no gradients)
const ax=(o={})=>({type:'category',boundaryGap:false,axisLine:{lineStyle:{color:k.line}},axisTick:{show:false},axisLabel:{color:k.faint,fontSize:11,hideOverlap:true},splitLine:{show:false},...o});
const ay=(o={})=>({type:'value',scale:true,splitNumber:3,position:'right',axisLine:{show:false},axisTick:{show:false},axisLabel:{color:k.faint,fontSize:11,margin:10},splitLine:{lineStyle:{color:k.line}},...o});
const tt=(o={})=>({trigger:'axis',backgroundColor:k.text,borderWidth:0,borderRadius:6,padding:[7,10],textStyle:{color:k.bg,fontSize:12},axisPointer:{type:'line',lineStyle:{color:k.muted,width:1},label:{show:false}},...o});
const lg=(o={})=>({top:0,left:0,icon:'roundRect',itemWidth:10,itemHeight:10,itemGap:16,textStyle:{color:k.muted,fontSize:12},...o});
const line=(name,data,color,o={})=>({name,type:'line',data,symbol:'none',showSymbol:false,lineStyle:{width:1.3,color},itemStyle:{color},sampling:'lttb',emphasis:{disabled:true},...o});
const G=(o={})=>({left:4,right:44,top:10,bottom:24,containLabel:false,...o});
function ec(id,opt){const el=typeof id==='string'?$('#'+id):id;echarts.getInstanceByDom(el)?.dispose();const c=echarts.init(el);
 el._ro?.disconnect();el._ro=new ResizeObserver(()=>c.resize());el._ro.observe(el);
 c.setOption({animation:false,textStyle:{fontFamily:'-apple-system,BlinkMacSystemFont,SF Pro Text,Segoe UI,Roboto,sans-serif'},grid:G(opt.legend?{top:30}:{}),...opt});
 el.ondblclick=()=>c.dispatchAction({type:'dataZoom',start:0,end:100});return c}
const zoomIn=()=>[{type:'inside',filterMode:'none',zoomOnMouseWheel:true,moveOnMouseMove:true}];

// ---------- data ----------
const A=REAL.activities;
const WD=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dlabel=d=>{const x=new Date(d+'T12:00');return WD[x.getDay()]+' '+x.getDate()+' '+MO[x.getMonth()]};
// [hours, deep, light, rem (min), hrv, lowest hr, bedtime (min after 00:00)], keyed by wake date
const NIGHT={};REAL.nights.forEach(n=>NIGHT[n.date]=[n.h,n.deep,n.light,n.rem,n.hrv,n.hr_min,n.bed]);
const NK=Object.keys(NIGHT).sort(),NV=i=>NK.map(d=>NIGHT[d][i]),ND=NK.map(d=>dlabel(d).slice(4));

// workouts: blocks = [reps, [[kind, minutes, zoneIndex]]]
const IF=[.55,.68,.8,.9,1.0],PACE=[470,440,405,370,340];
const TPL={rest:null,
 easy30:['Easy run 30 min','run',[[1,[['Warm-up',5,0]]],[1,[['Run',20,1]]],[1,[['Cool-down',5,0]]]]],
 easy35:['Easy run 35 min','run',[[1,[['Warm-up',5,0]]],[1,[['Run',25,1]]],[1,[['Cool-down',5,0]]]]],
 strides:['Steady 45 min + strides','run',[[1,[['Warm-up',10,0]]],[1,[['Run',25,1]]],[4,[['Stride',.5,3],['Walk',1.5,0]]],[1,[['Cool-down',2,0]]]]],
 mob:['Mobility 20 min','gym',[[1,[['Mobility',20,0]]]]],
 hike:['Hike 75 min','hike',[[1,[['Hike',75,0]]]]],
 int:['4 × 4 min intervals','run',[[1,[['Warm-up',12,1]]],[4,[['Interval',4,3],['Recover',3,0]]],[1,[['Cool-down',8,0]]]]],
 tempo:['Tempo 20 min','run',[[1,[['Warm-up',10,1]]],[1,[['Tempo',20,2]]],[1,[['Cool-down',10,0]]]]]};
const mkW=key=>{const t=TPL[key];return t&&{name:t[0],s:t[1],status:'Draft',blocks:t[2].map(([reps,parts])=>({reps,parts:parts.map(([kind,min,z])=>({kind,min,z}))}))}};
const flat=w=>w.blocks.flatMap(b=>rng(b.reps,r=>b.parts.map(p=>({...p,r:b.reps>1?r+1:0}))).flat());
const wsum=w=>{const F=flat(w),min=F.reduce((s,p)=>s+p.min,0);return{F,min,km:w.s==='gym'?0:F.reduce((s,p)=>s+p.min*60/(w.s==='hike'?720:PACE[p.z]),0),tss:F.reduce((s,p)=>s+p.min/60*IF[p.z]**2*100,0)}};


// ---------- per-activity 1 Hz recording (fetched on demand from /api/activities/{id}/recording) ----------
const REC={};
async function loadRec(a){if(!a||!a.has_rec||a.rec)return;const r=await fetch(`api/activities/${encodeURIComponent(a.id)}/recording`);if(r.ok)a.rec=await r.json()}
function recording(a){if(REC[a.id])return REC[a.id];const r=a.rec;if(!r)return null;const z=v=>v??0,N=r.hr.length,gps=!!(r.d&&r.sp);
 return REC[a.id]={N,gps,hr:r.hr.map(z),al:(r.al||[]).map(z),sp:gps?r.sp.map(z):[],d:gps?r.d.map(z):[],cd:r.cd?r.cd.map(z):[],pw:r.pw?r.pw.map(z):[]}}
