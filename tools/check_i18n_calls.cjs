const fs = require('node:fs');
const acorn = require('acorn');
const contract = JSON.parse(fs.readFileSync('botw_companion/i18n/contract.json', 'utf8'));
const used = new Set();
const rich = new Set();
for (const file of ['app.js', 'route_planner.js', 'browser_session.js', 'language.js']) {
  const tree = acorn.parse(fs.readFileSync('botw_companion/web/' + file, 'utf8'), {ecmaVersion: 'latest'});
  function walk(node, html = false) {
    if (!node?.type) return;
    // Treat messages inside esc() as text, even within an HTML template.
    if (node.type === 'CallExpression' && node.callee.name === 'esc') html = false;
    if (node.type === 'AssignmentExpression' && node.left.property?.name === 'innerHTML') html = true;
    if (node.type === 'TemplateLiteral' && node.quasis.some(q => /<\/?[a-z]/i.test(q.value.cooked))) html = true;
    if (node.type === 'CallExpression' && node.callee.object?.name === 'BOTWI18n' && node.callee.property.name === 't') {
      const key = node.arguments[0]?.value;
      const entry = contract[key];
      if (!entry) throw new Error(`${file}: unknown message ${key}`);
      const supplied = (node.arguments[1]?.properties || []).map(p => p.key.name).sort();
      if (JSON.stringify(supplied) !== JSON.stringify([...entry.params].sort())) throw new Error(`${file}: invalid parameters for ${key}`);
      used.add(key);
      if (html) rich.add(key);
      html ||= entry.rich;
    }
    for (const value of Object.values(node)) for (const child of Array.isArray(value) ? value : [value]) if (child?.type) walk(child, html);
  }
  walk(tree);
}
const missing = [...rich].filter(key => !contract[key].rich);
if (process.argv.includes('--inventory')) process.stdout.write(JSON.stringify({used: [...used], rich: [...rich], missing}));
else {
  if (missing.length) throw new Error('Unescaped messages in HTML: ' + missing.join(', '));
  console.log(`Message calls checked: ${used.size}; source-owned HTML: ${rich.size}`);
}
