"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const acorn = require('acorn');
const source = fs.readFileSync(path.join(__dirname, '../botw_companion/web/app.js'), 'utf8');
const tree = acorn.parse(source, {ecmaVersion: 'latest'});
function context(locale) {
  const result = vm.createContext({Intl, BOTWI18n: {formatLocale: locale}});
  for (const name of ['formatUnit', 'bloodMoonDuration', 'formatDistance']) {
    const node = tree.body.find(node => node.type === 'FunctionDeclaration' && node.id.name === name);
    assert(node, `Missing formatter: ${name}`);
    vm.runInContext(source.slice(node.start, node.end), result);
  }
  return result;
}
test('duration and route distances use the selected language', () => {
  for (const locale of ['fr-FR', 'en-US', 'ru-RU', 'ar-EG']) {
    const c = context(locale);
    const unit = (value, unit, options = {}) => new Intl.NumberFormat(locale,
      {style: 'unit', unit, unitDisplay: 'short', numberingSystem: 'latn', ...options}).format(value);
    assert.equal(c.bloodMoonDuration(3660), `${unit(1, 'hour')} ${unit(1, 'minute')}`);
    assert.equal(c.bloodMoonDuration(3600), unit(1, 'hour'));
    assert.equal(c.bloodMoonDuration(30), unit(1, 'minute'));
    assert.equal(c.formatDistance(23.7), unit(24, 'meter'));
    assert.equal(c.formatDistance(1234), unit(1.234, 'kilometer',
      {minimumFractionDigits: 2, maximumFractionDigits: 2}));
    assert.equal(c.formatDistance(12000), unit(12, 'kilometer',
      {minimumFractionDigits: 1, maximumFractionDigits: 1}));
  }
});

test('duration rounding carries into the next hour and rejects unavailable values', () => {
  const c = context('en-US');
  for (const seconds of [null, undefined, NaN, Infinity, -Infinity, 'invalid']) {
    assert.equal(c.bloodMoonDuration(seconds), '-', String(seconds));
  }
  for (const seconds of [-1, 0, 0.5, 60]) assert.equal(c.bloodMoonDuration(seconds), '1 min');
  assert.equal(c.bloodMoonDuration(61), '2 min');
  assert.equal(c.bloodMoonDuration(3599), '1 hr');
  assert.equal(c.bloodMoonDuration(3601), '1 hr 1 min');
  assert.equal(c.bloodMoonDuration(7199), '2 hr');
  assert.equal(c.bloodMoonDuration('7200'), '2 hr');
});

test('distance boundaries preserve the meter/kilometer threshold and precision', () => {
  const c = context('en-US');
  for (const [meters, expected] of [[0, '0 m'], [999.4, '999 m'], [999.7, '1,000 m'],
    [1000, '1.00 km'], [1234, '1.23 km'], [9999, '10.00 km'], [10000, '10.0 km']]) {
    assert.equal(c.formatDistance(meters), expected, String(meters));
  }
  assert.equal(context('fr-FR').formatDistance(1234).replace(/\s/gu, ' '), '1,23 km');
  assert.equal(context('ru-RU').formatDistance(1234).replace(/\s/gu, ' '), '1,23 км');
});

test('unit formatting retains Latin digits for locales using other numbering systems', () => {
  const c = context('ar-EG');
  for (const output of [c.formatDistance(1234), c.bloodMoonDuration(3660)]) {
    assert.match(output, /[0-9]/);
    assert.doesNotMatch(output, /[\u0660-\u0669\u06f0-\u06f9\u061c\u200e\u200f]/);
  }
});
