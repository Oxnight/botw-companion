const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function localize(context, locale = 'fr') {
  const packageRoot = path.join(__dirname, '../botw_companion');
  vm.runInContext(fs.readFileSync(path.join(packageRoot, 'locales', locale, 'browser.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(packageRoot, 'web/i18n.js'), 'utf8'), context);
  return context;
}
module.exports = {localize};
