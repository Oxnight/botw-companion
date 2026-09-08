# Avis relatifs aux composants tiers

Ce document couvre les composants logiciels utilisés pour produire ou exécuter
BOTW Companion. Les données et ressources éditoriales sont décrites séparément
dans [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Composants présents dans les applications distribuées

### CPython 3.12

Les applications Windows et macOS embarquent un runtime CPython 3.12. Python est
distribué selon la Python Software Foundation License Version 2 et contient des
éléments régis par les avis reproduits dans le texte officiel complet :
[`licenses/PYTHON-3.12.txt`](licenses/PYTHON-3.12.txt).

Copyright © 2001 Python Software Foundation. All Rights Reserved.

Source officielle : <https://docs.python.org/3/license.html>

### Simple DirectMedia Layer 3.4.14

Le moteur JoyConDSU est distribué avec SDL 3.4.14 sous licence zlib. Le texte
complet est fourni dans [`licenses/SDL3-3.4.14.txt`](licenses/SDL3-3.4.14.txt)
et à côté de la bibliothèque native dans chaque paquet.

Copyright © Sam Lantinga and the SDL contributors.

Sources officielles : <https://www.libsdl.org/license.php> et
<https://github.com/libsdl-org/SDL/tree/release-3.4.14>

### BOTW Companion et JoyConDSU

Le code propre à BOTW Companion, y compris le moteur JoyConDSU situé dans ce
dépôt, est distribué sous la licence MIT du fichier [`LICENSE`](LICENSE).
JoyConDSU utilise SDL3 mais ne contient pas le code du projet tiers historique
portant le même nom.

## Outils de construction non installés chez le joueur

* **PyInstaller 6.22.2** produit les bundles autonomes. Sa licence GPL 2.0 avec
  exception autorise les exécutables générés à conserver la licence du projet
  et précise qu'aucun avis PyInstaller n'est requis dans l'application :
  <https://pyinstaller.org/en/stable/license.html>.
* **Inno Setup 6** produit uniquement l'installateur Windows. Son avis officiel
  autorise cet usage et apprécie, sans l'imposer, une mention dans la
  documentation : <https://jrsoftware.org/files/is/license.txt>.
* **CMake**, les compilateurs Apple Clang/MSVC, **setuptools** et les actions
  GitHub servent uniquement à la construction et ne sont pas installés avec
  BOTW Companion.
* **Playwright 1.62.0** (Apache-2.0) et **axe-core 4.13.0** (MPL-2.0) servent
  uniquement aux tests navigateur. Ils ne sont pas présents dans les deux
  applications publiées.

Les versions et le périmètre de ces composants sont contrôlés par
`tools/audit_distribution.py` avant chaque construction.
