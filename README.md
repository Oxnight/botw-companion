# BOTW Companion

BOTW Companion analyse localement les sauvegardes de *The Legend of Zelda:
Breath of the Wild* utilisées par Ryujinx ou Cemu et accompagne une progression
complète du jeu.

Le projet est non officiel et n'est ni affilié à Nintendo, ni approuvé,
sponsorisé ou soutenu par Nintendo.

## Télécharger

La version actuelle est disponible dans
[GitHub Releases](https://github.com/Oxnight/botw-companion/releases).

| Système | Fichier à télécharger |
| --- | --- |
| Windows 10/11 x64 | le fichier se terminant par `_Setup.exe` |
| macOS 14 ou ultérieur, Apple Silicon | le fichier se terminant par `_macOS_arm64.dmg` |

Les deux applications sont autonomes : Python, les données et cartes hors
ligne, JoyConDSU, SDL3, les icônes et le lanceur sont inclus. Aucun clone, outil
de développement ou téléchargement supplémentaire n'est nécessaire.

Consulter le [guide d'installation et de mise à jour](docs/INSTALLATION.md) pour
les étapes détaillées et les avertissements SmartScreen ou Gatekeeper.

## Fonctions principales

- Détection automatique de Ryujinx ou Cemu et de leur sauvegarde BOTW la plus
  récente.
- Aperçu du slot sélectionné avec mode, date, émulateur et plateforme.
- Suivi de la carte officielle, des sanctuaires, quêtes, Korogus, équipements,
  boss, DLC et autres objectifs.
- Solutions hors ligne des 152 quêtes, des 900 Korogus, des coffres, des
  sanctuaires et des boss.
- Filtres et marqueurs sur une carte haute définition utilisable hors ligne.
- Suivi manuel, notes et planificateur d'itinéraire persistants.
- Import, export et sauvegardes de sécurité des données du Companion.
- Détection facultative des nouvelles versions avec téléchargement guidé du
  paquet correspondant au système.
- Estimation de la prochaine lune de sang depuis le compteur de la sauvegarde.
- Serveur gyroscopique Cemuhook/DSU pour Ryujinx et Cemu avec diagnostic de
  calibration et de qualité.
- Interface locale accessible, navigation au clavier et réduction des
  animations selon le réglage du système.

## Complétion

Deux mesures indépendantes sont affichées :

- le **pourcentage officiel de la carte**, où chaque marqueur vaut
  `100 / 1207` en jeu de base ou `100 / 1224` avec l'Expansion Pass ;
- le **profil de complétion du compagnon**, calculé avec
  `100 × objectifs automatiques uniques validés / objectifs automatiques uniques du profil`.

Le profil principal contient 3 400 objectifs en jeu de base et 3 565 avec les
DLC. Les activités sans preuve persistante dans la sauvegarde restent dans le
suivi manuel mais ne bloquent pas le 100 %. Les amiibo sont séparés du profil
principal. L'interface liste les **Éléments empêchant le 100 %**.

La victoire contre Ganon est déterminée en priorité par le marqueur persistant
`GameClear`, et non par le seul état temporaire de la quête finale après le
générique.

## Documentation

- [Installation et mises à jour](docs/INSTALLATION.md)
- [Configuration du gyroscope DSU](docs/DSU.md)
- [Dépannage](docs/TROUBLESHOOTING.md)
- [Développement et tests](docs/DEVELOPMENT.md)
- [Contribuer au projet](CONTRIBUTING.md)
- [Journal des versions](CHANGELOG.md)
- [Publier une version](RELEASING.md)

## Données et confidentialité

Le serveur écoute uniquement sur `127.0.0.1`. Les sauvegardes et données de
progression ne sont envoyées à aucun service distant. Seule la liste publique
des Releases GitHub peut être consultée pour signaler une mise à jour ; cette
vérification expire rapidement et n'empêche jamais le fonctionnement hors
ligne. Les liens externes et le téléchargement restent déclenchés par
l'utilisateur.

Les données personnelles sont conservées séparément de l'application :

```text
Windows : %LOCALAPPDATA%\BOTW Companion
macOS   : ~/Library/Application Support/BOTW Companion
```

Une mise à niveau ou une désinstallation ne les supprime pas. Les détails sont
dans [`PRIVACY.md`](PRIVACY.md).

## Sécurité et licences

- [`SECURITY.md`](SECURITY.md) explique comment signaler une vulnérabilité sans
  publier de donnée sensible.
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) recense les composants
  inclus et les outils de construction.
- [`DATA_SOURCES.md`](DATA_SOURCES.md) documente la provenance des données et de
  la carte.
- [`licenses/`](licenses/) contient les textes complets requis par les
  composants redistribués.

Le code propre au projet est distribué sous licence MIT. Cette licence ne
s'étend pas aux marques, ressources ou contenus appartenant à Nintendo ou à
d'autres tiers.
