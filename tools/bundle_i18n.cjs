const esbuild = require('esbuild');
const result = esbuild.buildSync({entryPoints: ['tools/i18n_browser.js'], bundle: true,
  minify: true, legalComments: 'inline', write: false, format: 'iife', target: 'es2020'});
process.stdout.write('/* Generated from tools/i18n_browser.js with esbuild 0.25.12. */\n');
process.stdout.write(result.outputFiles[0].text);
