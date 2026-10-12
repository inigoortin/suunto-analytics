// Dashboard on the local Suunto data. TARGET is the weekly routine the calendar and projection compare against
// (default: 2–3 runs and 2–3 gym sessions a week; edit to match yours).
const TODAY=new Date(),DAYMS=864e5,iso=d=>new Date(d.getTime()-d.getTimezoneOffset()*6e4).toISOString().slice(0,10);
const addDays=(d,n)=>iso(new Date(+new Date(d+'T12:00:00')+n*DAYMS)),monday=d=>{const x=new Date(d+'T12:00:00');return addDays(d,-((x.getDay()+6)%7))};
const pctl=(a,p)=>{const s=[...a].sort((x,y)=>x-y);return s[Math.min(s.length-1,Math.floor(p*s.length))]};
const DAYS=REAL.days,TARGET={run:[2,3],gym:[2,3]};
// the latest runs with a recording (boot.js preloads exactly these)
const dashRuns=()=>A.filter(x=>x.s==='run'&&x.has_rec&&x.km>=1).sort((x,y)=>x.day<y.day?1:x.day>y.day?-1:x.t<y.t?1:-1).slice(0,5);
const shortM=s=>Math.round(s/60)+'′';

// ---------- metrics from real data ----------
function kmSplits(D){const out=[];let s=0;for(let i=1;;i++){let e=D.d.findIndex(v=>v>=i*1000);const part=e<0;if(part)e=D.N-1;const dist=(D.d[e]-D.d[s])/1000;if(e-s<30||dist<.3)break;
 const hr=avg(D.hr.slice(s,e).filter(v=>v>0)),pace=(e-s)/dist,cad=avg(D.cd.slice(s,e).filter(v=>v>100));out.push({km:i,dist,pace,hr,cad,ef:(1000/pace*60)/hr});if(part)break;s=e}return out}
function realStats(){
 const today=iso(TODAY),first=[...A.map(a=>a.day),...NK,...Object.keys(DAYS)].sort()[0],dates=[];for(let d=monday(first);d<=today;d=addDays(d,1))dates.push(d);
 const tss=dates.map(d=>+A.filter(a=>a.day===d).reduce((s,a)=>s+(a.tss||0),0).toFixed(1));
 let c=0,a=0;const load=tss.map(t=>{c+=(t-c)/42;a+=(t-a)/7;return[c,a,c-a]}),[ctl,atl,tsb]=load.at(-1);
 const weeks=[...new Set(dates.map(monday))],inWeek=(w,d)=>d>=w&&d<=addDays(w,6);
 const runs=dashRuns(),runRec=runs.map(r=>({r,D:recording(r),sp:kmSplits(recording(r))}));
 const nv=NK.map(d=>NIGHT[d]),lastN=nv.at(-1),prev=nv.slice(-8,-1),last=runRec[0];
 let dec=null;if(last){const D=last.D,h=Math.floor(D.N/2),e=(i,j)=>{const sp=avg(D.sp.slice(i,j)),hr=avg(D.hr.slice(i,j).filter(v=>v>0));return{sp,hr,ef:sp*60/hr}};dec={a:e(0,h),b:e(h,D.N)};dec.pct=(dec.a.ef-dec.b.ef)/dec.a.ef*100}
 const dk=Object.keys(DAYS).sort(),avgT=s=>{const L=A.filter(x=>x.s===s&&x.tss);return L.length?avg(L.map(x=>x.tss)):null};
 return{today,dates,tss,load,ctl,atl,tsb,acwr:ctl>0?atl/ctl:null,weeks,inWeek,runs,runRec,dec,
  hrv:lastN&&lastN[4],hrvBase:avg(prev.map(n=>n[4])),rhr:lastN&&lastN[5],rhrBase:avg(prev.map(n=>n[5])),vo2:Math.max(...A.map(x=>x.vo2||0))||null,
  recNow:dk.length?DAYS[dk.at(-1)].rec_last:null,week:tss.slice(-7).reduce((s,v)=>s+v,0),tRun:avgT('run')??40,tGym:avgT('gym')??35,tStr:avgT('stretch')??8}}

