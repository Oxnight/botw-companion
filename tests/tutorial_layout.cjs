"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../botw_companion/web/app.js"), "utf8");
const layoutSource = source.slice(source.indexOf("function setTutorialRectangle("),
  source.indexOf("function renderTutorialStep("));
const transitionSource = source.slice(source.indexOf("async function changeTutorialStep("),
  source.indexOf("function openTutorial("));

function layout(width, height, raw, cardHeight = 480) {
  const node = () => ({style: {}, dataset: {}, hidden: false,
    classList: {add() {}, remove() {}}});
  const card = node(), preview = node(), spotlight = node(), masks = Array.from({length: 4}, node);
  const target = {offsetWidth: raw.width, offsetHeight: raw.height, getBoundingClientRect: () => raw};
  Object.defineProperties(card, {
    offsetWidth: {get: () => Math.min(440, width - 24)},
    offsetHeight: {get: () => Math.min(cardHeight,
      Number.parseFloat(card.style.maxHeight) || height - 24)}
  });
  preview.dataset.sourceSize = `${raw.width}:${raw.height}`;
  preview.shadowRoot = {lastElementChild: {style: {}}};
  const nodes = {"#tutorialCard": card, "#tutorialPreview": preview,
    "#tutorialSpotlight": spotlight, "#tutorialLayer": {querySelectorAll: () => masks}};
  const context = vm.createContext({$: id => nodes[id],
    tutorialState: {index: 0}, currentTutorialStep: () => ({target: ".hero"}),
    visibleTutorialTarget: () => target, window: {innerWidth: width, innerHeight: height}});
  vm.runInContext(layoutSource, context);
  vm.runInContext("positionTutorial()", context);
  const rect = element => {
    const left = Number.parseFloat(element.style.left), top = Number.parseFloat(element.style.top);
    const w = element === card ? card.offsetWidth : Number.parseFloat(element.style.width);
    const h = element === card ? card.offsetHeight : Number.parseFloat(element.style.height);
    return {left, top, right: left + w, bottom: top + h, width: w, height: h};
  };
  return {card: rect(card), frame: rect(spotlight), mode: card.dataset.layout,
    scale: Number(preview.dataset.scale), preview};
}

test("complete targets and separate cards across viewport and target sizes", () => {
  let count = 0;
  for (const [width, height] of [[240, 240], [320, 568], [390, 844], [640, 360],
    [844, 390], [900, 600], [1280, 720], [2048, 1000]]) {
    for (const targetWidth of [150, width - 40, width, width * 1.5]) {
      for (const targetHeight of [48, 240, height, height * 2]) {
        for (const top of [-50, 20, height / 2]) {
          const raw = {left: 20, top, right: 20 + targetWidth, bottom: top + targetHeight,
            width: targetWidth, height: targetHeight};
          const {card, frame, mode, scale} = layout(width, height, raw);
          const description = JSON.stringify({width, height, raw, card, frame, mode});
          for (const rect of [card, frame]) {
            assert(rect.left >= 0 && rect.top >= 0 && rect.right <= width + .01
              && rect.bottom <= height + .01, description);
          }
          const overlap = Math.max(0, Math.min(card.right, frame.right) - Math.max(card.left, frame.left))
            * Math.max(0, Math.min(card.bottom, frame.bottom) - Math.max(card.top, frame.top));
          assert(overlap <= .01, description);
          if (mode === "overview") {
            assert(scale > 0 && scale <= 1, description);
            assert(Math.abs(frame.width - raw.width * scale - 18) < .01, description);
            assert(Math.abs(frame.height - raw.height * scale - 18) < .01, description);
          } else {
            assert(frame.left <= raw.left && frame.top <= raw.top
              && frame.right >= raw.right && frame.bottom >= raw.bottom, description);
          }
          count++;
        }
      }
    }
  }
  assert.equal(count, 384);
});

test("use the actual target when the viewport has enough room", () => {
  const result = layout(1280, 900,
    {left: 50, top: 200, right: 250, bottom: 350, width: 200, height: 150}, 350);
  assert.equal(result.mode, "direct");
  assert.equal(result.preview.hidden, true);
});

function transition(reducedMotion = false) {
  const animations = [], session = {index: 0}, card = {dataset: {},
    setAttribute() {}, removeAttribute() {}}, spotlight = {};
  for (const element of [card, spotlight]) {
    element.animate = () => {
      let finish;
      const finished = new Promise(resolve => { finish = resolve; });
      const animation = {finished, cancel: finish, finish};
      animations.push(animation);
      return animation;
    };
  }
  const rendered = [];
  const context = vm.createContext({tutorialState: session, tutorialTransition: null,
    $: id => id === "#tutorialCard" ? card : id === "#tutorialSpotlight" ? spotlight : {focus() {}},
    window: {matchMedia: () => ({matches: reducedMotion})},
    renderTutorialStep: () => rendered.push(session.index), positionTutorial() {},
    requestAnimationFrame: callback => callback()});
  vm.runInContext(transitionSource, context);
  return {context, card, animations, session, rendered};
}

test("a double click cannot skip a step during the fade", async () => {
  const state = transition();
  const first = vm.runInContext("changeTutorialStep(1)", state.context);
  await vm.runInContext("changeTutorialStep(2)", state.context);
  assert.equal(state.session.index, 0);
  assert.equal(state.card.dataset.transitioning, "true");
  state.animations.slice(0, 2).forEach(animation => animation.finish());
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(state.rendered, [1]);
  state.animations.slice(2).forEach(animation => animation.finish());
  await first;
  assert.equal(state.session.index, 1);
  assert.equal(state.card.dataset.transitioning, undefined);
});

test("reduced motion changes the step immediately without animations", async () => {
  const state = transition(true);
  await vm.runInContext("changeTutorialStep(1)", state.context);
  assert.equal(state.session.index, 1);
  assert.equal(state.animations.length, 0);
  assert.deepEqual(state.rendered, [1]);
});

test("closing during a fade cannot render a stale step", async () => {
  const state = transition();
  const pending = vm.runInContext("changeTutorialStep(1)", state.context);
  vm.runInContext("tutorialState = null; tutorialTransition = null", state.context);
  state.animations.forEach(animation => animation.cancel());
  await pending;
  assert.deepEqual(state.rendered, []);
});
