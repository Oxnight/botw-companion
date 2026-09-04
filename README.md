# BOTW Companion

BOTW Companion est une application locale qui détecte automatiquement Ryujinx ou Cemu, analyse la sauvegarde correspondante de *The Legend of Zelda: Breath of the Wild* et accompagne une progression complète du jeu.

La version actuelle est **0.40.0 alpha 24**. Elle ajoute une application autonome pour les Mac Apple Silicon sans modifier l’interface, les données de jeu ou les fonctions du site. Les applications Windows et macOS fonctionnent hors ligne après l’installation ; seuls les liens externes des fiches nécessitent une connexion Internet.

## Sommaire

* [Fonctions principales](#fonctions-principales).
* [Configuration prise en charge](#configuration-prise-en-charge).
* [Installer l’application](#installer-lapplication).
* [Installation depuis un clone Git](#installation-depuis-un-clone-git).

  * [1. Cloner le dépôt](#1-cloner-le-dépôt).
  * [2. Installer les prérequis macOS](#2-installer-les-prérequis-macos).
  * [3. Créer l’environnement Python](#3-créer-lenvironnement-python).
  * [4. Premier lancement dans le terminal](#4-premier-lancement-dans-le-terminal).
* [Configurer le gyroscope universel dans Ryujinx ou Cemu](#configurer-le-gyroscope-universel-dans-ryujinx-ou-cemu).
* [Utilisation en ligne de commande](#utilisation-en-ligne-de-commande).
* [Données locales et confidentialité](#données-locales-et-confidentialité).
* [Mise à jour du clone](#mise-à-jour-du-clone).
* [Remarques](#remarques).

## Fonctions principales

* Détection automatique de Ryujinx ou Cemu et actualisation fiable de la sauvegarde BOTW de l’émulateur actif.
* Aperçu visuel du slot sélectionné à partir de son `caption.jpg`, avec numéro, mode, date, émulateur et plateforme.
* Suivi détaillé de la carte officielle, des sanctuaires, quêtes, Korogus, équipements, boss, DLC et autres objectifs.
* Solutions intégrales hors ligne des 152 quêtes, avec étapes spécifiques, prérequis, récompenses, sources et reprise prudente selon l'état détecté.
* Solutions hors ligne des 900 Korogus, avec type d’énigme vérifié, étapes adaptées, prérequis, repères croisés et parcours cartographiques disponibles.
* Solutions hors ligne des coffres : accès individuels lorsque les données le prouvent, méthodes vérifiées par famille dans les autres cas, positions intérieures et mécanismes des sanctuaires et donjons.
* Stratégies intégrales hors ligne des boss et mini-boss, avec 21 variantes documentées, points faibles, phases, dangers, butins et règles d'évolution des ennemis.
* Filtres cartographiques et marqueurs hors ligne.
* Suivi manuel persistant avec vue centralisée, recherche, catégories, accès aux fiches et annulation sécurisée des validations.
* Planificateur d’itinéraire avec sessions persistantes.
* Estimation de la prochaine lune de sang à partir du compteur interne de la sauvegarde.
* Serveur gyroscopique universel compatible Cemuhook/DSU pour Ryujinx et Cemu sur macOS et Windows, avec sélection de la source SDL3.
* Diagnostic gyroscopique détaillé avec qualité globale, cadence, jitter, âge des échantillons, anomalies, réseau et historique de calibration.
* Interface Web locale accessible sur `http://127.0.0.1:8765`.
* Lanceurs macOS et Windows pour démarrer le serveur sans terminal et ouvrir automatiquement le navigateur.

## Configuration prise en charge

* Mac Apple Silicon : M1, M2, M3, M4 ou génération ultérieure.
* macOS 14 ou plus récent, Apple Silicon uniquement.
* Windows 10/11 : détection de Ryujinx standard/portable et de Cemu standard/portable, avec lecture du `mlc_path` de Cemu lorsqu’il est personnalisé.
* Python 3.10 ou plus récent, Python 3.12 recommandé pour un clone ; aucun Python requis par les applications installées.
* Sur macOS, Ryujinx et Cemu sont détectés comme processus ; l’arrêt automatique fonctionne avec l’un ou l’autre après qu’il a été observé actif.

### État du socle Windows

Cette version alpha détecte automatiquement les sauvegardes Ryujinx et Cemu. Pour Cemu, elle inspecte les dossiers standards, les installations portables connues, le chemin de l’exécutable Cemu actuellement lancé et le `mlc_path` enregistré dans `settings.xml`.

Deux variables permettent de forcer un emplacement particulier sans modifier le code :

* `RYUJINX_DATA_DIR` : dossier de données Ryujinx contenant `bis\user\save` ;
* `BOTW_COMPANION_DATA_DIR` : dossier persistant de BOTW Companion.

Le cœur du cycle de vie Windows reconnaît `Ryujinx.exe`, `Ryujinx.Ava.exe` et `Cemu.exe`, empêche une seconde instance du serveur pour le même utilisateur et ne dépend jamais du heartbeat d’un onglet. La surveillance ne déclenche un arrêt qu’après avoir réellement vu un émulateur supporté actif puis confirmé sa fermeture après un délai de grâce. Une reprise après veille réinitialise cette confirmation afin d’éviter un faux arrêt.

L’interface affiche automatiquement **Windows** ou **macOS**, utilise la consigne de relance adaptée et indique le nom ainsi que l’emplacement du journal du moteur natif correspondant. Les lanceurs graphiques activent automatiquement la surveillance de Ryujinx ou Cemu. Le bouton **Activer** lance le moteur JoyConDSU embarqué sans terminal ; les états de calibration, d'attente, de disponibilité et d'erreur sont identiques sur les deux plateformes.

Pour préparer le lanceur Windows depuis un clone, utiliser PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Dans un clone Windows, construire une fois le moteur avant d'utiliser le bouton du gyroscope :

```powershell
.\tools\build_joycon_dsu_windows.ps1
```

Le script place automatiquement `JoyConDSU.exe`, `SDL3.dll` et leur manifeste dans les ressources utilisées par le Companion.

La chaîne de distribution Windows produit maintenant un paquet autonome. Elle utilise PyInstaller en mode one-folder afin d'éviter l'extraction temporaire et le ralentissement initial du mode one-file. L'installateur Inno Setup place l'application dans `%LOCALAPPDATA%\Programs\BOTW Companion`, crée le raccourci du menu Démarrer et propose celui du Bureau. Les données personnelles restent dans `%LOCALAPPDATA%\BOTW Companion` et ne font pas partie des fichiers désinstallés.

## Installer l’application

Télécharger le fichier correspondant depuis [GitHub Releases](https://github.com/Oxnight/botw-companion/releases) :

* Windows x64 : `BOTW_Companion_0.40.0-alpha.24_Setup.exe` ;
* Mac Apple Silicon : `BOTW_Companion_0.40.0-alpha.24_macOS_arm64.dmg`.

Sous Windows, lancer l’installateur. Sous macOS, ouvrir le DMG puis glisser **BOTW Companion** dans **Applications**. Les deux paquets incluent Python, toutes les données et cartes hors ligne, le moteur JoyConDSU, SDL3, les icônes et le lanceur. Git, Python, Homebrew, Xcode, Visual Studio et un clone du dépôt ne sont pas nécessaires.

Ces versions alpha ne sont pas signées avec un certificat commercial. Windows SmartScreen ou macOS Gatekeeper peuvent donc demander une confirmation. Télécharger uniquement depuis la page Releases officielle ; sous macOS, utiliser **Réglages Système > Confidentialité et sécurité > Ouvrir quand même** si nécessaire.

## Installation depuis un clone Git

### 1. Cloner le dépôt

```bash
git clone https://github.com/Oxnight/botw-companion.git
cd botw-companion
```

### 2. Installer les prérequis macOS de développement

```bash
xcode-select --install
brew install sdl3
```

### 3. Créer l’environnement Python

Avec `uv` :

```bash
uv sync
```

Ou avec Python et `pip` :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

### 4. Premier lancement dans le terminal

```bash
.venv/bin/python -m botw_companion interface
```

BOTW Companion cherche automatiquement les emplacements habituels des sauvegardes Ryujinx. Pour analyser explicitement un dossier de sauvegarde :

```bash
.venv/bin/python -m botw_companion interface "/chemin/vers/la/sauvegarde"
```

## Lanceur Windows depuis un clone de développement

Après avoir créé `.venv` avec les commandes PowerShell ci-dessus, ouvrir le dossier `windows` et double-cliquer sur `Installer BOTW Companion.cmd`. L’installeur ne demande pas de droits administrateur. Il crée un raccourci sur le Bureau et dans le menu Démarrer, puis conserve les réglages dans `%LOCALAPPDATA%\BOTW Companion`.

Le raccourci utilise `wscript.exe` et `pythonw.exe` : aucune fenêtre de terminal n’apparaît. Un clone de développement utilise `.venv\Scripts\pythonw.exe`.

À chaque double-clic, le lanceur vérifie d’abord le serveur local. S’il fonctionne déjà, il tente de remettre la fenêtre BOTW Companion au premier plan ; Windows peut refuser cette opération selon ses règles de sécurité, auquel cas le navigateur par défaut ouvre ou réactive la page. Sinon, le serveur démarre puis le navigateur s’ouvre une seule fois. Après avoir vu Ryujinx actif, la surveillance vérifie son état toutes les 15 secondes et demande un arrêt propre après 30 secondes d’absence confirmée.

Le fichier `%LOCALAPPDATA%\BOTW Companion\launcher.json` permet de changer le port, d’indiquer une sauvegarde précise ou d’ajouter le nom d’un exécutable Ryujinx personnalisé. Les erreurs de lancement sont consignées dans `%LOCALAPPDATA%\BOTW Companion\launcher.log`.

### Construire l'application Windows

La construction doit être effectuée sous Windows x64 avec Python 3.12, Visual Studio 2022 Build Tools comprenant C++ et CMake, ainsi qu'Inno Setup 6 :

```powershell
.\tools\build_windows_app.ps1
```

Le script compile le moteur C, crée un environnement de construction isolé, génère le dossier `dist\BOTW Companion`, vérifie ses ressources par un auto-test, puis produit l'installateur dans `dist\installer`. La même procédure est exécutée automatiquement par le workflow Windows du dépôt.

## Configurer le gyroscope universel dans Ryujinx ou Cemu

1. Connecter la manette à l’ordinateur en Bluetooth ou en USB.
2. Dans BOTW Companion, choisir la **Source du gyroscope**. Toutes les manettes détectées par SDL3 sont affichées ; seules celles qui exposent réellement gyro + accéléromètre peuvent être activées. La paire Joy-Con reste proposée comme une source unique en mode grip.
3. Dans Ryujinx ou Cemu, activer la source de mouvement Cemuhook/DSU.
4. Utiliser l’hôte `127.0.0.1` et le port `26760`.
5. Cliquer sur **Activer** puis laisser la manette immobile pendant la calibration.
6. Attendre l’état **Gyroscope prêt** avant de jouer.

Le serveur DSU reste désactivé par défaut. Le moteur conserve le calibrage, la précision, le protocole, la reconnexion et l’arrêt propre déjà utilisés pour les Joy-Con. Le traitement n’ajoute ni filtre ni zone morte aux mouvements.

## Utilisation en ligne de commande

Afficher un résumé de progression :

```bash
.venv/bin/python -m botw_companion analyse
```

Lister les éléments restant dans une catégorie :

```bash
.venv/bin/python -m botw_companion reste --categorie sanctuaires
```

Surveiller les nouvelles sauvegardes :

```bash
.venv/bin/python -m botw_companion surveille --intervalle 3
```

Afficher toutes les options :

```bash
.venv/bin/python -m botw_companion --help
```

## Données locales et confidentialité

Le serveur écoute uniquement sur l’interface locale `127.0.0.1`. Les sauvegardes et données de progression ne sont pas envoyées vers un service distant.

Les fichiers personnels, journaux et préférences sont conservés hors du dépôt, principalement dans :

```text
~/Library/Application Support/BOTW Companion/
```

Sous Windows, ils sont conservés dans :

```text
%LOCALAPPDATA%\BOTW Companion\
```

L’API locale `/api/version` fournit le chemin exact du dossier de données et du journal DSU à l’interface. Le survol de l’encadré DSU affiche également l’emplacement réellement utilisé.

## Validation des navigateurs

Installer une fois la dépendance de test et lancer le serveur synthétique :

```bash
npm install --ignore-scripts
python tools/browser_test_server.py --port 18765
```

Le même test fonctionnel peut ensuite viser les trois navigateurs prévus :

```bash
node tools/browser_smoke.js http://127.0.0.1:18765 chrome
node tools/browser_smoke.js http://127.0.0.1:18765 edge
node tools/browser_smoke.js http://127.0.0.1:18765 firefox
```

Chrome et Microsoft Edge doivent être installés sur la machine de test Windows. Le workflow teste Chrome, Edge et Firefox sous Windows, puis Chromium, Firefox et WebKit sur Apple Silicon. Le parcours vérifie le chargement, les filtres, la carte, le zoom, les fiches, la désélection, la liste centralisée des validations manuelles et la conservation des notes après annulation, le planificateur, l’import/export, la lune de sang, la synchronisation, le bouton DSU, son diagnostic détaillé et l’affichage responsive.

## Mise à jour du clone

Après un `git pull`, resynchroniser l’environnement :

```bash
uv sync
```

ou, sans `uv` :

```bash
.venv/bin/python -m pip install -e .
```

Les lanceurs macOS et Windows vérifient la version du serveur déjà ouvert. Lorsqu’une nouvelle version du code est installée, ils ferment l’ancienne instance locale avant de lancer la nouvelle.

## Remarques

* `manual_tracking.json`, `route_sessions.json`, `preferences.json` et `runtime_state.json` possèdent chacun un schéma versionné et une sauvegarde valide. La première lecture d’un ancien format utilisateur conserve aussi une copie `pre-migration`.
* La sauvegarde générale contient le suivi manuel, les itinéraires et les préférences portables. Son import restaure l’ensemble ou revient intégralement à l’état précédent en cas d’échec.
* `runtime_state.json` mémorise uniquement sur la machine la dernière source Ryujinx et l’historique récent de synchronisation. Il n’est jamais inclus dans un export multiplateforme, car il peut contenir un chemin local.
* Les fichiers `catalog_fr_compiled.json`, `cartography_reference_fr_compiled.json` et `nomenclature_audit_compiled.json` sont des ressources d’exécution nécessaires au démarrage rapide : ils doivent rester dans le dépôt.
* Les tuiles de `botw_companion/web/map-tiles/` sont nécessaires à la carte haute définition hors ligne.
* L’interface ne charge automatiquement aucune police, bibliothèque, image ou API distante. Les liens vers des guides externes restent optionnels et n’empêchent aucune fonction locale lorsque l’ordinateur est hors ligne.
* Le dossier `third_party/JoyConDSU/Sources/JoyConDSU/` est nécessaire à la compilation locale du serveur DSU.
