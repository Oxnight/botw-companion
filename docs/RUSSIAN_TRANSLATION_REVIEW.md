# Russian translation review

## Complete draft, disabled locale

All required input values are supplied:

| Resource | Supplied | Required |
| --- | ---: | ---: |
| Fluent interface, help, diagnostic and game-guide messages | 1,692 | 1,692 |
| Game identities | 5,676 | 5,676 |
| Shrine trial titles | 136 | 136 |
| Prose values | 12,650 | 12,650 |

There are no missing message IDs, game IDs, trial IDs or prose keys. Fifteen
technical literals in the last batch (CLI options, Content-Disposition values
and internal actor identifiers) are intentionally preserved under
`docs/TRANSLATING.md`; they are not untranslated user-facing sentences.
The complete list is in `RUSSIAN_REMAINING_PROSE.json`.

This is a complete translation draft ready for testing, not final human approval.
`locale.json` remains `enabled: false`. Selective browser visual review with a real save has been completed; native screens and a full gameplay review remain pending.
The installer is outside this change. No commit or PR has been created.

## Terminology and sources

`RUSSIAN_NAME_REVIEW.json` records per-term sources, per-identity mappings,
excluded source errors and contextual corrections. `RUSSIAN_PROSE_REVIEW.json`
records every supplied prose value and its French source key.

Main references are the BOTW Russian name tables on Zelda Wiki, Anton’s
Russian/English BOTW StaticMsg glossary, and his Russian Creating a Champion
v1.2 reference. Only factual terms are used; workbook/book files, pictures and
article paragraphs are not bundled. Provenance is registered in DATA_SOURCES.md.

Additional quest titles are compared with a community reproduction of the
Russian quest log. These pages contain typos and are not a Nintendo glossary.
Some remaining names use proposed editorial wording or comparative Kiranico
Tears of the Kingdom references. They are explicitly listed in
`RUSSIAN_TERMINOLOGY_REVIEW.md` and `provisional_terms_for_botw_review`; sequel
spellings are not asserted to prove BOTW spellings. There are 46 unique terms
in that review list, including the descriptive Travel Medallion prose label.
Do not describe draft coverage as independent confirmation of every official name.

The user-supplied Sky Octorok translation is «Небесный окторок»; its source and
review status remain explicit. Cucco uses «кокко». Sentry uses «Дозорный» in
accordance with the bilingual glossary. Apparent transcription mistakes are
reconciled or flagged. The source spelling «Синеволный воробей» is preserved
because it also appears in the comparative table; no guessed spelling replaces it.

Some original guides confuse NPCs or shrines. Contextual corrections use the
quest/actor identity rather than global aliases. In particular the roast quest
reveals Kayra Mah, and the stone-pillar song reveals Voo Lota. Other source-guide
mechanics still require gameplay review (for example the mushroom quantity).

## Wording and technical decisions

- Translate complete phrases using French and English context.
- Use «цель» for objective and «ручная отметка» for manual validation.
- Distinguish a game save from a backup archive and a chest from a safe.
- Preserve stable IDs, coordinates, filenames, URLs and program commands.
- Preserve significant whitespace and markup attributes in legacy fragments.
- Count-neutral Russian legacy templates omit French plural/gender suffix
  slots while retaining numeric, display and non-suffix values. Each such
  decision is documented in the prose review record.

A public Google Translate endpoint supplied isolated candidates from public
project strings with protected names/parameters. Raw candidates are excluded
from locale inputs. Accepted editorial batches were rewritten as complete
Russian phrases; generated guide variants reuse sourced terms and translated
full sentences. No translation service or new dependency is used at runtime.

## Validation

- Every Russian input has the exact required key set and nonempty values.
- All 1,692 Fluent messages pass the full parameter/markup contract.
- 6,888 Python rendering probes pass, including Russian plural boundary cases,
  negative values and fractions. All 691 browser-exposed probes also agree
  with their Python results; 6,197 probes cover Python-only messages.
- The full generator succeeds with Russian enabled only in memory: 20 products,
  including all six Russian outputs. The actual manifest remains disabled.
- Supplied prose matches its review record exactly. Game IDs and pending lists
  agree, and all source/review files are UTF-8 with LF line endings.

The normal enabled-locale build check, distribution audit and version check
are run separately. They do not replace Russian wording or visual review.

## Next stage

Editorial review on 2026-10-24 covered all 13 help chapters, tutorial wording,
272 long action entries and 407 additional guidance entries. See
`RUSSIAN_EDITORIAL_REVIEW.md` for corrections and limits. All 46 provisional
terms were researched and retained; the audit does not certify every BOTW label.
Continue native and gameplay validation before enabling a release.

## Contribution staging

This is the fourth contribution (guides/report prose), following shared fixes,
interface/help and game names. The four Russian input files exactly match the
preserved complete draft. Translation was AI-assisted and edited; automated
checks and editorial review do not replace independent human terminology review.
