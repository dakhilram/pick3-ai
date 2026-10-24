"use strict";

const SESSIONS = ["morning", "day", "evening", "night"];
const TIMES = {morning: [10, 0], day: [12, 27], evening: [18, 0], night: [22, 12]};
const CENTRAL = "America/Chicago";
const $ = id => document.getElementById(id);
let data = null;
let selectedSession = null;
let feedbackTimer = null;

function localParts(instant) {
  return Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone: CENTRAL, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  }).formatToParts(instant).filter(part => part.type !== "literal")
    .map(part => [part.type, Number(part.value)]));
}

function nextScheduled(now = new Date()) {
  const local = localParts(now);
  const minuteNow = local.hour * 60 + local.minute;
  for (let offset = 0; offset < 8; offset++) {
    const day = new Date(Date.UTC(local.year, local.month - 1, local.day + offset, 12));
    if (day.getUTCDay() === 0) continue;
    for (const session of SESSIONS) {
      const [hour, minute] = TIMES[session];
      if (offset === 0 && hour * 60 + minute <= minuteNow) continue;
      return {
        session,
        date: day.toISOString().slice(0, 10),
        label: day.toLocaleDateString("en-US", {timeZone: "UTC", weekday: "long", month: "long", day: "numeric"}),
        time: new Date(Date.UTC(2020, 0, 1, hour, minute)).toLocaleTimeString("en-US", {timeZone: "UTC", hour: "numeric", minute: "2-digit"})
      };
    }
  }
  throw Error("Draw schedule unavailable");
}

const when = value => value ? new Intl.DateTimeFormat("en-US", {
  timeZone: CENTRAL, dateStyle: "medium", timeStyle: "short"
}).format(new Date(value)) + " Central" : "not recorded";
const pct = value => value == null ? "—" : (value * 100).toFixed(2) + "%";
const title = session => session[0].toUpperCase() + session.slice(1);
const combination = number => [...number].sort().join("");
const numbers = item => item.predictions.map(pick => pick.group);
const allNumbersText = item => numbers(item).join(", ");

function freshness(item, now = new Date()) {
  const target = Date.parse(item?.target_draw);
  if (!Number.isFinite(target)) return "Update Delayed";
  if (target > now.getTime()) return "Current";
  const drawDate = item.target_draw.slice(0, 10);
  if ((item.last_draw || "") < drawDate && now.getTime() - target < 2 * 60 * 60 * 1000) {
    return "Awaiting Official Result";
  }
  return "Update Delayed";
}

function valid(dataset) {
  if (dataset?.schema_version !== 9 || !dataset.generated_at || !dataset.sessions || !Array.isArray(dataset.results)) {
    throw Error("Published data needs a V2 refresh.");
  }
  for (const session of SESSIONS) {
    const picks = dataset.sessions[session]?.predictions;
    if (!Array.isArray(picks) || picks.length !== 10 || new Set(picks.map(p => p.group)).size !== 10 ||
        picks.some(p => !/^\d{3}$/.test(p.group) || combination(p.group) !== p.group)) {
      throw Error("Invalid " + session + " forecast.");
    }
  }
  return dataset;
}

// The legacy textarea path works on browsers where the Clipboard API is unavailable.
async function copyText(value, clipboard = globalThis.navigator?.clipboard, doc = globalThis.document) {
  if (clipboard?.writeText) {
    try { await clipboard.writeText(value); return true; } catch (_) { /* Try the fallback. */ }
  }
  if (!doc?.body || typeof doc.execCommand !== "function") return false;
  const field = doc.createElement("textarea");
  const active = doc.activeElement;
  field.value = value;
  field.readOnly = true;
  field.style.position = "fixed";
  field.style.opacity = "0";
  field.style.left = "-9999px";
  doc.body.append(field);
  try {
    field.focus();
    field.select();
    field.setSelectionRange?.(0, value.length);
    return Boolean(doc.execCommand("copy"));
  } catch (_) {
    return false;
  } finally {
    field.remove();
    active?.focus?.();
  }
}

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
}

function feedback(message, success) {
  const host = $("copyFeedback");
  host.textContent = message;
  host.className = "copy-feedback " + (success ? "success" : "error");
  clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => { host.textContent = ""; }, 3000);
}

async function copyNumber(value) {
  const success = await copyText(value);
  feedback(success ? `Copied ${value}` : "Could not copy. Please select and copy the number.", success);
}

async function copyAll() {
  const value = allNumbersText(data.sessions[selectedSession || nextScheduled().session]);
  const success = await copyText(value);
  feedback(success ? "Copied all 10 numbers" : "Could not copy. Please select and copy the numbers.", success);
}

function pickCard(pick, index) {
  const card = el("div", "pick");
  card.append(el("span", "rank", String(index + 1).padStart(2, "0")),
    el("strong", "number", pick.group));
  const button = el("button", "copy-one", "Copy");
  button.type = "button";
  button.setAttribute("aria-label", `Copy ${pick.group}`);
  button.addEventListener("click", () => copyNumber(pick.group));
  card.append(button, el("span", "pick-detail", `Model estimate ${pct(pick.model_probability)}`));
  return card;
}

function renderTop(now = new Date()) {
  const next = nextScheduled(now);
  const session = selectedSession || next.session;
  const item = data.sessions[session];
  const state = freshness(item, now);
  $("sessionSelect").value = session;
  $("nextTitle").textContent = `${title(next.session)} · ${next.label} · ${next.time} Central`;
  $("nextMeta").textContent = "Drawing times shown in America/Chicago.";
  $("forecastTitle").textContent = `${title(session)} Top 10 · ${item.target_draw.slice(0, 10)}`;
  $("forecastMeta").textContent = `Published ${when(item.published_at)} · Latest official ${item.latest_result || "not recorded"} (${item.last_draw || "date unavailable"})`;
  $("freshness").textContent = state;
  $("freshness").className = `freshness ${state.toLowerCase().replaceAll(" ", "-")}`;
  $("topPicks").replaceChildren(...item.predictions.map(pickCard));
  $("copyAll").disabled = item.predictions.length !== 10;
}