const noData=()=>!A.length&&!NK.length&&!Object.keys(DAYS).length;
R.dash=()=>{if(noData()){$('#dash').innerHTML='<div class="pn" style="padding:28px"><h3>No data yet</h3><div class="nt" style="margin-top:6px">Click <b>Sync</b> at the top to fetch your Suunto data (or run <code>uv run suunto sync</code>). If Suunto asks you to sign in, run <code>uv run suunto login</code> in a terminal first.</div></div>';return}
 const S=realStats(),g=G({top:24,left:12,right:40,bottom:22}),leg=lg({top:0,left:0,itemWidth:9,itemHeight:9,itemGap:10,textStyle:{color:k.muted,fontSize:11}});
 const bar=(name,data,color,o={})=>({name,type:'bar',data,itemStyle:{color},barCategoryGap:'30%',barMaxWidth:28,...o}),stk=(n,d,c)=>bar(n,d,c,{stack:'s'}),wl=S.weeks.map(w=>'wk '+dlabel(w).slice(4));
 const thisW=monday(S.today),lastWk=addDays(thisW,-7),wA=A.filter(a=>S.inWeek(thisW,a.day)),pA=A.filter(a=>S.inWeek(lastWk,a.day)),cnt=s=>wA.filter(a=>a.s===s).length,pc=s=>pA.filter(a=>a.s===s).length,ph=L=>(L.reduce((s,a)=>s+a.dur,0)/3600).toFixed(1);
 // header: this week vs routine
 $('#o-range').textContent=`since ${dlabel(S.dates[0])} · ${A.length} activities · ${NK.length} nights`;
 const prog=(n,[lo,hi])=>`<div class="bar3">${rng(hi,i=>`<i style="background:${i<n?(n>=lo?k.c3:k.c2):k.line}"></i>`).join('')}</div>`;
 $('#o-week').innerHTML=[['run','Runs',TARGET.run],['gym','Weight training',TARGET.gym]].map(([s,l,t])=>`<div><div class="n">${cnt(s)}<small> / ${t[0]}–${t[1]}</small></div><div class="l">${l} this week · last week ${pc(s)}</div>${prog(cnt(s),t)}</div>`).join('')+
  `<div><div class="n">${cnt('stretch')}</div><div class="l">Stretching · last week ${pc('stretch')}</div></div><div><div class="n">${ph(wA)}<small> h</small></div><div class="l">Active time · last week ${ph(pA)} h</div></div><div><div class="n">${Math.round(S.week)}</div><div class="l">Load, last 7 days</div></div>`;
 const left=6-((new Date(S.today+'T12:00').getDay()+6)%7);
 $('#o-note').textContent=`Week of ${dlabel(thisW)} · ${left} day${left===1?'':'s'} left · zones from your Suunto profile: ${ZT.join(' / ')} bpm (max HR ${REAL.max_hr||'–'})`;
 const kp=[['Fitness (CTL)',S.ctl.toFixed(1),'',`low: ${S.dates.length} days of history`,k.c1,'Your 42-day average training load. It rises slowly as you train consistently.'],
  ['Fatigue (ATL)',S.atl.toFixed(1),'',`last 7 days ${Math.round(S.week)} TSS`,k.c4,'Your 7-day average training load: how much recent work you are carrying.'],
  ['Form (TSB)',S.tsb.toFixed(1),'',S.tsb<-10?'tired':S.tsb>5?'fresh':'balanced',S.tsb<-10?k.bad:k.text,'Fitness minus fatigue. Below −10 you are tired; above +5 you are fresh.'],
  ['Load ratio',S.acwr?S.acwr.toFixed(2):'–','','aim 0.8–1.3',S.acwr>1.5?k.bad:k.text,'Recent load vs what you are used to. Well above 1.3 means a sudden jump, which raises injury risk. High now because your history is short.'],
  ['Resting HR',S.rhr,' bpm',`${S.rhr-S.rhrBase>0?'+':''}${(S.rhr-S.rhrBase).toFixed(1)} vs previous nights`,k.text,'Lowest heart rate while asleep. A rise of 3+ bpm often means fatigue, illness or poor recovery.'],
  ['VO2max',S.vo2??'–','','Suunto estimate',k.text,'Estimated aerobic capacity from your runs (ml/kg/min). Higher = fitter.'],
  ['HRV',S.hrv,' ms',`previous 7 nights avg ${Math.round(S.hrvBase)}`,k.text,'Heart-rate variability during sleep. Lower than your normal usually means more stress or fatigue.'],
  ['Recovery',S.recNow??'–',' %','Suunto balance, latest',k.text,'Suunto recovery balance: how recovered your body is right now, from 24/7 heart rate.']];
 $('#g-kpis').innerHTML=kp.map(([l,v,u,d,c,tip])=>`<div title="${tip}" style="cursor:help"><div class="k">${l} ⓘ</div><div class="v" style="color:${c}">${v}<small>${u}</small></div><div class="d">${d}</div></div>`).join('');
 // week-by-week calendar
 const wd=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],calW=S.weeks.slice(-4);
 $('#cal').innerHTML='<div></div>'+wd.map(d=>`<div class="h">${d}</div>`).join('')+calW.map(w=>{const L=A.filter(a=>S.inWeek(w,a.day)),c_=s=>L.filter(a=>a.s===s).length;
  return`<div class="w"><b>${dlabel(w).slice(4)}</b><br>${c_('run')} run · ${c_('gym')} gym<br>${c_('stretch')} stretch · ${c_('walk')} walk</div>`+rng(7,i=>{const d=addDays(w,i),its=A.filter(a=>a.day===d).slice().reverse();
   return`<div class="d ${d===S.today?'today':''} ${d>S.today?'fut':''}"><span class="dn">${+d.slice(8)}</span>${its.map(a=>`<span class="it" data-act="${a.id}" title="${esc(a.name)} · ${esc(a.t)}">${ico(a.s,'s')}${a.s==='run'||a.km>=2?a.km.toFixed(1)+' km':shortM(a.dur)}</span>`).join('')}</div>`}).join('')}).join('');
 $$('#cal [data-act]').forEach(e=>e.onclick=()=>openAct(e.dataset.act));
 const wk=f=>S.weeks.map(w=>f(A.filter(a=>S.inWeek(w,a.day))));
 ec('o-sess',{grid:g,legend:leg,tooltip:tt({axisPointer:{type:'shadow'}}),xAxis:ax({data:wl,boundaryGap:true}),yAxis:ay({min:0,minInterval:1,max:v=>Math.max(4,v.max)}),
  series:[bar('Runs',wk(L=>L.filter(a=>a.s==='run').length),k.c2,{barGap:'10%',markArea:{silent:true,itemStyle:{color:alpha(k.c3,.1)},label:{show:true,position:'insideTopRight',color:k.c3,fontSize:10,formatter:'target 2–3'},data:[[{yAxis:2},{yAxis:3}]]}}),bar('Weight training',wk(L=>L.filter(a=>a.s==='gym').length),k.c1),bar('Stretching',wk(L=>L.filter(a=>a.s==='stretch').length),alpha(css('--stretch'),.55))]});
 // routes on map tiles (Leaflet)
 const withRoute=A.filter(a=>a.route);let sel=withRoute.find(a=>a.s==='run')||withRoute[0],lines={};
 if(window._map){window._map.remove();window._map=null}
 if(withRoute.length&&window.L){const m=window._map=L.map('rt-map',{zoomControl:true,attributionControl:true,scrollWheelZoom:false});m.setView(withRoute[0].route[0],13);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors',className:'osm-tiles'}).addTo(m);
  withRoute.forEach(a=>{lines[a.id]=L.polyline(a.route,{color:k.muted,weight:2,opacity:.5}).addTo(m).on('click',()=>pick(a))});}
 const pick=a=>{sel=a;Object.entries(lines).forEach(([id,l])=>l.setStyle(id===a.id?{color:k.c4,weight:4,opacity:.95}:{color:k.muted,weight:2,opacity:.5}));if(lines[a.id]){window._map.fitBounds(lines[a.id].getBounds(),{padding:[24,24]});lines[a.id].bringToFront()}
  $$('#rt-list [data-r]').forEach(x=>x.classList.toggle('on',x.dataset.r===a.id));drawRun()};
 const drawRun=()=>{if(!sel)return;const D=recording(sel);$('#rt-name').textContent=`${esc(sel.name)} · ${dlabel(sel.day)}`;if(!D||!D.gps)return;
  const st=10,n=Math.floor(D.N/st),B=f=>rng(n,i=>avg(D[f].slice(i*st,(i+1)*st))),sp=B('sp'),hr=B('hr'),al=B('al'),dk=B('d').map(v=>(v/1000).toFixed(2)),mean=avg(sp.filter(v=>v>.5)),dev=sp.map(v=>+((v-mean)*3.6).toFixed(2));
  ec('rt-dev',{grid:G({top:6,left:8,right:36,bottom:20}),tooltip:tt({formatter:p=>`${p[0].axisValue} km · ${(sp[p[0].dataIndex]*3.6).toFixed(1)} km/h (${dev[p[0].dataIndex]>0?'+':''}${dev[p[0].dataIndex]} vs avg)`}),xAxis:ax({data:dk,axisLabel:{color:k.faint,fontSize:10,interval:Math.floor(n/6)}}),yAxis:[ay({splitNumber:2,axisLabel:{color:k.faint,fontSize:10,formatter:v=>(v>0?'+':'')+v}}),ay({show:false,min:Math.min(...al)-3})],
   series:[line('Elevation',al,k.muted,{yAxisIndex:1,lineStyle:{width:0},areaStyle:{color:alpha(k.muted,.18)}}),line('Faster',dev.map(v=>Math.max(0,v)),k.c4,{lineStyle:{width:0},areaStyle:{color:alpha(k.c4,.85)}}),line('Slower',dev.map(v=>Math.min(0,v)),k.c1,{lineStyle:{width:0},areaStyle:{color:alpha(k.c1,.85)}})]});
  ec('rt-hs',{grid:G({top:22,left:30,right:36,bottom:20}),legend:leg,tooltip:tt(),xAxis:ax({data:dk,axisLabel:{color:k.faint,fontSize:10,interval:Math.floor(n/6)}}),yAxis:[ay({position:'left',splitNumber:3}),ay({splitNumber:3,splitLine:{show:false}})],
   series:[line('HR (bpm)',hr.map(Math.round),k.ink,{lineStyle:{width:1,color:k.ink}}),line('Speed (km/h)',sp.map(v=>+(v*3.6).toFixed(1)),k.c5,{yAxisIndex:1,lineStyle:{width:1,color:k.c5}})]})};
 $('#rt-list').innerHTML=withRoute.map(a=>`<div data-r="${esc(a.id)}">${ico(a.s,'s')}<span><b>${esc(a.name)}</b><br><span class="muted">${dlabel(a.day)} · ${a.km.toFixed(2)} km · ${mmss(a.dur)}${a.km>=1?' · '+mmss(a.dur/a.km)+'/km':''} · ${a.hr} bpm</span></span><span class="tg">${SPORT[a.s][0].toLowerCase()}</span></div>`).join('');
 $$('#rt-list [data-r]').forEach(e=>e.onclick=()=>pick(byId(e.dataset.r)));
 if(sel)setTimeout(()=>{window._map&&window._map.invalidateSize();pick(sel)},0);
 // HR-pace profile
 const bands=rng(13,i=>115+i*5),pts=[],bandSp=bands.map(()=>[]);S.runRec.forEach(({D})=>{for(let i=0;i+30<=D.N;i+=30){const s=avg(D.sp.slice(i,i+30)),h=avg(D.hr.slice(i,i+30));if(s>1.8&&h>100)pts.push([Math.round(h),Math.round(1000/s)])}D.hr.forEach((h,i)=>{const b=Math.floor((h-115)/5);if(D.sp[i]>1.8&&b>=0&&b<13)bandSp[b].push(D.sp[i])})});
 const prof=bands.map((b,i)=>bandSp[i].length>20?[b+2.5,Math.round(1000/pctl(bandSp[i],.5))]:null).filter(Boolean);
 ec('lp-c',{grid:G({top:22,left:8,right:44,bottom:22}),legend:leg,tooltip:tt({trigger:'item',formatter:p=>`${p.value[0]} bpm · ${mmss(p.value[1])} /km`}),xAxis:{type:'value',min:110,max:185,axisLine:{lineStyle:{color:k.line}},splitLine:{show:false},axisLabel:{color:k.faint,fontSize:10,showMinLabel:false,showMaxLabel:false}},yAxis:ay({inverse:true,axisLabel:{color:k.faint,fontSize:10,formatter:mmss}}),
  series:[{name:'30-s segments',type:'scatter',symbolSize:4,data:pts,itemStyle:{color:alpha(k.c1,.35)},markArea:{silent:true,data:ZT.map((t,i)=>[{xAxis:t,itemStyle:{color:alpha(k['z'+(i+2)],.08)}},{xAxis:i<3?ZT[i+1]:185}])}},line('Median pace',prof,k.c4,{symbol:'circle',symbolSize:5,showSymbol:true,lineStyle:{width:1.6,color:k.c4}})]});
 const zn=['Recovery','Aerobic','Tempo','Threshold','Maximum'],zsp=rng(5,()=>[]),zsec=[0,0,0,0,0];S.runRec.forEach(({D})=>D.hr.forEach((h,i)=>{if(h>0){const z=zi(h);zsec[z]++;if(D.sp[i]>1.8)zsp[z].push(D.sp[i])}}));const zt=zsec.reduce((s,v)=>s+v,0)||1;
 $('#lp-t').innerHTML='<tr><th>Zone</th><th>Heart rate</th><th class="r">Your pace</th><th class="r">Run time</th></tr>'+zn.map((n,i)=>`<tr><td><b style="color:var(--z${i+1})">Z${i+1}</b> ${n}</td><td>${ZR[i]} bpm</td><td class="r">${zsp[i].length>20?mmss(1000/pctl(zsp[i],.5))+'/km':'–'}</td><td class="r">${Math.round(zsec[i]/zt*100)}%</td></tr>`).join('');
 // fitness, fatigue, form + 4-week projection with the routine (loads averaged from your own sessions)
 const pd=28,pattern=w=>w%2?['gym','run','stretch','gym','run','gym','rest']:['gym','run','stretch','gym','run','run','rest'],loadOf={run:S.tRun,gym:S.tGym,stretch:S.tStr,rest:0};
 const startIdx=((new Date(S.today+'T12:00').getDay()+6)%7)+1,plan=rng(pd,i=>{const j=startIdx+i;return Math.round(loadOf[pattern(Math.floor(j/7))[j%7]])});
 let c=S.ctl,a=S.atl;const proj=plan.map(t=>{c+=(t-c)/42;a+=(t-a)/7;return[c,a,c-a]});
 const lbl=S.dates.map(d=>dlabel(d).slice(4)).concat(rng(pd,i=>dlabel(addDays(S.today,i+1)).slice(4))),nH=S.load.length;
 const sH=j=>S.load.map(v=>+v[j].toFixed(1)).concat(rng(pd,()=>null)),sP=j=>rng(nH-1,()=>null).concat([+S.load.at(-1)[j].toFixed(1)],proj.map(v=>+v[j].toFixed(1)));
 ec('ff',{grid:G({top:26,left:36,right:44,bottom:24}),legend:lg({top:0,left:0,itemWidth:9,itemHeight:9,textStyle:{color:k.muted,fontSize:11},data:['Fitness (CTL)','Fatigue (ATL)','Form (TSB)','Daily load','Planned load']}),tooltip:tt(),xAxis:ax({data:lbl,axisLabel:{color:k.faint,fontSize:10,interval:Math.floor(lbl.length/10)}}),yAxis:[ay({min:0}),ay({position:'left',min:-40,max:40,splitLine:{show:false}})],dataZoom:zoomIn(),
  series:[{name:'Daily load',type:'bar',data:S.tss.concat(plan.map(()=>null)),itemStyle:{color:alpha(k.muted,.45)},barWidth:'60%'},{name:'Planned load',type:'bar',data:rng(nH,()=>null).concat(plan),itemStyle:{color:alpha(k.muted,.18)},barWidth:'60%',barGap:'-100%'},
   {name:'Form (TSB)',type:'bar',yAxisIndex:1,data:sH(2),color:k.c3,itemStyle:{color:p=>alpha(p.value<-10?k.c4:p.value<0?k.c2:k.c3,.6)},barWidth:'60%',barGap:'-100%'},line('Fitness (CTL)',sH(0),k.c1,{lineStyle:{width:2,color:k.c1}}),line('Fatigue (ATL)',sH(1),k.c4,{lineStyle:{width:1.3,color:k.c4}}),
   line('Fitness (CTL)',sP(0),k.c1,{lineStyle:{width:1.6,type:[5,4],color:k.c1}}),line('Fatigue (ATL)',sP(1),k.c4,{lineStyle:{width:1,type:[5,4],color:k.c4}}),line('Form (TSB)',sP(2),k.c3,{yAxisIndex:1,lineStyle:{width:1.2,type:[2,3],color:k.c3},markLine:{silent:true,symbol:'none',label:{color:k.muted,fontSize:10,formatter:'today'},lineStyle:{color:k.ink,type:[3,3]},data:[{xAxis:nH-1}]}})]});
 // load
 const dl=S.dates.map(d=>dlabel(d).slice(4)),acwr=S.load.map(v=>v[0]>.5?+(v[1]/v[0]).toFixed(2):null);
 ec('ld-acwr',{grid:g,tooltip:tt(),xAxis:ax({data:dl,axisLabel:{color:k.faint,fontSize:10,interval:3}}),yAxis:ay({min:0}),series:[line('Load ratio',acwr,k.ink,{symbol:'circle',symbolSize:4,showSymbol:true,markArea:{silent:true,itemStyle:{color:alpha(k.c3,.12)},data:[[{yAxis:.8},{yAxis:1.3}]]}})]});
 const wT=S.weeks.map(w=>Math.round(S.dates.reduce((s,d,i)=>s+(S.inWeek(w,d)?S.tss[i]:0),0)));
 ec('ld-week',{grid:g,tooltip:tt({axisPointer:{type:'shadow'}}),xAxis:ax({data:wl,boundaryGap:true}),yAxis:ay({min:0}),series:[bar('TSS',wT.map((v,i)=>({value:v,label:{show:i>0&&wT[i-1]>0,position:'top',color:k.muted,fontSize:10,formatter:()=>{const p=Math.round((v-wT[i-1])/wT[i-1]*100);return(p>0?'+':'')+p+'%'}}})),alpha(k.c4,.6))]});
 const lastW=S.weeks.slice(-2);
 ec('ld-mono',{grid:g,legend:leg,tooltip:tt({axisPointer:{type:'shadow'}}),xAxis:ax({data:wd,boundaryGap:true}),yAxis:ay({min:0}),series:lastW.map((w,j)=>{const cur=j===lastW.length-1;return bar(cur?'This week':'Last week',rng(7,i=>S.tss[S.dates.indexOf(addDays(w,i))]??null),cur?k.c4:alpha(k.muted,.6),{barGap:'8%'})})});
 // recovery, steps
 const dk=Object.keys(DAYS).sort(),dkl=dk.map(d=>dlabel(d).slice(4)),rc=v=>v>=70?k.c3:v>=50?k.c2:k.c4;
 ec('rr',{grid:G({top:24,left:12,right:40,bottom:22}),legend:leg,tooltip:tt({axisPointer:{type:'shadow'},valueFormatter:v=>v!=null?v+' %':'–'}),xAxis:ax({data:dkl,boundaryGap:true}),yAxis:ay({min:0,max:100,interval:50}),series:[bar('Daily peak',dk.map(d=>({value:DAYS[d].rec_max,itemStyle:{color:rc(DAYS[d].rec_max)}})),k.c3,{barMaxWidth:40}),line('End of day',dk.map(d=>DAYS[d].rec_last),k.ink,{symbol:'circle',symbolSize:5,showSymbol:true,lineStyle:{width:1.2,color:k.ink}})]});
 ec('st',{grid:G({top:24,left:12,right:40,bottom:22}),legend:leg,tooltip:tt({axisPointer:{type:'shadow'}}),xAxis:ax({data:dkl,boundaryGap:true}),yAxis:[ay({min:0}),ay({position:'left',show:false,min:0})],series:[bar('Steps',dk.map(d=>DAYS[d].steps),k.c1),line('Active kcal',dk.map(d=>DAYS[d].kcal),k.c2,{yAxisIndex:1,symbol:'circle',symbolSize:5,showSymbol:true,lineStyle:{width:1.2,color:k.c2}})]});
 // sleep & HRV
 const hv=NV(4),mu=avg(hv),s_=sd(hv);
 ec('p-hrv',{grid:g,tooltip:tt({valueFormatter:v=>v+' ms'}),xAxis:ax({data:ND}),yAxis:ay(),series:[line('HRV',hv,k.ink,{symbol:'circle',symbolSize:6,showSymbol:true,lineStyle:{width:1.4,color:k.ink},markArea:{silent:true,itemStyle:{color:alpha(k.c3,.1)},data:[[{yAxis:mu-s_},{yAxis:mu+s_}]]}})]});
 ec('p-rhr',{grid:g,legend:leg,tooltip:tt({valueFormatter:v=>v!=null?v+' bpm':'–'}),xAxis:ax({data:ND}),yAxis:ay({minInterval:1}),series:[line('Asleep',NV(5),k.ink,{symbol:'circle',symbolSize:6,showSymbol:true,lineStyle:{width:1.4,color:k.ink}}),line('24/7 lowest',NK.map(d=>DAYS[d]?DAYS[d].hr_min:null),k.c5,{symbol:'circle',symbolSize:4,showSymbol:true,lineStyle:{width:1,type:[4,3],color:k.c5}})]});
 ec('p-sleep',{grid:g,legend:leg,tooltip:tt({axisPointer:{type:'shadow'},valueFormatter:v=>Math.floor(v)+'h'+pad(Math.round(v%1*60))}),xAxis:ax({data:ND,boundaryGap:true}),yAxis:ay({min:0,max:9,interval:3}),series:[['Deep','deep',1],['Light','light',2],['REM','rem',3]].map(([n,c_,i],j)=>({...stk(n,NV(i).map(v=>+(v/60).toFixed(2)),k[c_]),markLine:j?undefined:{silent:true,symbol:'none',lineStyle:{color:k.muted,type:[4,4]},label:{show:false},data:[{yAxis:7}]}}))});
 ec('p-bed',{grid:g,tooltip:tt({axisPointer:{type:'shadow'}}),xAxis:ax({data:ND,boundaryGap:true}),yAxis:[ay({inverse:true,min:-120,max:240,interval:60,axisLabel:{color:k.faint,fontSize:10,formatter:v=>hm((v+1440)%1440)}}),ay({position:'left',show:false,min:0,max:14})],
  series:[bar('Hours slept',NV(0),alpha(k.light,.8),{yAxisIndex:1,tooltip:{valueFormatter:v=>v.toFixed(1)+' h'}}),{name:'Fell asleep',type:'scatter',symbolSize:9,data:NV(6),itemStyle:{color:k.c1},tooltip:{valueFormatter:v=>hm((v+1440)%1440)},markLine:{silent:true,symbol:'none',lineStyle:{color:k.muted,type:[4,4]},label:{color:k.muted,fontSize:10,formatter:'01:30'},data:[{yAxis:90}]}}]});
 const sc={run:k.c2,walk:k.c5,gym:k.c1,stretch:css('--stretch')};
 ec('p-rec',{grid:g,legend:leg,tooltip:tt({trigger:'item',formatter:p=>`${p.data.n}<br>${p.value[0]} TSS → ${p.value[1]} h`}),xAxis:{type:'value',min:0,axisLine:{lineStyle:{color:k.line}},splitLine:{show:false},axisLabel:{color:k.faint,fontSize:10}},yAxis:ay({min:0,axisLabel:{color:k.faint,fontSize:10,formatter:'{value} h'}}),
  series:Object.keys(sc).map(s=>({name:SPORT[s][0],type:'scatter',symbolSize:8,itemStyle:{color:sc[s]},data:A.filter(a=>a.s===s&&a.rec_h!=null).map(a=>({value:[Math.round(a.tss),a.rec_h],n:`${esc(a.name)}, ${dlabel(a.day)}`}))}))});
 // weight-training sessions, hours by sport
 const G_=A.filter(a=>a.s==='gym').slice().reverse(),gl=G_.map(a=>dlabel(a.day).slice(4)+' '+a.t);
 ec('p-gym',{grid:G({top:24,left:12,right:40,bottom:22}),legend:leg,tooltip:tt({axisPointer:{type:'shadow'},formatter:p=>{const a=G_[p[0].dataIndex];return`<b>${esc(a.name)}</b> · ${dlabel(a.day)} ${esc(a.t)}<br>${mmss(a.dur)} · avg ${a.hr} bpm · max ${a.mx} · load ${Math.round(a.tss)}`}}),xAxis:ax({data:gl,boundaryGap:true,axisLabel:{color:k.faint,fontSize:10}}),yAxis:[ay({min:0,axisLabel:{color:k.faint,fontSize:10,formatter:'{value}′'}}),ay({position:'left',show:false,min:60})],
  series:[bar('Weight training',G_.map(a=>Math.round(a.dur/60)),k.c1),{name:'Avg HR',type:'scatter',yAxisIndex:1,symbolSize:7,data:G_.map(a=>a.hr),itemStyle:{color:k.ink}}]});
 ec('p-hrs',{grid:G({top:24,left:12,right:40,bottom:22}),legend:leg,tooltip:tt({axisPointer:{type:'shadow'},valueFormatter:v=>v.toFixed(1)+' h'}),xAxis:ax({data:wl,boundaryGap:true}),yAxis:ay({min:0}),series:[['run','Running',k.c2],['gym','Weights',k.c1],['stretch','Stretching',css('--stretch')],['walk','Walking',k.c5]].map(([s,n,c_])=>stk(n,wk(L=>+(L.filter(a=>a.s===s).reduce((t,a)=>t+a.dur,0)/3600).toFixed(2)),c_))});
 // runs
 const runCol=i=>[k.c4,k.c1,k.c3,k.c2,k.c5][i%5],rname=x=>dlabel(x.r.day);
 ec('p-ef',{grid:g,legend:leg,tooltip:tt({trigger:'item',formatter:p=>`${p.seriesName} · km ${p.value[0]}: EF ${p.value[1]}`}),xAxis:{type:'value',min:1,minInterval:1,axisLine:{lineStyle:{color:k.line}},splitLine:{show:false},axisLabel:{color:k.faint,fontSize:10,formatter:'km {value}'}},yAxis:ay({axisLabel:{color:k.faint,fontSize:10,formatter:v=>v.toFixed(2)}}),
  series:S.runRec.map((x,i)=>line(rname(x),x.sp.map(s=>[s.km,+s.ef.toFixed(3)]),runCol(i),{symbol:'circle',symbolSize:6,showSymbol:true,lineStyle:{width:1.2,color:runCol(i)}}))});
 ec('p-cad',{grid:g,legend:leg,tooltip:tt({axisPointer:{type:'shadow'},valueFormatter:v=>v?Math.round(v)+' spm':'–'}),xAxis:ax({data:rng(Math.max(1,...S.runRec.map(x=>x.sp.length)),i=>'km '+(i+1)),boundaryGap:true}),yAxis:ay({min:140,max:180}),
  series:S.runRec.map((x,i)=>bar(rname(x),x.sp.map(s=>Math.round(s.cad)),runCol(i),{barGap:'10%',markLine:i?undefined:{silent:true,symbol:'none',lineStyle:{color:k.muted,type:[4,3]},label:{color:k.muted,fontSize:10,formatter:'165'},data:[{yAxis:165}]}}))});
 const d=S.dec;$('#dc-k').innerHTML=d?[['Pace 1st → 2nd',`${mmss(1000/d.a.sp)} → ${mmss(1000/d.b.sp)}`],['HR 1st → 2nd',`${Math.round(d.a.hr)} → ${Math.round(d.b.hr)}`],['Drift',d.pct.toFixed(1)+'<small> %</small>']].map(([a_,b])=>`<div><div class="k">${a_}</div><div class="v" style="font-size:16px">${b}</div></div>`).join(''):'<span class="muted">No run with a recording yet.</span>';
 if(S.runRec[0]){const D=S.runRec[0].D,w=120,n=Math.floor(D.N/30),efr=rng(n,i=>{if(i*30<120)return null;const a_=Math.max(0,i*30-w/2),b=Math.min(D.N,i*30+w/2),sp=avg(D.sp.slice(a_,b)),hr=avg(D.hr.slice(a_,b).filter(v=>v>0));return sp>1?+(sp*60/hr).toFixed(3):null});
  ec('dc-c',{grid:G({top:8,left:8,right:40,bottom:20}),tooltip:tt({valueFormatter:v=>v!=null?'EF '+v:'–'}),xAxis:ax({data:rng(n,i=>mmss(i*30)),axisLabel:{color:k.faint,fontSize:10,interval:Math.floor(n/5)}}),yAxis:ay({axisLabel:{color:k.faint,fontSize:10,formatter:v=>v.toFixed(2)}}),
   series:[line('Speed per beat (2-min window)',efr,k.c1,{lineStyle:{width:1.3,color:k.c1},connectNulls:true,markArea:{silent:true,itemStyle:{color:alpha(k.muted,.06)},data:[[{xAxis:mmss(Math.floor(n/2)*30)},{xAxis:mmss((n-1)*30)}]]}})]})}
 const p150=S.runRec.map(({D})=>{const v=D.sp.filter((s,i)=>s>1.8&&D.hr[i]>=140&&D.hr[i]<=150);return v.length>30?Math.round(1000/pctl(v,.5)):null});
 ec('p-p150',{grid:g,tooltip:tt({trigger:'item',formatter:p=>`${esc(p.name)}: ${mmss(p.value)} /km`}),xAxis:ax({data:S.runRec.map(rname),boundaryGap:true}),yAxis:ay({inverse:true,axisLabel:{color:k.faint,fontSize:10,formatter:mmss}}),series:[{type:'scatter',symbolSize:14,data:p150.map((v,i)=>({value:v,itemStyle:{color:runCol(i)}})),label:{show:true,position:'right',color:k.text,fontSize:11,fontWeight:600,formatter:p=>p.value?mmss(p.value)+'/km':''}}]});
};

// HR per km vs average on the activity detail
const _detailRender=detailRender;
detailRender=function(){_detailRender();const a=byId(actId),D=recording(a);if(!D||!D.gps)return;
 const L=[];let s=0;for(let i=1;i<=Math.ceil(a.km);i++){let e=D.d.findIndex(v=>v>=i*1000);if(e<0)e=D.N;if(e-s>20)L.push(avg(D.hr.slice(s,e)));s=e}
 const m=avg(D.hr),dev=L.map(v=>+(v-m).toFixed(1));
 ec('d-hrkm',{grid:G({top:6,left:4,right:40,bottom:20}),tooltip:tt({axisPointer:{type:'shadow'},formatter:p=>`km ${p[0].dataIndex+1}: ${Math.round(L[p[0].dataIndex])} bpm (${p[0].value>0?'+':''}${p[0].value})`}),xAxis:ax({data:L.map((_,i)=>i+1),boundaryGap:true}),yAxis:ay({splitNumber:2}),
  series:[{type:'bar',barWidth:'55%',data:dev.map(v=>({value:v,itemStyle:{color:v>0?k.c4:k.c1}}))}]})};

actId=A[0]?.id;theme();show('dash');
