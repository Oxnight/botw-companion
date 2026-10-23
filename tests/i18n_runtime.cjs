const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const acorn = require('acorn');
const {localize} = require('./i18n_context.js');
const runtime = fs.readFileSync('botw_companion/web/i18n.js', 'utf8');
const language = fs.readFileSync('botw_companion/web/language.js', 'utf8');
const session = fs.readFileSync('botw_companion/web/browser_session.js', 'utf8');

for (const damaged of [undefined, {locale: {id: 'fr', format_locale: 'fr'}, registry: {locales: {fr: {}}}, contract: {missing: {params: []}}, messages: 'broken = {'}]) {
  test(`${damaged ? 'malformed' : 'missing'} catalog: bounded localized emergency UI and no storage/session actions`, () => {
    let ready, rendered, replacements = 0;
    const document = {querySelector: () => ({content: 'Synthetic emergency 日本語'}),
      addEventListener(type, callback) {assert.equal(type, 'DOMContentLoaded'); ready = callback;},
      createElement: tag => ({tag, append(value) {this.child = value;}}),
      body: {replaceChildren(node) {rendered = node; replacements++;}}};
    const context = vm.createContext({document, BOTWLocaleData: damaged});
    vm.runInContext(runtime, context);
    assert.equal(context.BOTWI18n.failed, true);
    assert.throws(() => context.BOTWI18n.t('anything'), /Synthetic emergency/);
    vm.runInContext(language, context);
    vm.runInContext(session, context);
    ready();
    assert.equal(replacements, 1);
    assert.equal(rendered.child.child.textContent, 'Synthetic emergency 日本語');
  });
}

test('catalog scripts contain only JSON assignment and runtime requires no eval or network', () => {
  for (const locale of ['fr', 'en']) {
    const data = acorn.parse(fs.readFileSync(`botw_companion/locales/${locale}/browser.js`, 'utf8'), {ecmaVersion: 'latest'});
    assert.equal(data.body.length, 1);
    assert.equal(data.body[0].expression.type, 'AssignmentExpression');
    function constant(node) {
      assert(['ObjectExpression', 'ArrayExpression', 'Property', 'Literal', 'Identifier'].includes(node.type));
      for (const value of Object.values(node)) for (const child of Array.isArray(value) ? value : [value]) if (child?.type) constant(child);
    }
    constant(data.body[0].expression.right);
    const context = vm.createContext({fetch() {assert.fail('No network during locale initialization');}});
    localize(context, locale);
    assert.equal(context.BOTWI18n.failed, false);
    assert.equal(context.BOTWI18n.locale, locale);
  }
  function inspect(node) {
    assert(!(node.type === 'CallExpression' && ['eval', 'fetch', 'importScripts'].includes(node.callee.name)));
    assert(!(node.type === 'NewExpression' && node.callee.name === 'Function'));
    for (const value of Object.values(node)) for (const child of Array.isArray(value) ? value : [value]) if (child?.type) inspect(child);
  }
  inspect(acorn.parse(runtime, {ecmaVersion: 'latest'}));
});

test('browser selection keeps URL, cookie, storage and document precedence with broken storage', () => {
  for (const [query, cookie, saved, expected, broken] of [
    ['en', 'fr', 'fr', 'en'], ['invalid', 'en', 'fr', 'en'],
    [null, 'invalid', 'en', 'en'], [null, null, null, 'fr'],
    ['../../en', 'en', null, 'en', true], [null, null, 'en', 'fr', true]]) {
    const replacements = [], writes = [];
    const href = 'http://127.0.0.1:18765/' + (query ? '?lang=' + encodeURIComponent(query) : '');
    const document = {documentElement: {lang: 'fr', dataset: {}}, cookie: cookie ? 'botw-language=' + cookie : '', addEventListener() {}};
    const window = {location: {href, replace(value) {replacements.push(value);}}};
    const context = vm.createContext({URL, window, document, localStorage: {
      getItem() {if (broken) throw Error('Disabled'); return saved;},
      setItem(key, value) {if (broken) throw Error('Disabled'); writes.push([key, value]);}
    }});
    localize(context, 'fr');
    vm.runInContext(language, context);
    assert(document.cookie.startsWith('botw-language=' + expected + ';'));
    assert.equal(replacements.length, expected === 'fr' ? 0 : 1);
    if (!broken) assert.equal(writes[0][1], expected);
  }
});

for (const [locale, expected] of [['fr', 'Cet onglet BOTW Companion n’est plus actif'], ['en', 'This BOTW Companion tab is inactive']]) {
  test(`${locale}: retired-tab explanation uses resources available before report loading`, () => {
    let rendered, replacements = 0;
    const document = {createElement: tag => ({tag, append(...values) {this.children = values;}}),
      body: {replaceChildren(node) {rendered = node; replacements++;}}};
    const context = vm.createContext({document, window: {close() {throw Error('Cannot close');}},
      stopped: false, leaving: false, timer: null, stop() {}, clearTimeout() {}});
    localize(context, locale);
    vm.runInContext(session.slice(session.indexOf('    function retire()'), session.indexOf('    function begin(')), context);
    vm.runInContext('retire(); retire();', context);
    assert.equal(replacements, 1);
    assert.equal(rendered.children[0].children[0].textContent, expected);
  });
}

test('application collation uses formatting tags and preserves published FR/EN ordering', () => {
  const source = acorn.parse(fs.readFileSync('botw_companion/web/app.js', 'utf8'), {ecmaVersion: 'latest'});
  let checked = 0;
  function inspect(node) {
    if (node.type === 'CallExpression' && ['localeCompare', 'toLocaleLowerCase'].includes(node.callee.property?.name)) {
      for (const argument of node.arguments) if (argument.type === 'MemberExpression' && argument.object.name === 'BOTWI18n') {
        assert.equal(argument.property.name, 'formatLocale'); checked++;
      }
    }
    for (const value of Object.values(node)) for (const child of Array.isArray(value) ? value : [value]) if (child?.type) inspect(child);
  }
  inspect(source); assert(checked >= 5);
  for (const [locale, formatting] of [['fr', 'fr-FR'], ['en', 'en-US']]) {
    const data = JSON.parse(fs.readFileSync(`botw_companion/locales/${locale}/presentation-data.json`, 'utf8'));
    const names = Object.values(data.names_by_id);
    assert.deepEqual([...names].sort((a, b) => a.localeCompare(b, formatting)),
      [...names].sort((a, b) => a.localeCompare(b, locale)));
    assert.deepEqual(names.map(name => name.toLocaleLowerCase(formatting)), names.map(name => name.toLocaleLowerCase(locale)));
  }
});
