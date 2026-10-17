"use strict";
const $ = id => document.getElementById(id);
const HOUSTON_ZONE = "America/Chicago";
const houstonTime = value => new Intl.DateTimeFormat("en-US",{timeZone:HOUSTON_ZONE,month:"short",day:"numeric",year:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"}).format(new Date(value));
const DRAW_TIMES=[["morning",10,0],["day",12,27],["evening",18,0],["night",22,12]];
function nextHoustonDraw(now=new Date()){
 const parts=Object.fromEntries(new Intl.DateTimeFormat("en-US",{timeZone:HOUSTON_ZONE,year:"numeric",month:"numeric",day:"numeric",hour:"numeric",minute:"numeric",hourCycle:"h23"}).formatToParts(now).filter(p=>p.type!=="literal").map(p=>[p.type,+p.value]));
 const elapsed=parts.hour*60+parts.minute;
 for(let offset=0;offset<8;offset++){
  const day=new Date(Date.UTC(parts.year,parts.month-1,parts.day+offset,12));
  if(day.getUTCDay()===0)continue;
  for(const [session,hour,minute] of DRAW_TIMES){
   if(offset===0 && hour*60+minute<=elapsed)continue;
   const label=day.toLocaleDateString("en-US",{timeZone:"UTC",weekday:"long",month:"short",day:"numeric"});
   return {session,label,time:new Date(Date.UTC(2020,0,1,hour,minute)).toLocaleTimeString("en-US",{timeZone:"UTC",hour:"numeric",minute:"2-digit"})};
  }
 }
 throw Error("Next draw unavailable");
}
function showNextDraw(){
 const next=nextHoustonDraw();
 const names={morning:"Morning",day:"Day",evening:"Evening",night:"Night"};
 $("nextDraw").textContent="Next scheduled Houston draw: "+names[next.session]+" · "+next.label+" at "+next.time+" Central. Rankings update after new official results are published.";
 for(const opt of $("draw").options){
  const label=names[opt.value]+" · "+({"morning":"10:00 AM","day":"12:27 PM","evening":"6:00 PM","night":"10:12 PM"})[opt.value];
  opt.textContent=(opt.value===next.session?"NEXT · ":"")+label;
 }
 return next.session;
}
let dataset = null, visible = [], liveHistory = null;
const strategyDescriptions={model:"Recommended: automatically selects the model that did best on earlier historical validation; not a guarantee.",random_forest:"Random Forest: multiple decision trees learn historical digit features.",gradient_boosting:"Gradient Boosting: sequential trees model past features.",ensemble:"Combined models: averages Random Forest, boosted trees and frequency baseline.",smoothed_frequency:"Historical frequency: digit counts with smoothing.",hot:"Hot digits: ranks digits that occurred more often in the last 40 draws.",cold:"Cold digits: ranks digits that occurred less often; they are not overdue.",uniform:"Fair baseline: all 1,000 exact orders have equal scores."};
const OPTIONS = new Set(["model","random_forest","gradient_boosting","ensemble","smoothed_frequency","hot","cold","uniform"]);
const digits = Array.from({length:10},(_,i)=>i);
function validProbabilityRows(probs){
 return Array.isArray(probs)&&probs.length===3&&probs.every(row=>Array.isArray(row)&&row.length===10&&row.every(x=>typeof x==="number"&&Number.isFinite(x)&&x>=0)&&Math.abs(row.reduce((a,b)=>a+b,0)-1)<.001);
}
function validate(data){
 if(!data||typeof data!=="object"||!data.games||!data.generated_at||!Number.isFinite(Date.parse(data.generated_at)))throw Error("Invalid published dataset");
 for(const name of ["morning","day","evening","night"]){
  const g=data.games[name];
  if(!g||!validProbabilityRows(g.probabilities)||!Array.isArray(g.recent)||!g.recent.length||!g.recent.every(v=>/^\d{3}$/.test(v))||!Array.isArray(g.validation)||g.validation.length!==3||!Number.isFinite(g.draws)||!Number.isFinite(g.holdout_draws))throw Error("Invalid "+name+" archive");
 }
 return data;
}
function normalize(a){const s=a.reduce((x,y)=>x+y,0);return a.map(v=>v/s);}
function frequencies(recent){const counts=Array(10).fill(0);recent.slice(0,40).forEach(number=>[...number].forEach(d=>counts[+d]++));return counts;}
function getScores(g,strategy){
 if(["random_forest","gradient_boosting","ensemble","smoothed_frequency"].includes(strategy)){
  const p=g.model_probabilities?.[strategy];
  if(!validProbabilityRows(p))throw Error("The requested model has not been trained yet. Run the data refresh.");
  return p;
 }
 if(strategy==="uniform")return Array.from({length:3},()=>Array(10).fill(.1));
 if(strategy==="hot"||strategy==="cold"){
  const counts=frequencies(g.recent),w=counts.map(v=>strategy==="hot"?v+1:1/(v+1)),p=normalize(w);
  return [p,p,p];
 }
 return g.probabilities;
}
function combinations(probs){
 const list=[];
 for(const i of digits)for(const j of digits)for(const k of digits)list.push({n:`${i}${j}${k}`,p:probs[0][i]*probs[1][j]*probs[2][k]});
 return list.sort((a,b)=>b.p-a.p||a.n.localeCompare(b.n));
}

function boxCombinations(probs){
 const groups = new Map();
 for(const entry of combinations(probs)){
  const key = [...entry.n].sort().join("");
  if(!groups.has(key))groups.set(key,{n:key,p:0,permutations:[]});
  const group=groups.get(key);
  group.p += entry.p;
  group.permutations.push(entry.n);
 }
 return [...groups.values()].sort((a,b)=>b.p-a.p||a.n.localeCompare(b.n));
}


function percent(n){return (100*n).toFixed(2)+"%";}
function renderLive(){
 const session=$("draw").value;
 const rows=liveHistory?.games?.[session]||[];
 $("liveStatus").textContent=rows.length?"COMPLETED OFFICIAL DRAWS":"NO COMPLETED TESTS YET";
 $("liveCount").textContent=String(rows.length);
 $("confidenceLive").textContent=rows.length?percent(rows.filter(r=>r.exact_any_hit).length/rows.length):"—";
 $("confidenceSample").textContent=rows.length?`${rows.length} verified live draws; fair rate depends on selected permutations`:"No verified live outcomes yet";
 const metrics=[
  ["exact_hit","exact_fair_probability","liveExact","liveExactBaseline"],
  ["exact_any_hit","exact_any_fair_probability","liveAny","liveAnyBaseline"],
  ["box_hit","box_fair_probability","liveBox","liveBoxBaseline"]
 ];
 for(const [key,base,el,baseline] of metrics){
  const actual=rows.filter(row=>row[key]===true).length;
  const fair=rows.length?rows.reduce((sum,row)=>sum+Number(row[base]||0),0)/rows.length:0;
  $(el).textContent=rows.length?percent(actual/rows.length):"—";
  $(baseline).textContent=rows.length?`${actual} of ${rows.length} matches · fair expectation ${percent(fair)}`:"Waiting for live results";
 }
 $("liveDetails").textContent=rows.length
  ? "Live records use the recommended model's previous top five, saved before the next draw. Other model selectors do not change this scorecard. Small samples fluctuate substantially."
  : "No eligible completed live prediction has been scored yet. The first verified outcome will appear after the next official draw is processed.";
 $("liveRows").replaceChildren(...rows.slice(-12).reverse().map(item=>{
  const row=document.createElement("div");row.className="live-row";
  const date=document.createElement("span");date.textContent=item.draw_date+" · "+item.actual;
  const result=document.createElement("strong");result.textContent=item.exact_hit?"EXACT HIT":item.exact_any_hit?"ANY HIT":item.box_hit?"BOX HIT":"NO MATCH";
  result.className=item.exact_hit||item.exact_any_hit||item.box_hit?"match":"miss";
  const picks=document.createElement("small");picks.textContent=" · Earlier top 5: "+item.exact_picks.join(", ");
  row.append(date,result,picks);return row;
 }));
}
async function loadLive(){
 try{
  const response=await fetch("data/live_history.json",{cache:"no-store"});
  if(!response.ok)throw Error("no live records yet");
  const next=await response.json();
  if(!next||typeof next.games!=="object")throw Error("invalid live data");
  liveHistory=next;
 }catch(error){if(!liveHistory)liveHistory={games:{}};}
 renderLive();
}

function render(){
 if(!dataset)return;
 const name=$("draw").value, strategy=$("strategy").value;
 const g=dataset.games[name];if(!g||!OPTIONS.has(strategy))return;
 try{
  const scores=getScores(g,strategy),n=Number($("count").value);
  if(!validProbabilityRows(scores)||![5,10,20,50].includes(n))throw Error("Invalid rankings");
  const play=$("playType").value;
  if(!["straight","box","both","combo"].includes(play))throw Error("Invalid play type");
  if(play==="both"){
    const chosen=boxCombinations(scores).slice(0,n);
    visible=chosen.map(group=>{
      const exact=combinations(scores).filter(entry=>[...entry.n].sort().join("")===group.n)[0];
      return {n:exact.n,p:group.p,permutations:group.permutations};
    });
  }else visible=(play==="box"||play==="combo"?boxCombinations(scores):combinations(scores)).slice(0,n);
  $("playBadge").textContent=({box:"ANY ORDER",straight:"EXACT ORDER",both:"EXACT / ANY ORDER",combo:"COMBO · ALL EXACT ORDERS"})[play];
  $("playHelp").textContent=({straight:"Only the precise three-digit order matches. Fair-draw odds: 1 in 1,000.",box:"Any Order: all distinct permutations are grouped (1, 3 or 6).",both:"Exact/Any: use the displayed number for both Exact and Any Order on one ticket. A 50¢ base play costs $1 total; FIREBALL is extra.",combo:"Combo covers every distinct exact-order permutation of the selected digits; total ticket cost depends on 1, 3 or 6 ways."})[play]+" These are exploratory model scores, not certified odds.";
  // Present scores as relative rankings, not certified odds.
  $("numbers").replaceChildren(...visible.map((entry,i)=>{
   const el=document.createElement("div");el.className="number";
   const rank=document.createElement("span");rank.className="rank";rank.textContent="#"+String(i+1).padStart(2,"0");
   const number=document.createElement("strong");number.textContent=entry.n;
   const score=document.createElement("small");score.textContent=(entry.p*100).toFixed(3)+"% score"+((play==="box"||play==="combo")?" · "+entry.permutations.length+" ways":"");
   el.append(rank,number,score);return el;
  }));
  $("total").textContent=g.draws.toLocaleString();
  renderLive();
  $("last").textContent=g.recent[0];
  $("lastDate").textContent=g.last_draw;
  $("holdout").textContent=g.holdout_draws.toLocaleString();
  const mlSelected=(g.selected_models||g.validation.map(m=>m.selected)).filter(m=>m!=="smoothed_frequency").length;
  $("confidenceTitle").textContent=g.exact_any_selection?"Selected for this session: "+g.exact_any_selection.model.replaceAll("_"," "):(mlSelected?"Models selected for "+mlSelected+" of 3 digit positions":"Historical frequency baseline selected");
  $("confidenceDetail").textContent="This is validation-based model selection, not a reliable winning-confidence percentage. The same 3 digits can be used for Exact, Any or Exact/Any; matching rules and ticket costs differ. FIREBALL is optional and not scored.";
  $("confidenceBacktest").textContent=g.backtest?.box?.coverage?.top_5!=null?percent(g.backtest.box.coverage.top_5):"—";
  const selected=g.selected_models||g.validation.map(m=>m.selected);
  $("performance").textContent=selected.filter(m=>m!=="smoothed_frequency").length+" / 3";
  const freq=frequencies(g.recent),max=Math.max(1,...freq);
  $("bars").replaceChildren(...freq.map((count,i)=>{
   const row=document.createElement("div");row.className="barrow";
   const index=document.createElement("strong");index.textContent=i;
   const track=document.createElement("div");track.className="track";
   const fill=document.createElement("div");fill.className="fill";fill.style.width=(100*count/max)+"%";track.append(fill);
   const countLabel=document.createElement("span");countLabel.textContent=count;
   row.append(index,track,countLabel);return row;
  }));
  $("metrics").replaceChildren(...g.validation.map(m=>{
   const el=document.createElement("div");el.className="metric";
   const label=document.createElement("span");label.textContent="Digit "+m.position+" · "+String(m.selected).replaceAll("_"," ");
   const result=document.createElement("strong");result.textContent="Test log loss: "+Number(m.test_log_loss??m.model_log_loss).toFixed(3);
   el.append(label,result);return el;
  }));
  const b=g.backtest;
  const report=(play==="box"||play==="combo"||play==="both")?b?.box:b?.straight;
  if(play==="both"&&b?.straight&&b?.box){
    $("backtest").textContent=`Exact/Any on unseen ${b.draws} draws: Exact top 5 ${(100*b.straight.coverage.top_5).toFixed(2)}% (fair 0.50%); Any-order top 5 groups ${(100*b.box.coverage.top_5).toFixed(2)}% (fair ${(100*b.box.fair_expected_coverage.top_5).toFixed(2)}%). Any-order groups correspond to the displayed Exact/Any play; the test does not account for payouts.`;
  } else {
    $("backtest").textContent=report?`Unseen ${b.draws} draws · ${play==="box"||play==="combo"?"Unique Any Order / Combo group":"Exact Order"} top 1: ${(100*report.coverage.top_1).toFixed(2)}% (fair ${(100*report.fair_expected_coverage.top_1).toFixed(2)}%) · Top 10: ${(100*report.coverage.top_10).toFixed(2)}% (fair ${(100*report.fair_expected_coverage.top_10).toFixed(2)}%) · Top 20: ${(100*report.coverage.top_20).toFixed(2)}% (fair ${(100*report.fair_expected_coverage.top_20).toFixed(2)}%).`:"This play-type backtest is not published yet. Await the next model refresh.";
  }
  $("alert").className="alert ok";
  $("alert").textContent=`Showing ${name} research through ${g.last_draw}. Model trained ${houstonTime(dataset.generated_at)}. Official results checked ${houstonTime(dataset.official_checked_at||dataset.generated_at)}. ${strategy==="model"?"Automatic validation-selected models.":"Exploratory ranking: "+$("strategy").selectedOptions[0].textContent+"."} Historical patterns are not verified winning odds.`;
 }catch(e){visible=[];$("alert").className="alert error";$("alert").textContent=e.message;}
}
async function boot(announce=false){
 try{
  const response=await fetch("data/predictions.json",{cache:"no-store"});
  if(!response.ok)throw Error("Results are not published yet (HTTP "+response.status+").");
  const incoming=validate(await response.json());
  const previous=dataset?.generated_at;
  dataset=incoming;
  $("dataStatus").textContent="Official archives connected";
  document.querySelector(".status").classList.add("ok");
  render();
  await loadLive();
  if(announce&&previous==dataset.generated_at){$("alert").textContent="No new official dataset published since "+houstonTime(dataset.generated_at)+". Your rankings remain unchanged.";}
 }catch(error){
  if(dataset&&announce){$("alert").className="alert error";$("alert").textContent="Could not check for newer data. Your previously loaded rankings remain available.";return;}
  $("dataStatus").textContent="Data unavailable";
  document.querySelector(".status").classList.add("error");
  $("alert").className="alert error";
  $("alert").textContent=error.message+" Check the latest training run on GitHub Actions.";
 }
}
for(const key of ["draw","strategy","count","playType"])$(key).addEventListener("change",()=>{sessionStorage.setItem("pick3-"+key,$(key).value);render();});
for(const key of ["draw","strategy","count","playType"]){const stored=sessionStorage.getItem("pick3-"+key);if(stored&&[...$(key).options].some(o=>o.value===stored))$(key).value=stored;}
if(!sessionStorage.getItem("pick3-draw"))$("draw").value=showNextDraw();else showNextDraw();
$("strategy").addEventListener("change",()=>{$("modelExplainer").textContent=strategyDescriptions[$("strategy").value];});
$("modelExplainer").textContent=strategyDescriptions[$("strategy").value];
$("copy").addEventListener("click",async()=>{
 if(!visible.length)return;
 const text=visible.map(x=>x.n+(x.permutations?" ["+x.permutations.join("/") +"]":"")).join(", ");
 try{await navigator.clipboard.writeText(text);$("copy").textContent="Copied!";}
 catch{window.prompt("Copy these combinations:",text);}
 setTimeout(()=>$("copy").textContent="Copy displayed combinations",1600);
});
$("refreshData").addEventListener("click",async()=>{const btn=$("refreshData");btn.disabled=true;btn.textContent="Checking…";try{await boot(true);}finally{btn.disabled=false;btn.textContent="↻ Check latest results";}});
boot();