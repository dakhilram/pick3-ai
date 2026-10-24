"use strict";

const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const published = require("../web/data/predictions.json");
const {allNumbersText, combination, copyText, freshness, nextScheduled, numbers, valid} = require("../web/app.js");

test("the dashboard keeps the published rank and canonical three-digit strings", () => {
  valid(published);
  for (const item of Object.values(published.sessions)) {
    assert.deepEqual(numbers(item), item.predictions.map(pick => pick.group));
    assert.equal(numbers(item).length, 10);
  }
  assert.equal(combination("907"), "079");
  assert.equal(combination("700"), "007");
  assert.deepEqual(numbers({predictions: [{group: "007", representative: "700"}]}), ["007"]);
});

test("single and all copy contain only numbers and retain leading zeros", async () => {
  const item = {predictions: ["007", "049", "123", "456", "018", "222", "345", "567", "789", "009"]
    .map(group => ({group}))};
  const written = [];
  const clipboard = {writeText: async value => written.push(value)};
  assert.equal(allNumbersText(item), "007, 049, 123, 456, 018, 222, 345, 567, 789, 009");
  assert.equal(await copyText(item.predictions[0].group, clipboard), true);
  assert.equal(await copyText(allNumbersText(item), clipboard), true);
  assert.deepEqual(written, ["007", "007, 049, 123, 456, 018, 222, 345, 567, 789, 009"]);
});

test("clipboard fallback supports mobile-style selection and reports failure", async () => {
  let copied = null;
  let removed = false;
  let restored = false;
  const field = {
    style: {}, focus() {}, select() {}, setSelectionRange(start, end) {
      assert.equal(start, 0);
      assert.equal(end, 3);
    }, remove() { removed = true; }
  };
  const doc = {
    body: {append(node) { assert.equal(node, field); }},
    activeElement: {focus() { restored = true; }},
    createElement(tag) { assert.equal(tag, "textarea"); return field; },
    execCommand(command) { assert.equal(command, "copy"); copied = field.value; return true; }
  };
  assert.equal(await copyText("049", {writeText: async () => { throw Error("denied"); }}, doc), true);
  assert.equal(copied, "049");
  assert.equal(removed, true);
  assert.equal(restored, true);
  assert.equal(await copyText("007", null, {
    body: {append() {}}, createElement: () => field, execCommand: () => false
  }), false);
});

test("freshness follows the actual target timestamp and official draw state", () => {
  const item = {target_draw: "2026-10-23T10:00:00-05:00", last_draw: "2026-10-22"};
  assert.equal(freshness(item, new Date("2026-10-23T14:59:59Z")), "Current");
  assert.equal(freshness(item, new Date("2026-10-23T15:06:00Z")), "Awaiting Official Result");
  assert.equal(freshness(item, new Date("2026-10-23T17:01:00Z")), "Update Delayed");
  assert.equal(freshness({...item, last_draw: "2026-10-23"}, new Date("2026-10-23T15:06:00Z")), "Update Delayed");
  assert.equal(freshness({target_draw: null}, new Date()), "Update Delayed");
});

test("next scheduled session handles Sundays and both DST offsets", () => {
  assert.deepEqual(nextScheduled(new Date("2026-07-18T23:30:00Z")).session, "night");
  assert.deepEqual(nextScheduled(new Date("2026-10-25T16:00:00Z")), {
    session: "morning", date: "2026-10-26", label: "Monday, October 26", time: "10:00 AM"
  });
  assert.equal(nextScheduled(new Date("2026-11-01T16:00:00Z")).date, "2026-11-02");
});

test("rendered picks, session selection, history, and copy buttons use published groups", async () => {
  const ids = {};
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.value = ""; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    addEventListener(name, callback) { this.events[name] = callback; }
    setAttribute() {}
  }
  const doc = {
    getElementById(id) { return ids[id] ||= new Element(id); },
    createElement(tag) { return new Element(tag); },
    querySelector() { return {scrollIntoView() {}}; },
    hidden: false
  };
  const dataset = structuredClone(published);
  dataset.sessions.day.predictions = ["007", "049", "123", "456", "018", "222", "345", "567", "789", "009"]
    .map((group, index) => ({group, representative: [...group].reverse().join(""), model_probability: .01 - index * .0001}));
  dataset.results = [{session: "day", draw_date: "2026-10-23", actual: "700",
    verified_at: "2026-10-23T22:00:00Z", published_at: "2026-10-23T14:00:00Z",
    predictions: dataset.sessions.day.predictions}];
  const written = [];
  const FixedDate = class extends Date {
    constructor(...args) { super(...(args.length ? args : ["2026-10-23T16:00:00Z"])); }
  };
  const context = {
    document: doc, navigator: {clipboard: {writeText: async value => written.push(value)}},
    fetch: async () => ({ok: true, json: async () => dataset}),
    Date: FixedDate, Intl, setInterval() {}, setTimeout() {}, clearTimeout() {}, console
  };
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(require.resolve("../web/app.js"), "utf8"), context);
  await new Promise(setImmediate);
  assert.equal(ids.topPicks.children.length, 10);
  assert.equal(ids.topPicks.children[0].children[1].textContent, "007");
  assert.equal(ids.sessions.children.length, 4);
  assert.match(ids.nextTitle.textContent, /^Day ·/);
  assert.match(ids.latestResult.textContent, /Day 700/);
  assert.equal(ids.history.children.at(-1).children[1].textContent, "Matched prediction #1");
  await ids.topPicks.children[0].children[2].events.click();
  await ids.copyAll.events.click();
  assert.deepEqual(written, ["007", dataset.sessions.day.predictions.map(pick => pick.group).join(", ")]);
  assert.equal(ids.copyFeedback.textContent, "Copied all 10 numbers");
  context.navigator.clipboard.writeText = async () => { throw Error("clipboard unavailable"); };
  await ids.copyAll.events.click();
  assert.match(ids.copyFeedback.textContent, /Could not copy/);
  ids.sessionSelect.value = "morning";
  ids.sessionSelect.events.change({target: ids.sessionSelect});
  assert.equal(ids.topPicks.children[0].children[1].textContent, dataset.sessions.morning.predictions[0].group);
  ids.historyDate.value = "2030-01-01";
  ids.historyDate.events.change();
  assert.match(ids.history.children[0].textContent, /No verified official result/);
});
