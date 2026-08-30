# BOTW Companion

BOTW Companion est une application locale qui détecte automatiquement Ryujinx ou Cemu, analyse la sauvegarde correspondante de *The Legend of Zelda: Breath of the Wild* et accompagne une progression complète du jeu.

La version actuelle est **0.40.0 alpha 16**. Elle ajoute un diagnostic visuel du gyroscope partagé par macOS et Windows : qualité excellente, correcte, instable ou recalibration recommandée, accompagnée des fréquences, du jitter, de l’âge des échantillons, des anomalies de timestamps, des paquets, des erreurs réseau, des reconnexions et des calibrations. Elle conserve la détection automatique Ryujinx/Cemu, le gyroscope universel, les migrations et sauvegardes atomiques, le chargement UTF-8 sous Windows et le défilement adaptatif de la liste. L’application fonctionne hors ligne après l’installation ; les liens externes éventuellement proposés dans certaines fiches restent naturellement soumis à une connexion Internet.

## Sommaire

* [Fonctions principales](#fonctions-principales).
* [Configuration prise en charge](#configuration-prise-en-charge).
* [Installation depuis un clone Git](#installation-depuis-un-clone-git).

  * [1. Cloner le dépôt](#1-cloner-le-dépôt).
  * [2. Installer les prérequis macOS](#2-installer-les-prérequis-macos).
  * [3. Créer l’environnement Python](#3-créer-lenvironnement-python).
  * [4. Premier lancement dans le terminal](#4-premier-lancement-dans-le-terminal).
* [Installer le lanceur macOS](#installer-le-lanceur-macos).
* [Installer le lanceur Windows](#installer-le-lanceur-windows).
* [Configurer le gyroscope universel dans Ryujinx ou Cemu](#configurer-le-gyroscope-universel-dans-ryujinx-ou-cemu).
* [Utilisation en ligne de commande](#utilisation-en-ligne-de-commande).
* [Données locales et confidentialité](#données-locales-et-confidentialité).
* [Mise à jour du clone](#mise-à-jour-du-clone).
* [Remarques](#remarques).

## Fonctions principales

* Détection automatique de Ryujinx ou Cemu et actualisation fiable de la sauvegarde BOTW de l’émulateur actif.
* Suivi détaillé de la carte officielle, des sanctuaires, quêtes, Korogus, équipements, boss, DLC et autres objectifs.
* Filtres cartographiques et marqueurs hors ligne.
* Suivi manuel persistant pour les éléments que la sauvegarde ne peut pas prouver.
* Planificateur d’itinéraire avec sessions persistantes.
* Estimation de la prochaine lune de sang à partir du compteur interne de la sauvegarde.
* Serveur gyroscopique universel compatible Cemuhook/DSU pour Ryujinx et Cemu sur macOS et Windows, avec sélection de la source SDL3.
* Diagnostic gyroscopique détaillé avec qualité globale, cadence, jitter, âge des échantillons, anomalies, réseau et historique de calibration.
* Interface Web locale accessible sur `http://127.0.0.1:8765`.
* Lanceurs macOS et Windows pour démarrer le serveur sans terminal et ouvrir automatiquement le navigateur.

## Configuration prise en charge

* Mac Apple Silicon : M1, M2, M3, M4 ou génération ultérieure.
* macOS 12 ou plus récent.
* Windows 10/11 : détection de Ryujinx standard/portable et de Cemu standard/portable, avec lecture du `mlc_path` de Cemu lorsqu’il est personnalisé.
* Python 3.10 ou plus récent, Python 3.12 recommandé pour un clone ; aucun Python requis par l'application Windows installée.
* Sur macOS, Ryujinx et Cemu sont détectés comme processus ; l’arrêt automatique fonctionne avec l’un ou l’autre après qu’il a été observé actif.
* Homebrew, SDL3 et les outils en ligne de commande Xcode pour compiler le serveur JoyConDSU sur le Mac cible.

### État du socle Windows

Cette version alpha détecte automatiquement les sauvegardes Ryujinx et Cemu. Pour Cemu, elle inspecte les dossiers standards, les installations portables connues, le chemin de l’exécutable Cemu actuellement lancé et le `mlc_path` enregistré dans `settings.xml`.

Deux variables permettent de forcer un emplacement particulier sans modifier le code :

* `RYUJINX_DATA_DIR` : dossier de données Ryujinx contenant `bis\user\save` ;
* `BOTW_COMPANION_DATA_DIR` : dossier persistant de BOTW Companion.

Le cœur du cycle de vie Windows reconnaît `Ryujinx.exe`, `Ryujinx.Ava.exe` et `Cemu.exe`, empêche une seconde instance du serveur pour le même utilisateur et ne dépend jamais du heartbeat d’un onglet. La surveillance ne déclenche un arrêt qu’après avoir réellement vu un émulateur supporté actif puis confirmé sa fermeture après un délai de grâce. Une reprise après veille réinitialise cette confirmation afin d’éviter un faux arrêt.

L’interface affiche automatiquement **Windows** ou **macOS**, utilise la consigne de relance adaptée et indique le nom ainsi que l’emplacement du journal du moteur natif correspondant. Le lanceur graphique Windows active automatiquement la surveillance de Ryujinx ou Cemu. Le moteur JoyConDSU se construit nativement sous Windows avec Winsock 2.2 et SDL3, puis le bouton **Activer** le lance directement sans fenêtre de console. Les états de calibration, d'attente, de disponibilité et d'erreur restent identiques à ceux de macOS. Le comportement macOS existant reste inchangé.

Pour préparer le lanceur Windows depuis un clone, utiliser PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

La partie JoyConDSU inclut aussi un binaire Apple Silicon de secours. Une compilation locale reste préférable afin d’utiliser le SDK et la version de SDL3 présents sur la machine. La procédure de construction Windows du moteur est décrite dans `third_party/JoyConDSU/README_WINDOWS.md`.

Dans un clone Windows, construire une fois le moteur avant d'utiliser le bouton du gyroscope :

```powershell
.\tools\build_joycon_dsu_windows.ps1
```

Le script place automatiquement `JoyConDSU.exe`, `SDL3.dll` et leur manifeste dans les ressources utilisées par le Companion.

La chaîne de distribution Windows produit maintenant un paquet autonome. Elle utilise PyInstaller en mode one-folder afin d'éviter l'extraction temporaire et le ralentissement initial du mode one-file. L'installateur Inno Setup place l'application dans `%LOCALAPPDATA%\Programs\BOTW Companion`, crée le raccourci du menu Démarrer et propose celui du Bureau. Les données personnelles restent dans `%LOCALAPPDATA%\BOTW Companion` et ne font pas partie des fichiers désinstallés.

## Installation depuis un clone Git

### 1. Cloner le dépôt

```bash
git clone https://github.com/Oxnight/botw-companion.git
cd botw-companion
```

### 2. Installer les prérequis macOS

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

## Installer le lanceur macOS

Le lanceur ne copie pas tout le projet dans l’application : il démarre le clone avec le Python de `.venv`. Le clone et son environnement doivent donc rester présents sur le Mac.

Depuis le Finder, double-cliquer sur :

```text
macos/Installer BOTW Companion.command
```

Si macOS ne l’autorise pas encore à s’exécuter :

```bash
chmod +x "macos/Installer BOTW Companion.command"
"macos/Installer BOTW Companion.command"
```

L’installeur copie `BOTW Companion.app` dans `~/Applications`. Au premier lancement, si le projet n’est pas trouvé automatiquement, l’application demande de sélectionner le dossier cloné contenant `pyproject.toml` et `.venv`.

L’application n’est pas signée avec un certificat Apple. Si Gatekeeper la bloque après le téléchargement, utiliser **Réglages Système > Confidentialité et sécurité > Ouvrir quand même**, ou faire un clic droit sur l’application puis **Ouvrir**. Il n’existe pas de réinstallation périodique tous les sept jours pour cette application locale.

## Installer le lanceur Windows

### Application autonome recommandée

Télécharger l'artefact Windows produit par l'automatisation GitHub, puis lancer :

```text
BOTW_Companion_0.40.0-alpha.16_Setup.exe
```

L'installation se fait pour l'utilisateur courant et ne nécessite normalement pas de droits administrateur. Python, le clone Git, Visual Studio et SDL3 ne sont pas requis pour utiliser cette version. L'application apparaît dans le menu Démarrer, dans les applications installées et, si l'option est cochée, sur le Bureau.

Cette version alpha n'est pas encore signée. Windows SmartScreen peut donc demander une confirmation ; la signature et le durcissement de la distribution correspondent à l'étape 14 de la roadmap.

### Lanceur depuis un clone de développement

Après avoir créé `.venv` avec les commandes PowerShell ci-dessus, ouvrir le dossier `windows` et double-cliquer sur `Installer BOTW Companion.cmd`. L’installeur ne demande pas de droits administrateur. Il crée un raccourci sur le Bureau et dans le menu Démarrer, puis conserve les réglages dans `%LOCALAPPDATA%\BOTW Companion`.

Le raccourci utilise `wscript.exe` et `pythonw.exe` : aucune fenêtre de terminal n’apparaît. Un runtime autonome placé dans `runtime\pythonw.exe` est utilisé en priorité lorsqu’il est fourni par un futur paquet ; un clone de développement utilise `.venv\Scripts\pythonw.exe`.

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

Chrome et Microsoft Edge doivent être installés sur la machine de test ; Firefox peut être installé par `npx playwright install firefox`. Le parcours vérifie le chargement, les filtres, la carte, le zoom, les fiches, la désélection, le suivi manuel, le planificateur, l’import/export, la lune de sang, la synchronisation, le bouton DSU, son diagnostic détaillé et l’affichage responsive. Ces parcours se lancent localement sur la machine utilisée pour la validation.

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