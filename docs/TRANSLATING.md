# Translating BOTW Companion

BOTW Companion includes French and English. Each language requires human review
of wording and official game terminology as well as automated validation.
Contributions follow the terms in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Source files and generated resources

Work in `botw_companion/locales/<id>/`. Translate values while preserving message
IDs, JSON keys and game identifiers.

| Source file | What to edit |
| --- | --- |
| `locale.json` | Language identity, native name, formatting tag, direction, aliases, fallback metadata and enabled state |
| `messages.ftl` | Fluent messages for interface text, attributes, help, tutorial, updates, diagnostics and launcher dialogs |
| `prose.json` | Report prose values; the French source-text keys remain unchanged |
| `game.json` | Official names and shrine trial titles, keyed by stable game identity |

The glossary and expanded report cache are generated from these inputs. Do not
supply a separate cache or add `legacy-cache.json` to a locale folder.

The following are generated product resources. Include their updated versions
with a translation change, but never edit them by hand:

- Each enabled locale's `presentation-data.json`, `contract.json`, `browser.ftl`,
  `backend.ftl`, `index.html` and `browser.js`.
- `botw_companion/locales/registry.json` and `botw_companion/web/i18n.js`.

The shared `botw_companion/i18n/*.json` files define message contracts, source
inventories and bindings maintained by developers. They are not translation
worksheets. `i18n/settings.json` declares the default and canonical source locale;
changing a language must not rewrite canonical game data. The HTML template and
application code are shared by all locales. Adding a locale requires no
language-specific Python/JavaScript module, packaging list or workflow change.
Installed applications load the generated registry and bundled resources offline;
they do not load translations from query-string paths or player data directories.

## Create and configure a locale

Discuss the scope in a translation issue and prepare a focused branch targeting
`master`. Follow [DEVELOPMENT.md](DEVELOPMENT.md) to create and activate a Python
environment. Python 3.12 is recommended. Install the pinned dependencies:

```bash
python -m pip install -r requirements-runtime.txt
npm ci --ignore-scripts
```

Create a draft, substituting the intended language, native name and formatting tag:

```bash
python tools/i18n.py scaffold pt-br --name "Português (Brasil)" --format-locale pt-BR
python tools/i18n.py coverage
```

The scaffold creates incomplete inputs with `enabled: false`. Fill every required
message and every prose/game section, using the French and English inputs for
context. Do not use untranslated copies or automatic fallback to claim completion.

A manifest has this form:

```json
{
  "schema": 1,
  "id": "pt-br",
  "native_name": "Português (Brasil)",
  "format_locale": "pt-BR",
  "direction": "ltr",
  "aliases": [],
  "fallback": null,
  "enabled": false
}
```

Choose a stable lower-case ID that preserves script and regional distinctions,
such as `sr-latn` or `pt-br`, and use it as the folder name. The logical ID is
independent of `format_locale`, which must be a supported Babel/browser Intl tag.
Do not collapse distinct script or regional variants. Existing `fr` and `en`
preferences remain valid. Aliases are case-insensitive exact matches; ambiguous
aliases, unknown manifest fields and fallback cycles are rejected.

`native_name` labels the language in the selector. An optional `display_names`
object maps interface locale IDs to alternative labels for this language.
Selection follows explicit or saved preferences; the OS/browser language is not
automatically selected. Fallback metadata describes relationships and does not
supply missing release content or count toward translated coverage.

Use `direction: "rtl"` where appropriate. Formatting language and text direction
are separate settings. Generated RTL documents isolate the map, coordinates and
numeric inputs as LTR; text direction must never mirror game space, controller
axes or gestures. Review fonts, mixed-direction text and layout in real browsers
and native packages; the manifest alone cannot establish visual compatibility.

Keep drafts disabled until all required content is supplied and reviewed. A
complete locale can be enabled for validation and review; enabling incomplete
input fails generation. Disabled locales are absent from the installed selector.

## Parameters, plurals and whitespace

Keep message IDs stable when editing wording. The shared contract is
`botw_companion/i18n/contract.json`. Preserve parameter names and required values;
inspect the corresponding `BOTWI18n.t` or Python message call for context.
Parameters such as `value0` contain formatted text; typed parameters such as
`count` or `number0` support numeric selection. Keep coordinates and protocol
values in their supplied display slots.

Translate complete phrases rather than joining independently translated
fragments. A translation-only contribution implements existing message IDs.
Adding a new application message also requires a developer to add its source
call and common contract entry. Use descriptive parameter names for such messages.

For example, the existing `renderitems-result` message provides a numeric `count`
and a formatted `value0`. A locale can select the whole phrase without using
its suffix parameter:

