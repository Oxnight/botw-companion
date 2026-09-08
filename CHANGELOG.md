# Journal des versions

Ce fichier recense les changements visibles ou importants de BOTW Companion.
Il suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le projet
utilise [Semantic Versioning](https://semver.org/lang/fr/).

## [À venir]

## [0.40.0-alpha.33] - 2026-09-08

### Ajouté

- Guides distincts pour l'installation, le gyroscope DSU, le dépannage et le
  développement.
- Instructions de contribution et historique public des versions.
- Contrôles automatiques de la structure et des liens de la documentation.

### Modifié

- README recentré sur la présentation du projet et le démarrage rapide.
- Documents utiles aux joueurs inclus dans les applications autonomes.

## [0.40.0-alpha.32] - 2026-09-08

### Ajouté

- Licences complètes de Python 3.12 et SDL3 dans les deux applications.
- Registre de provenance des données, politique de confidentialité et politique
  de sécurité.
- Audit bloquant des composants distribués et des actifs de release.

## [0.40.0-alpha.31] - 2026-09-08

### Ajouté

- Guide de premier lancement accessible et réouvrable depuis l'interface.
- Navigation au clavier, focus visible, annonces pour lecteurs d'écran et prise
  en charge de la réduction des animations.
- Audit automatisé WCAG 2.2 AA dans les parcours navigateur.

## [0.40.0-alpha.30] - 2026-09-08

### Modifié

- Workflow rendu indépendant d'une version précise.
- Tags, titres de release et noms d'installateurs dérivés d'une source de
  version unique.
- Commits et pull requests limités aux tests ; publication réservée aux tags.

## [0.40.0-alpha.29] - 2026-09-08

### Modifié

- Validation des installations propres et des mises à niveau depuis
  l'alpha 24 sur Windows et macOS.
- Conservation vérifiée du suivi manuel, des itinéraires, des préférences et
  des raccourcis.

## [0.40.0-alpha.28] - 2026-09-08

### Modifié

- Refonte complète des états visuels et de l'animation de la lune de sang.
- Références visuelles automatiques ajoutées aux tests navigateur.

## [0.40.0-alpha.27] - 2026-09-08

### Sécurité

- Jeton de session obligatoire pour les actions locales sensibles.
- Vérification de l'hôte, de l'origine et du contexte des requêtes.
- Ajout d'en-têtes de protection et refus des origines distantes.

## [0.40.0-alpha.26] - 2026-09-08

### Modifié

- Traduction française complétée et audit récursif de la nomenclature.
- Ressources françaises précompilées pour conserver un démarrage rapide hors
  ligne.

## [0.40.0-alpha.25] - 2026-09-08

### Corrigé

- Détection permanente de la victoire contre Ganon grâce à `GameClear`.
- Formules du pourcentage officiel et du profil de complétion rendues
  indépendantes et dédupliquées.
- Liste des éléments qui empêchent encore d'atteindre 100 %.

## [0.40.0-alpha.24] - 2026-09-07

### Ajouté

- Application et DMG autonomes pour macOS 14 ou ultérieur sur Apple Silicon.
- Runtime Python, JoyConDSU et SDL3 intégrés sans dépendance à Homebrew ou
  Xcode chez le joueur.

## [0.40.0-alpha.23] - 2026-09-02

### Ajouté

- Installateur Windows x64 autonome avec runtime Python, JoyConDSU et SDL3.
- Raccourcis Bureau et menu Démarrer et conservation des données à la mise à
  niveau.

[À venir]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.33...HEAD
[0.40.0-alpha.33]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.32...v0.40.0-alpha.33
[0.40.0-alpha.32]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.31...v0.40.0-alpha.32
[0.40.0-alpha.31]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.30...v0.40.0-alpha.31
[0.40.0-alpha.30]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.29...v0.40.0-alpha.30
[0.40.0-alpha.29]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.28...v0.40.0-alpha.29
[0.40.0-alpha.28]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.27...v0.40.0-alpha.28
[0.40.0-alpha.27]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.26...v0.40.0-alpha.27
[0.40.0-alpha.26]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.25...v0.40.0-alpha.26
[0.40.0-alpha.25]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.24...v0.40.0-alpha.25
[0.40.0-alpha.24]: https://github.com/Oxnight/botw-companion/compare/v0.40.0-alpha.23...v0.40.0-alpha.24
[0.40.0-alpha.23]: https://github.com/Oxnight/botw-companion/releases/tag/v0.40.0-alpha.23
