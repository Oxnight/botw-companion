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

## Translation regression reference

The independent name and shrine-trial fixture records the public game-text
extraction at MrCheeze/botw-tools commit
`39e57e4731add15b9a0dcedb5dd136215aaba7c7`. It contains names already represented
in the application catalog, not a redistribution of the complete game script.
The fixture checks represented names and shrine trials. It does not establish
that every editorial sentence or French term has independent source coverage.
