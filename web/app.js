"use strict";
const $ = id => document.getElementById(id);
let dataset = null, visible = [];
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
function render(){
 if(!dataset)return;
 const name=$("draw").value, strategy=$("strategy").value;
 const g=dataset.games[name];if(!g||!OPTIONS.has(strategy))return;
 try{
  const scores=getScores(g,strategy),n=Number($("count").value);
  if(!validProbabilityRows(scores)||![5,10,20,50].includes(n))throw Error("Invalid rankings");
  visible=combinations(scores).slice(0,n);
  // Present scores as relative rankings, not certified odds.
  $("numbers").replaceChildren(...visible.map((entry,i)=>{
   const el=document.createElement("div");el.className="number";
   const rank=document.createElement("span");rank.className="rank";rank.textContent="#"+String(i+1).padStart(2,"0");
   const number=document.createElement("strong");number.textContent=entry.n;
   const score=document.createElement("small");score.textContent=(entry.p*100).toFixed(3)+"% score";
   el.append(rank,number,score);return el;
  }));
  $("total").textContent=g.draws.toLocaleString();
  $("last").textContent=g.recent[0];
  $("lastDate").textContent=g.last_draw;
  $("holdout").textContent=g.holdout_draws.toLocaleString();
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
  $("backtest").textContent=b?`Unseen ${b.draws} draws · Top 1: ${(100*b.coverage.top_1).toFixed(2)}% · Top 10: ${(100*b.coverage.top_10).toFixed(2)}% (fair baseline 1%) · Top 20: ${(100*b.coverage.top_20).toFixed(2)}% · Mean position log loss: ${Number(b.mean_position_log_loss).toFixed(3)} (uniform: 2.303).`:"Older output format: independent test diagnostics unavailable.";
  $("alert").className="alert ok";
  $("alert").textContent=`Showing ${name} research through ${g.last_draw}. Dataset generated ${new Date(dataset.generated_at).toLocaleString()}. ${strategy==="model"?"Automatic validation-selected models.":"Exploratory ranking: "+$("strategy").selectedOptions[0].textContent+"."} Historical patterns are not verified winning odds.`;
 }catch(e){visible=[];$("alert").className="alert error";$("alert").textContent=e.message;}
}
async function boot(){
 try{
  const response=await fetch("data/predictions.json",{cache:"no-store"});
  if(!response.ok)throw Error("Results are not published yet (HTTP "+response.status+").");
  dataset=validate(await response.json());
  $("dataStatus").textContent="Official archives connected";
  document.querySelector(".status").classList.add("ok");
  render();
 }catch(error){
  $("dataStatus").textContent="Data unavailable";
  document.querySelector(".status").classList.add("error");
  $("alert").className="alert error";
  $("alert").textContent=error.message+" Check the latest training run on GitHub Actions.";
 }
}
for(const key of ["draw","strategy","count"])$(key).addEventListener("change",render);
$("rerank").addEventListener("click",render);
$("copy").addEventListener("click",async()=>{
 if(!visible.length)return;
 const text=visible.map(x=>x.n).join(", ");
 try{await navigator.clipboard.writeText(text);$("copy").textContent="Copied!";}
 catch{window.prompt("Copy these combinations:",text);}
 setTimeout(()=>$("copy").textContent="Copy displayed combinations",1600);
});
boot();