function renderSessions(now = new Date()) {
  const next = nextScheduled(now);
  $("sessions").replaceChildren(...SESSIONS.map(session => {
    const item = data.sessions[session];
    const upcoming = session === next.session;
    const card = el("article", "session-card" + (upcoming ? " upcoming" : ""));
    const heading = el("div", "session-heading");
    heading.append(el("h3", null, title(session)));
    if (upcoming) heading.append(el("span", "next-tag", "Next drawing"));
    card.append(heading,
      el("p", "muted", `Forecast for ${item.target_draw.slice(0, 10)} · ${freshness(item, now)}`),
      el("p", "session-numbers", numbers(item).join(" · ")));
    const button = el("button", "text-button", `View ${title(session)} Top 10`);
    button.type = "button";
    button.addEventListener("click", () => {
      selectedSession = session;
      renderTop();
      document.querySelector(".featured")?.scrollIntoView({behavior: "smooth", block: "start"});
    });
    card.append(button);
    return card;
  }));
}

function renderHistory() {
  const rows = data.results.filter(row => row.draw_date === $("historyDate").value)
    .sort((a, b) => SESSIONS.indexOf(a.session) - SESSIONS.indexOf(b.session));
  if (!rows.length) {
    $("history").replaceChildren(el("p", "muted", "No verified official result for this date yet."));
    return;
  }
  $("history").replaceChildren(...rows.map(row => {
    const card = el("article", "history-card");
    const match = row.predictions?.findIndex(pick => pick.group === combination(row.actual)) ?? -1;
    card.append(el("h3", null, `${title(row.session)} · ${row.actual}`),
      el("p", match >= 0 ? "hit" : "muted",
        !row.predictions ? "No forecast was published before this draw" : match >= 0 ? `Matched prediction #${match + 1}` : "No Top 10 match"));
    if (row.predictions) {
      const list = el("ol", "history-picks");
      for (const pick of row.predictions) {
        const entry = el("li", pick.group === combination(row.actual) ? "matched" : "", pick.group);
        if (pick.model_probability != null) entry.append(el("small", null, `Model ${pct(pick.model_probability)}`));
        list.append(entry);
      }
      card.append(list);
    }
    card.append(el("p", "muted", `Published ${when(row.published_at)} · Verified ${when(row.verified_at)}`));
    return card;
  }));
}

function metricTable(report, label) {
  const group = el("div", "metric-group");
  group.append(el("h4", null, `${label} · ${report.draws || 0} scored draws`));
  const table = el("table", "metric-table");
  const header = el("tr");
  for (const text of ["Rank", "Observed hit rate", "Fair random"]) header.append(el("th", null, text));
  table.append(header);
  for (const k of [1, 5, 10]) {
    const row = el("tr");
    for (const text of [`Top ${k}`, pct(report[`top_${k}`]), pct(report[`fair_top_${k}`])]) row.append(el("td", null, text));
    table.append(row);
  }
  group.append(table);
  if (report.estimated_top_10 != null) group.append(el("p", "muted", `Average model Top 10 estimate: ${pct(report.estimated_top_10)}`));
  return group;
}

function renderMetrics() {
  $("metrics").replaceChildren(...SESSIONS.map(session => {
    const card = el("article", "metric-card");
    card.append(el("h3", null, title(session)),
      metricTable(data.backtest?.[session] || {}, "Historical walk-forward"),
      metricTable(data.forward?.[session] || {}, "Published forecasts"));
    return card;
  }));
  $("calibration").textContent = "Model estimates are exploratory and uncalibrated. Compare them with observed hit rates only where scored samples exist; small published samples can vary widely.";
}

function render() {
  const latest = [...data.results].sort((a, b) => (b.verified_at || "").localeCompare(a.verified_at || ""))[0];
  $("latestResult").textContent = latest ? `${title(latest.session)} ${latest.actual} · ${latest.draw_date}` : "None verified yet";
  $("generatedAt").textContent = when(data.generated_at);
  renderTop();
  renderSessions();
  renderHistory();
  renderMetrics();
  $("status").textContent = "Forecast data connected";
}

async function refresh() {
  try {
    const response = await fetch("data/predictions.json", {cache: "no-store"});
    if (!response.ok) throw Error(`Data request failed (${response.status}).`);
    const incoming = valid(await response.json());
    const previous = data?.generated_at;
    data = incoming;
    if (!$("historyDate").value) $("historyDate").value = data.results.map(row => row.draw_date).sort().at(-1) || nextScheduled().date;
    if (previous !== data.generated_at) render();
    else { renderTop(); renderSessions(); }
    $("status").textContent = "Forecast data connected";
  } catch (error) {
    $("status").textContent = error.message;
  }
}

if (typeof document !== "undefined") {
  $("historyDate").addEventListener("change", () => { if (data) renderHistory(); });
  $("sessionSelect").addEventListener("change", event => {
    selectedSession = event.target.value;
    if (data) renderTop();
  });
  $("copyAll").addEventListener("click", () => data && copyAll());
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 120000);
  setInterval(() => { if (data) { renderTop(); renderSessions(); } }, 60000);
}

if (typeof module !== "undefined") module.exports = {
  allNumbersText, combination, copyText, freshness, nextScheduled, numbers, valid
};
