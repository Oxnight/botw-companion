const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const acorn = require('acorn');

const root = path.join(__dirname, '../botw_companion');
const source = fs.readFileSync(path.join(root, 'web/app.js'), 'utf8');
const tree = acorn.parse(source, {ecmaVersion: 'latest'});
const render = tree.body.find(node => node.type === 'FunctionDeclaration' && node.id.name === 'renderFilterNav');
const escape = tree.body.flatMap(node => node.declarations || []).find(node => node.id.name === 'esc');

function fixture(locale, count, message, formatLocale) {
  const output = {};
  const items = Array.from({length: count}, (_, id) => ({id, informational: true}));
  const context = vm.createContext({Intl, filtersInitialized: false, selectedTypes: new Set(),
    filterGroupsForDisplay: () => [{label: 'Group', types: [{id: 'info', label: 'Info'}]}],
    allItems: () => items, gameModeMatches: () => true, locationMatches: () => true,
    itemFilterTypes: () => ['info'], itemId: item => item.id, combinedDone: () => false,
    $: () => output, document: {querySelectorAll: () => []}});
  vm.runInContext(fs.readFileSync(path.join(root, 'locales', locale, 'browser.js'), 'utf8'), context);
  if (formatLocale) {
    context.BOTWLocaleData.locale.format_locale = formatLocale;
    context.BOTWLocaleData.registry.locales[locale].format_locale = formatLocale;
  }
  if (message) {
    context.BOTWLocaleData.messages = context.BOTWLocaleData.messages.replace(
      /^renderfilternav-point-count = .*$/m, message(context.BOTWLocaleData));
  }
  vm.runInContext(fs.readFileSync(path.join(root, 'web/i18n.js'), 'utf8'), context);
  assert.equal(context.BOTWI18n.failed, false);
  vm.runInContext('const esc = ' + source.slice(escape.init.start, escape.init.end), context);
  vm.runInContext(source.slice(render.start, render.end), context);
  context.renderFilterNav();
  return {context, html: output.innerHTML};
}

test('informational counts use the bundled locale and preserve filter identifiers', () => {
  for (const locale of ['fr', 'en']) for (const count of [1, 2, 1001]) {
    const {context, html} = fixture(locale, count);
    const formattedCount = count.toLocaleString(context.BOTWI18n.formatLocale);
    assert(html.includes(`>${formattedCount} pts</small>`));
    assert(html.includes('data-filter-type="info"'));
    assert.equal(context.BOTWI18n.t('renderfilternav-point-count', {formattedCount, count}),
      formattedCount + ' pts');
  }
});

test('translated count text cannot become HTML through the intermediate progress value', () => {
  for (const locale of ['fr', 'en']) {
    const {html} = fixture(locale, 1, data => {
      const parameter = data.contract['renderfilternav-point-count'].params.includes('formattedCount')
        ? 'formattedCount' : 'value0';
      return `renderfilternav-point-count = { $${parameter} } <b data-probe="literal">& 'pts'</b>`;
    });
    assert(!html.includes('<b data-probe='));
    assert(html.includes('1 &lt;b data-probe=&quot;literal&quot;&gt;&amp; &#39;pts&#39;&lt;/b&gt;'));
  }
});

test('point messages receive a numeric count for plural selection', () => {
  for (const [count, form] of [[0, 'many'], [1, 'one'], [2, 'few'], [4, 'few'], [5, 'many'],
    [11, 'many'], [14, 'many'], [21, 'one'], [22, 'few'], [25, 'many'], [101, 'one']]) {
    const {context, html} = fixture('en', count, () => `renderfilternav-point-count = { $count ->
    [one] { $formattedCount } one
    [few] { $formattedCount } few
    [many] { $formattedCount } many
   *[other] { $formattedCount } other
    }`, 'ru-RU');
    const formattedCount = count.toLocaleString('ru-RU');
    assert.equal(context.BOTWI18n.t('renderfilternav-point-count', {formattedCount, count}),
      `${formattedCount} ${form}`);
    if (count) assert(html.includes(`>${formattedCount} ${form}</small>`));
    else assert(!html.includes('class="filterType '));
  }
});

test('informational counts retain Latin digits for non-Latin numbering locales', () => {
  const {html} = fixture('en', 1001, undefined, 'ar-EG');
  assert(html.includes('>1,001 pts</small>'));
  assert.doesNotMatch(html, /[\u0660-\u0669\u06f0-\u06f9]/);
});