```ftl
renderitems-result = { $count ->
    [one] { $value0 } result
   *[other] { $value0 } results
    }
```

Supply the plural categories the language needs, including `zero`, `two`, `few`
or `many` where applicable. Do not derive another language's plurals from a
French/English suffix slot. Count messages with suffix parameters document their
numeric inputs in `raw_counts` contract metadata. Explicit numeric variants can
express a form that differs from CLDR. Check 0, 1, 2, 4, 5, 11, 14, 21, 22, 25,
101, negative and fractional values.

The supported Fluent contract includes strings, finite numbers, select/plural
branches and `NUMBER` with grouping and digit precision options. Options are
integer literals: `useGrouping` is 0 or 1, integer/significant digits are 1–21,
and fraction digits are 0–20. Minimum bounds must not exceed maximum bounds.
Message/term references, attributes, arbitrary functions and `DATETIME` are
rejected. Dates are formatted by source code and passed as complete values.

Numeric output uses Latin digits, locale-specific separators and no incidental
bidi marks. String parameters retain their bidi characters. Automatic Fluent
isolation is disabled; source-owned contexts provide isolation where needed.
Do not add invisible marks to translations to alter a path or controller value.
Babel and browser Intl can use different CLDR versions, so changes to formatting
dependencies require cross-runtime validation.

Save source files as UTF-8 with LF line endings. Preserve significant spaces and
line breaks. Use Fluent string literals when exact leading/trailing whitespace
or line breaks are required; do not trim such text automatically. Ordinary
Fluent text is preferred otherwise. Never translate paths, URLs, tokens, hashes,
API field names, technical category identifiers, flags, stable IDs, CLI command names,
personal notes or player-authored route names. Translate user-facing category labels
through the locale resources. External OS/library and device diagnostics remain
verbatim inside localized explanations. CLI commands remain French, and native
installer language follows its own configuration.

## Markup and official terminology

Plain messages are inserted through text/attribute APIs. Rich messages escape
translator-owned literals; only markup slots supplied by application code can
produce tags. Keep those slots in their declared order. They retain DOM IDs,
classes, actions, URLs, checked states and dynamic-value escaping. Do not add
HTML, scripts, CSS, handlers or CDN resources to translations. Review quotes,
braces, percent signs, multiline text, non-BMP characters and `</script>` as text.
Suggested export filenames must end in `.json` and contain no path separators
or control characters.

Preserve every key in `game.json`, including distinct equipment variants and
shrine trial titles. Resolve names against official localized game/publisher
references and document those sources in the PR. See
[DATA_SOURCES.md](../DATA_SOURCES.md) for the source and rights register. Do not
guess Nintendo names, request a ROM, distribute game binaries or submit personal
saves. Identical terms across languages can be correct; tests cannot certify
natural wording or permission to redistribute a source.

## Generate, validate and submit

From the repository root, run:

```bash
python tools/i18n.py build
python tools/i18n.py check
python tools/i18n.py coverage
python tools/audit_localization.py
python tools/audit_distribution.py
python tools/check_version_consistency.py
python -m unittest discover -s tests -v
node --test tests/*.cjs
```

Build a second time and confirm that it changes no bytes. Check mode compares
generated bytes and rejects stale files without rewriting them. Review coverage
for each locale; fallback is not translated coverage. The compatibility command
`python tools/build_english_assets.py --check` delegates to the shared checker.
An ordinary locale addition requires no new dependency.

For wheel validation, build a wheel with the normal Python backend and prepare a
wheelhouse containing the pinned runtime requirements. Then run:

```bash
python tools/verify_locale_wheel.py /path/to/botw_companion.whl --wheelhouse /path/to/wheelhouse
```

This installs into a disposable environment and checks every enabled locale
outside the checkout. It does not replace an installed player application.

Run the full [browser tests](DEVELOPMENT.md#browser-tests) with external network
blocked. Review the locale at 320, 390, 768, 1024, 1440 and 1920 px, including
help/tutorial, keyboard and focus, filters, dialogs, details, notes/exports,
startup errors, inactive tabs, reload/history, storage failure and update handoff.
Real browser and native installer checks are separate from Node/in-memory tests.
Synthetic test locales are temporary fixtures, not reviewed translations to ship.

Submit the locale's source folder and deterministic generated products. Describe
the language, terminology sources, coverage, actual checks, human review and
remaining gaps. Keep unrelated changes in separate PRs. Exclude logs, archives,
build output, node_modules, environments and user data. Leave application-version
selection and native upgrade/release validation to the maintainer. Follow
[CONTRIBUTING.md](../CONTRIBUTING.md) when preparing the PR.
