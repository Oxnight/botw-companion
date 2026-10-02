# French and English localization audit

Audited on 2026-10-02 against the complete RC8 source archive. Nothing was
pushed, tagged, or published during this audit.

## Findings and corrections

| Finding | Correction |
| --- | --- |
| Separately translated template fragments could corrupt quotes and technical HTML attributes. | Translate complete phrases and templates; preserve class names, identifiers, URLs, and expression order. Compare the generated HTML structure with French. |
| Hidden detail and route controls retained French text. | Translate map buttons, tooltips, accessible labels, counters, conditional instructions, and route actions. |
| Literal map/card, save/backup, and coordinate/contact translations were misleading. | Use context-specific interface terminology in help, details, diagnostics, and messages. |
| French plural suffixes leaked into English adjectives. | Preserve noun plurals and remove adjective suffixes, including completion and chest counters. |
| Guardian Shield, Spear, and Sword 1.0/3.0 aliases were inverted. | Restore the base, +, and ++ sequence; retain authoritative actor-ID resolution and regression tests. |
| Game terms in prose differed from item names. | Correct Stasis, Sheikah Slate, One-Hit Obliterator, blight bosses, Divine Beasts, cooking pots, rafts, and equipment variants in instructions as well as labels. |
| Two French quest instructions incorrectly named Dézelle. | Use Della/Bedoli for The Ancient Rito Song and Onag/Prima for A Gift for My Beloved. |
| A game name inside an error's file path could be translated. | Preserve literal user paths and URLs while translating the surrounding diagnostic. |
| Rare invalid-JSON, missing-folder, and missing-GameData diagnostics retained French. | Add complete message translations and inspect 158 raised diagnostics, including interpolated values. |
| Trial of the Sword strategies contained literal weapon/enemy terms and incorrect imperative verbs. | Review all 54 distinct strategies and their 54 room summaries; use Ancient Arrows, Wizzrobes, Keese, Stalhorse, Stone Smasher, and Stasis+. |
| Additional guide phrases confused the Divine Beast trunk with a chest, lost the afternoon in 15:00, or duplicated shrine names. | Correct whole phrases and embedded official names, including Oman Au Shrine, Misko, Drillshaft, and Meteo Wizzrobe. |
| Additional Zora quest steps used misspelled or English NPC names in French. | Use Jitato/Jiahto and Poréa/Torfeau in the respective languages. |
| Generated export download names remained French in English mode. | Localize the generated download filename while preserving the JSON data and user-written content. |

## Terminology evidence

Game names were compared against the ActorType, QuestMsg, Dungeon, and
LocationMarker entries in
[botw-tools at the pinned revision](https://github.com/MrCheeze/botw-tools/tree/39e57e4731add15b9a0dcedb5dd136215aaba7c7).
The reference contains 5,676 identifier-based entries, including descriptive
map labels. An independent direct comparison covered 726 entries with matching
game text keys: 590 exact names and 136 shrine chest labels with the additional
"Chest -" prefix. The 1,220 unique French aliases were also compared; remaining
differences were reviewed for short Divine Beast names, regional grouping
labels, typographic apostrophes, contextual Rito/Snowquill usage, and descriptive
shop labels replacing technical UMii identifiers.

Expansion terms were checked against
[Nintendo's game page](https://www.nintendo.com/en-gb/Games/Nintendo-Switch-games/The-Legend-of-Zelda-Breath-of-the-Wild-1173609.html)
and [The Champions' Ballad](https://ec.nintendo.com/AU/en/aocs/70050000000186).
European French NPC names were checked against the game-screen references in
[Bedoli/Della](https://zeldawiki.wiki/wiki/Bedoli) and
[Prima/Onag](https://zeldawiki.wiki/wiki/Prima). Zora names were additionally
compared with the packaged French nomenclature reference and the
[Jiahto](https://zeldawiki.wiki/wiki/Jiahto),
[Torfeau](https://zeldawiki.wiki/wiki/Torfeau), and
[Gruve](https://zeldawiki.wiki/wiki/Gruve) game-screen references.

Editorial walkthrough sentences are project content, not official Nintendo
translations. Official names are used within those instructions. Translation
references are packaged offline; no external translation service is called
when changing languages.

## Validation performed

- All 423 Python tests passed, including per-request language precedence,
  static HTML and accessible labels, official equipment variants, full catalog
  translation, coordinates, identifiers, cached-report isolation, notes,
  route exports, and backups.
- The localization audit passed for 859 distinct strings and complete templates.
  It checks conditional UI prose, hidden attributes, generated HTML structure,
  and API path parity. It also checks 158 raised diagnostics. Release validation runs this audit on Windows and macOS.
- Browser geometry checks now wait for the current frame/target relation after
  resize delivery, before asserting complete highlighting and no overlap.
- Complete Chromium 154 and Firefox 153 smoke suites passed locally on Linux:
  French desktop behavior, responsive layout, keyboard accessibility, zoom at
  200%, reduced motion, local dates, manual tracking, routes, and DSU controls.
- English checks passed for all 13 help chapters and all 10 essential tour
  steps, objective details, route buttons and attributes, preserved personal
  notes, French/English switching, remembered selection, mobile help, and
  absence of external requests during the language workflow.
- Generated English asset consistency, JavaScript syntax, version consistency,
  distribution provenance, and repository hygiene checks passed.
- The base map was visually inspected: its raster contains no French labels;
  game labels come from the localized interface and catalog.

## Scope and remaining platform validation

French remains the default. Both languages use the same save analysis, IDs,
coordinates, completion rules, personal data, and offline map. The audit also
covers conditional strings that need not appear in the initial screen.
User-written notes, custom session names, filenames, and imported personal
content retain their original language. Exports retain the original data.

The tests above are evidence for the checked corpus and scenarios, not a
linguistic certification of every future sentence or every runtime input.
The supplied Windows/macOS workflow logs confirm all 423 Python tests and
localization checks passed on both platforms. Browser checks then failed on
WebKit native select style reporting and the Windows language/reload sequence.
The browser harness now waits for each language document to initialize, uses
portable stylesheet readiness probes, and records readiness failure snapshots.
Native Windows/macOS installer and updater jobs, Edge, and WebKit remain to be
confirmed by the release workflow. WebKit could not be run locally because
the execution host lacked its required system libraries. External sites and
operating-system dialogs use their own language settings.

## Reproduce

```sh
npm ci --ignore-scripts
python tools/build_english_assets.py --check
python tools/audit_localization.py
python tools/check_version_consistency.py
python tools/audit_distribution.py
python -m unittest discover -s tests -v
```

The existing release workflow runs the browser matrix and native packaging
checks. Do not create the release tag until those jobs pass.
