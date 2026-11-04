/* Baseline: 8009763. Unit formatting and escaped filter counts have dedicated
 * behavior tests in localized_units.cjs and filter_localization.cjs.
 * All other symbolic hashes remain unchanged. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const acorn = require('acorn');
const {normalized} = require('./i18n_symbolic.js');
const expected = require('./fixtures/ui_compatibility.json');
for (const locale of ['fr', 'en']) for (const name of ['app', 'route_planner']) {
  test(`${locale}/${name}: all baseline logic and symbolic presentation remain equivalent`, () => {
    const source = fs.readFileSync(path.join(__dirname, '../botw_companion/web', name + '.js'), 'utf8');
    // The added unit formatter has dedicated behavior tests; the baseline still
    // covers every pre-existing top-level declaration.
    const actual = normalized(acorn.parse(source, {ecmaVersion: 'latest'}), locale, true).body
      .filter(node => !(name === 'app' && node.type === 'FunctionDeclaration' && node.id.name === 'formatUnit'));
    const reference = expected[`${locale}/${name}`];
    assert.equal(actual.length, reference.length);
    actual.forEach((node, i) => assert.equal(crypto.createHash('sha256').update(JSON.stringify(node)).digest('hex'),
      reference[i].sha256, `${locale}/${name}: ${reference[i].name}`));
  });
}
