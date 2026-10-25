# Data sources and intellectual property

BOTW Companion is an unofficial fan project. It is not affiliated with,
endorsed by, sponsored by, or supported by Nintendo. *The Legend of Zelda*,
*Breath of the Wild*, and related material belong to their respective owners.
The repository's MIT License applies only to original BOTW Companion code and
content. It grants no rights to third-party trademarks, data, or assets.

## Source register

| Material | Use | Source and identified terms |
| --- | --- | --- |
| Hyrule map | Offline WebP tiles | `botw_map.png`, hosted by ZeldaMods and extracted from game files. Nintendo-owned material; this repository contains no redistribution permission. See `botw_companion/web/map-tiles/SOURCE.txt`. |
| BOTW Object Map | Coordinates, identifiers, and factual checks | [zeldamods/objmap](https://github.com/zeldamods/objmap), GPL-3.0 code. No code from that project is bundled; its license does not cover the game-extracted map. |
| MrCheeze/botw-tools | Identifiers and placements derived from game data | [MrCheeze/botw-tools](https://github.com/MrCheeze/botw-tools). The repository publishes no license; none of its programs are bundled. |
| ZeldaMods Wiki | Technical documentation and internal-data context | [ZeldaMods Wiki](https://zeldamods.org/wiki/Main_Page), CC BY-SA unless a page states otherwise. |
| Zelda Wiki | Quest names and facts used as references | [Zelda Wiki](https://zeldawiki.wiki/), editorial content generally under CC BY-SA 4.0. Selected facts were normalized and translated; source URLs remain in records. |
| Zelda Dungeon | Checks for routes, chests, Koroks, bosses, and quests | [Zelda Dungeon](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/). Used as a factual reference; no article, media, or program is bundled. |
| Palais de Zelda | French terminology and cross-checks | [Palais de Zelda](https://www.palaiszelda.com/breathofthewild/). Names and facts were normalized; no page, image, or program is bundled. |
| Nintendo | Official terminology and game rules | [Official game page](https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-switch/). Factual reference only. |
| Application icons | Windows ICO and macOS ICNS | Artwork stored in `windows/` and `macos/`. Authoring sources and separate permission records are not included; the maintainer must confirm authorship or redistribution rights. |

Offline guides are original project summaries. Their records retain source
links for verification. User save data is never added to the repository or
these datasets.

## Public distribution and intellectual property review

The high-resolution map was extracted from the game. Attribution is not
permission. Before presenting the project as a legally cleared distribution,
the maintainer must obtain written redistribution permission or replace the map
with an original background under terms that explicitly allow inclusion in the
installers. This requires a maintainer decision; an automated test cannot grant
missing rights. The current map is retained while that decision is pending.

The application icons also lack an authoring or permission record. Confirm their
authorship or redistribution rights before a legally cleared distribution.

## English terminology

English names are aligned by game identifiers with the original catalog and
ActorType, Dungeon, and LocationMarker name tables published in
[MrCheeze/botw-tools](https://github.com/MrCheeze/botw-tools/tree/39e57e4731add15b9a0dcedb5dd136215aaba7c7)
(revision `39e57e4731add15b9a0dcedb5dd136215aaba7c7`). Only factual names
are used, not game dialogue or descriptions. Nintendo's
[Explorer's Guide](https://media.nintendo.com/zelda/breath-of-the-wild/assets/ExplorersGuide.pdf)
and [Expansion Pass page](https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-expansion-pass-70070000000041-switch/)
provide checks for game concepts and expansion terminology. The project's
editorial guides are translated separately. All final references are offline;
changing language never fetches a dictionary from a third party.

## Russian terminology draft

The disabled Russian locale uses factual names checked against Zelda Wiki's
[BOTW translation data](https://zeldawiki.wiki/wiki/Data:Translations), including
enemy, item, character, location and miscellaneous tables. Where present, their
citations identify the Russian BOTW compendium, inventory, dialogue or quest log.
This is a community-maintained secondary reference, not a dictionary published
by Nintendo. Tables contain transcription errors; suspect rows are excluded.
No article prose, dialogue paragraphs, programs or media are bundled from it.

`docs/RUSSIAN_NAME_REVIEW.json` records term-level source URLs, whether the table
provides a game citation, per-identity mappings, excluded rows and unresolved
names. Actor identities are checked with the same pinned MrCheeze/botw-tools
revision used for English terminology. Numbered labels retain their numbers;
generic map-service labels are translator-authored application text. Shrine
labels use the corresponding monk's Russian name where the cited dialogue
actually contains it. A small trial-title batch uses the location tables; its
evidence is tracked separately in `trial_mappings`, including game-citation status.

The user supplied «Небесный окторок» for `Sky Octorok`, with the
[lvl.su entry](https://lvl.su/wiki/the-legend-of-zelda-breath-of-the-wild/post/nebesnyi-oktorok)
as a community reference. This term is marked as user-supplied; no official
Russian game citation has been independently verified for it.

Additional names and all 136 trial titles are checked against Anton’s
[BOTW StaticMsg glossary](https://zelda64rus.ucoz.ru/_fr/6/BotW_StaticMsg.xlsx),
published in [Zelda64rus forum post 99](https://zelda64rus.ucoz.ru/forum/31-607-2)
on 7 March 2019. The author describes it as extracted Russian/English game
terminology. This is a community-published reference, not a Nintendo-published
dictionary; final wording review remains pending. Only factual names are used.
The downloaded workbook is not bundled. Its hash and source are recorded in the
name review report. Translations in `prose.json` are documented in `docs/RUSSIAN_PROSE_REVIEW.json`,
including name/title matches, shared interface messages, stable identity aliases
and translator-authored guide patterns. Ambiguous matches are excluded.

Anton’s Russian *Creating a Champion* v1.2 reference (2021-10-21), linked
from the [Zelda64rus media page](https://shedevr.org.ru/zelda64rus/media.html#champion_ru),
provides additional factual names with English equivalents. The name review
report records page locators and the community-source status. No book pages,
illustrations or descriptive paragraphs are included. A few terms are supported
by Russian BOTW playthrough titles and explicitly marked for further review.

Public French project strings were also submitted to a public Google Translate
endpoint to prepare isolated draft candidates. Unchecked outputs are excluded
from locale inputs and completion counts. Accepted editorial batches were
reviewed and rewritten with source context. Translation remains entirely offline
in the distributed application; no new runtime dependency is introduced.

These references do not establish complete human review or distribution rights
for Nintendo content. Keep the locale disabled until its remaining content and
terminology review are complete.

## Translation regression reference

The independent name and shrine-trial fixture records the public game-text
extraction at MrCheeze/botw-tools commit
`39e57e4731add15b9a0dcedb5dd136215aaba7c7`. It contains names already represented
in the application catalog, not a redistribution of the complete game script.
The fixture checks represented names and shrine trials. It does not establish
that every editorial sentence or French term has independent source coverage.

## Additional Russian draft comparisons

The complete Russian draft additionally compares factual quest titles against
[this community quest-log reproduction](https://nastroy.sunnyfresh.ru/ispytanie-chuvstvo-mery-zelda/).
Its errors and inconsistent NPC spellings mean it cannot replace game review.
Only factual titles/names are used, not dialogue or guide paragraphs.

[Kiranico armor](https://zelda.kiranico.com/ru/totk/data/armors),
[animals](https://zelda.kiranico.com/ru/totk/data/animals) and
[enemies](https://zelda.kiranico.com/ru/totk/data/enemies) are explicitly marked
as comparative Tears of the Kingdom references. They do not certify BOTW names.
Proposed editorial terms and comparisons are listed in
`docs/RUSSIAN_TERMINOLOGY_REVIEW.md`; the disabled locale is an incremental draft,
not a claim of independently validated official terminology.
