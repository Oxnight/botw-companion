const vm = require('node:vm');
const {localize} = require('./i18n_context.js');
const entities = {'&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#x27;': "'", '&#39;': "'"};
const decode = value => value.replace(/&(?:amp|lt|gt|quot|#x27|#39);/g, entity => entities[entity]);

function concat(parts) {
  const result = [];
  for (const part of parts) {
    const values = Array.isArray(part?.concat) ? part.concat : [part];
    for (const value of values) {
      if (value === '') continue;
      if (typeof value === 'string' && typeof result.at(-1) === 'string') result[result.length - 1] += value;
      else result.push(value);
    }
  }
  return result.length === 1 ? result[0] : {concat: result};
}

function normalized(tree, locale) {
  // Compare expression ASTs and literal text after resolving message wrappers.
  // Browser tests cover rendering and escaping beyond this comparison.
  const context = localize(vm.createContext({}), locale);
  function normalize(node) {
    if (node == null) return node;
    if (Array.isArray(node)) return node.map(normalize);
    if (typeof node !== 'object') return node;
    if (node.type === 'Literal' && typeof node.value === 'string') return decode(node.value);
    if (node.type === 'TemplateLiteral') {
      return concat(node.quasis.flatMap((quasi, i) => [decode(quasi.value.cooked),
        ...(i < node.expressions.length ? [normalize(node.expressions[i])] : [])]));
    }
    // Published collation tags fr/en and fr-FR/en-US select the same
    // language rules; a private logical ID must use its manifest's tag.
    if (node.type === 'CallExpression' && ['localeCompare', 'toLocaleLowerCase'].includes(node.callee.property?.name)
        && node.arguments.some(arg => arg.type === 'MemberExpression' && arg.object.name === 'BOTWI18n' && arg.property.name === 'formatLocale')) {
      return normalize({...node, arguments: node.arguments.map(arg =>
        arg.type === 'MemberExpression' && arg.object.name === 'BOTWI18n' && arg.property.name === 'formatLocale'
          ? {type: 'Literal', value: locale} : arg)});
    }
    if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.callee.name === 'String') {
      return normalize(node.arguments[0]);
    }
    if (node.type === 'MemberExpression' && node.object.name === 'BOTWI18n') {
      if (node.property.name === 'formatLocale') return locale === 'fr' ? 'fr-FR' : 'en-US';
      if (node.property.name === 'locale') return locale;
    }
    if (node.type === 'CallExpression' && node.callee.type === 'MemberExpression'
        && node.callee.object.name === 'BOTWI18n' && node.callee.property.name === 't') {
      const key = node.arguments[0].value;
      const properties = node.arguments[1]?.properties || [];
      const values = {}, expressions = {};
      properties.forEach((property, i) => {
        values[property.key.name] = `PLACEHOLDER${i}END`;
        expressions[i] = normalize(property.value);
      });
      const text = decode(context.BOTWI18n.t(key, values));
      return concat(text.split(/(PLACEHOLDER\d+END)/g).map(value =>
        /^PLACEHOLDER\d+END$/.test(value) ? expressions[value.match(/\d+/)[0]] : value));
    }
    // Compare the stored locale identity separately from its formatting tag.
    if (node.type === 'VariableDeclarator' && node.id.name === 'language') return {languagePreference: 'registry'};
    const result = {};
    for (const [key, value] of Object.entries(node)) {
      if (!['start', 'end', 'raw'].includes(key)) result[key] = normalize(value);
    }
    return result;
  }
  return normalize(tree);
}
module.exports = {normalized};
