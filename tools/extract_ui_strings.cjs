/* Extract translatable leaves while retaining source offsets and syntax. */
const acorn = require('acorn');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const results = [];
for (const file of process.argv.slice(2).length ? process.argv.slice(2) : ['botw_companion/web/app.js', 'botw_companion/web/route_planner.js']) {
  const source = fs.readFileSync(path.resolve(root, file), 'utf8');
  const ast = acorn.parse(source, {ecmaVersion: 'latest', sourceType: 'script'});
  function walk(node, parent) {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'Literal' && typeof node.value === 'string') {
      results.push({file, start: node.start, end: node.end, value: node.value,
        kind: 'literal', key: parent?.type === 'Property' && parent.key === node && !parent.computed});
    } else if (node.type === 'TemplateLiteral') {
      const quasis = node.quasis.map(q => q.value.cooked ?? q.value.raw);
      const template = quasis.map((q, i) => q + (i < quasis.length - 1 ? `ZXQ${i}QXZ` : '')).join('');
      node.quasis.forEach((q, i) => results.push({file, start: q.start, end: q.end,
        value: quasis[i], kind: 'template', template, quasi: i}));
    }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) for (const child of value) walk(child, node);
      else if (value && typeof value === 'object' && typeof value.type === 'string') walk(value, node);
    }
  }
  walk(ast);
}
process.stdout.write(JSON.stringify(results));
