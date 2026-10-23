"use strict";
const $ = id => document.getElementById(id);
const SESSIONS = ["morning", "day", "evening", "night"];
const TIMES = {morning:[10,0],day:[12,27],evening:[18,0],night:[22,12]};
const CENTRAL = "America/Chicago";
let data = null;

function localParts(instant) {
  return Object.fromEntries(new Intl.DateTimeFormat("en-US", {timeZone:CENTRAL,
    year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"})
    .formatToParts(instant).filter(part=>part.type!=="literal").map(part=>[part.type,Number(part.value)]));
}
function nextScheduled(now=new Date()) {
  const local=localParts(now), minuteNow=local.hour*60+local.minute;
  for(let offset=0;offset<8;offset++) {
    const day=new Date(Date.UTC(local.year,local.month-1,local.day+offset,12));
    if(day.getUTCDay()===0) continue;
    for(const session of SESSIONS) {
      const [hour,minute]=TIMES[session];
      if(offset===0 && hour*60+minute<=minuteNow) continue;
      const key=day.toISOString().slice(0,10);
      return {session,date:key,label:day.toLocaleDateString("en-US",{timeZone:"UTC",weekday:"long",month:"long",day:"numeric"}),
        time:new Date(Date.UTC(2020,0,1,hour,minute)).toLocaleTimeString("en-US",{timeZone:"UTC",hour:"numeric",minute:"2-digit"})};
    }
  }
  throw Error("Draw schedule unavailable");
}
const when = value => value ? new Intl.DateTimeFormat("en-US",{timeZone:CENTRAL,dateStyle:"medium",timeStyle:"short"}).format(new Date(value)) : "not recorded";
const pct = value => value == null ? "—" : (value*100).toFixed(2)+"%";
const title = session => session[0].toUpperCase()+session.slice(1);
function el(tag, className, content) {
  const node=document.createElement(tag);
  if(className) node.className=className;
  if(content!=null) node.textContent=content;
  return node;
}
function valid(dataset) {
  if(dataset?.schema_version!==9 || !dataset.generated_at || !dataset.sessions || !Array.isArray(dataset.results)) throw Error("Published data needs a V2 refresh.");
  for(const session of SESSIONS) {
    const item=dataset.sessions[session], picks=item?.predictions;
    if(!Array.isArray(picks) || picks.length!==10 || new Set(picks.map(p=>p.group)).size!==10 ||
       picks.some(p=>!/^\d{3}$/.test(p.group) || [...p.group].sort().join("")!==p.group)) throw Error("Invalid "+session+" forecast.");
  }
  return dataset;
}
function pickCard(pick, index) {
  const mode=$("viewMode").value;
  const card=el("div","pick");
  card.append(el("span","rank",String(index+1).padStart(2,"0")),el("strong",null,
    mode==="any"||mode==="combo" ? pick.group : pick.representative||pick.group));
  const exact=mode==="exact";
  const detail=el("span","pick-detail",`Model ${pct(exact ? pick.exact_probability : pick.model_probability)} · Fair ${pct(exact ? .001 : pick.fair_probability)}`+
    (mode==="combo" ? ` · ${[...new Set(permutations(pick.group))].join("/")}` : ""));
  card.append(detail);
  return card;
}
function permutations(number) {
  return [number[0]+number[1]+number[2],number[0]+number[2]+number[1],
    number[1]+number[0]+number[2],number[1]+number[2]+number[0],
    number[2]+number[0]+number[1],number[2]+number[1]+number[0]];
}
function renderTop() {
  const next=nextScheduled(), item=data.sessions[next.session];
  $("nextTitle").textContent=`${title(next.session)} · ${next.label} · ${next.time} Central`;
  const target=item.target_draw.slice(0,10);
  $("nextMeta").textContent=`Published ${when(item.published_at)} · Official results through ${item.last_draw}`+
    (target!==next.date ? ` · Forecast targets ${target}; waiting for the next official refresh.` : "");
  $("topPicks").replaceChildren(...(target===next.date ? item.predictions.map(pickCard) :
    [el("p","muted","No eligible forecast for this next draw yet; awaiting verified official data.")]));
}
function renderSessions() {
  const target=$("sessions");
  target.replaceChildren(...SESSIONS.map(session=>{
    const item=data.sessions[session], card=el("article","session-card");
    card.append(el("h3",null,title(session)),el("p","muted",`Next ${item.target_draw.slice(0,10)} · Published ${when(item.published_at)}`));
    card.append(el("p","combos",item.predictions.map(p=>p.group).join(" · ")));
    card.append(el("p","muted",`Latest official: ${item.latest_result} on ${item.last_draw}`));
    return card;
  }));
}
function renderHistory() {
  const target=$("historyDate"), rows=data.results.filter(row=>row.draw_date===target.value)
    .sort((a,b)=>SESSIONS.indexOf(a.session)-SESSIONS.indexOf(b.session));
  if(!rows.length) {$("history").replaceChildren(el("p","muted","No verified record for this date."));return;}
  $("history").replaceChildren(...rows.map(row=>{
    const card=el("article","history-card");
    card.append(el("h3",null,`${title(row.session)} · Official ${row.actual}`));
    const mode=$("viewMode").value;
    const outcome=!row.predictions ? "No eligible forecast" : mode==="exact" ?
      (row.exact_hit===null ? "Exact match unavailable" : row.exact_hit ? "Exact order hit" : "No exact order hit") :
      row.hit_rank==null ? "No Any Order match" : `${mode==="combo"?"Combo":mode==="exact_any"?"Exact/Any":"Any Order"} hit #${row.hit_rank}`;
    const exact=row.exact_hit===null ? "Exact: not recorded" : row.exact_hit ? "Exact order hit" : "No exact order hit";
    card.append(el("p",row.hit_rank ? "hit" : "muted",`${outcome} · ${exact}`));
    card.append(el("p","combos",row.predictions?.map(p=>mode==="exact"||mode==="exact_any" ? p.representative||p.group : p.group).join(" · ") || "No snapshot was published before this draw."));
    card.append(el("p","muted",`Published ${when(row.published_at)} · Verified ${when(row.verified_at)}`));
    if(row.predictions?.some(p=>p.model_probability!=null)) {
      card.append(el("p","muted",`Top 10 model estimate ${pct(row.estimated_coverage)} · Fair benchmark ${pct(row.fair_coverage)}`));
      const detail=el("details");detail.append(el("summary",null,"Individual model estimates"),
        el("p","muted",row.predictions.map(p=>`${p.group} ${pct(p.model_probability)}`).join(" · ")));
      card.append(detail);
    }
    return card;
  }));
}
function renderMetrics() {
  const host=$("metrics");host.replaceChildren();
  for(const session of SESSIONS) {
    const historical=data.backtest?.[session]||{}, forward=data.forward?.[session]||{};
    const card=el("article","metric-card");card.append(el("h3",null,title(session)));
    for(const [label,report] of [["Walk-forward",historical],["Published forward",forward]]) {
      card.append(el("h4",null,`${label} · ${report.draws||0} scored draws`));
      for(const k of [1,5,10]) card.append(el("p","metric-line",`Any Order Top ${k}: ${pct(report[`top_${k}`])} observed · ${pct(report[`fair_top_${k}`])} fair`));
      if(report.estimated_top_10!=null) card.append(el("p","muted",`Top 10 model estimate: ${pct(report.estimated_top_10)}; observed: ${pct(report.top_10)}`));
    }
    host.append(card);
  }
  $("calibration").textContent="Calibration compares average uncalibrated model coverage estimates with actual Top 10 hit rates. Small forward samples are volatile; the fair benchmark counts distinct permutations, including repeated digits.";
}
function render() {
  renderTop();renderSessions();renderHistory();renderMetrics();
  $("updated").textContent=`Last published ${when(data.generated_at)}.`;
  $("status").textContent="Official archive connected";
}
async function refresh() {
  try {
    const response=await fetch("data/predictions.json",{cache:"no-store"});
    if(!response.ok) throw Error(`Data request failed (${response.status}).`);
    const incoming=valid(await response.json());
    const previous=data?.generated_at;
    data=incoming;
    if(!$("historyDate").value) $("historyDate").value=data.results.map(r=>r.draw_date).sort().at(-1)||nextScheduled().date;
    if(previous!==data.generated_at) render();
    else renderTop();
  } catch(error) {$("status").textContent=error.message;}
}
$("historyDate").addEventListener("change",()=>{if(data)renderHistory();});
$("viewMode").addEventListener("change",()=>{if(data){renderTop();renderHistory();}});
refresh();
setInterval(()=>{if(!document.hidden)refresh();},120000);
setInterval(()=>{if(data)renderTop();},60000);
