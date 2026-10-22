/* Expected hashes were captured from unchanged commit 8009763 before edits. */
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
    const actual = normalized(acorn.parse(source, {ecmaVersion: 'latest'}), locale, true).body;
    const reference = expected[`${locale}/${name}`];
    assert.equal(actual.length, reference.length);
    actual.forEach((node, i) => assert.equal(crypto.createHash('sha256').update(JSON.stringify(node)).digest('hex'),
      reference[i].sha256, `${locale}/${name}: ${reference[i].name}`));
  });
}
