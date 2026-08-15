# BOTW Companion

BOTW Companion est une application locale qui analyse une sauvegarde Ryujinx de *The Legend of Zelda: Breath of the Wild* et accompagne une progression complète du jeu.

La version actuelle est **0.40.0 alpha 6**. Elle porte le moteur natif JoyConDSU en C sous Windows sans modifier le protocole Cemuhook, la calibration, les timestamps, la télémétrie ni le fonctionnement macOS. La construction Windows reproductible fournit `JoyConDSU.exe` avec sa `SDL3.dll` locale ; son raccordement au bouton du Companion appartient à l’étape suivante. L’application fonctionne hors ligne après l’installation ; les liens externes éventuellement proposés dans certaines fiches restent naturellement soumis à une connexion Internet.

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
* [Configurer le gyroscope Joy-Con dans Ryujinx](#configurer-le-gyroscope-joy-con-dans-ryujinx).
* [Utilisation en ligne de commande](#utilisation-en-ligne-de-commande).
* [Données locales et confidentialité](#données-locales-et-confidentialité).
* [Mise à jour du clone](#mise-à-jour-du-clone).
* [Remarques](#remarques).

## Fonctions principales

* Détection et actualisation fiables de la sauvegarde Ryujinx la plus récente.
* Suivi détaillé de la carte officielle, des sanctuaires, quêtes, Korogus, équipements, boss, DLC et autres objectifs.
* Filtres cartographiques et marqueurs hors ligne.
* Suivi manuel persistant pour les éléments que la sauvegarde ne peut pas prouver.
* Planificateur d’itinéraire avec sessions persistantes.
* Estimation de la prochaine lune de sang à partir du compteur interne de la sauvegarde.
* Serveur gyroscopique Joy-Con compatible Cemuhook/DSU pour Ryujinx sur macOS, avec moteur C désormais portable et constructible sous Windows.
* Interface Web locale accessible sur `http://127.0.0.1:8765`.
* Lanceurs macOS et Windows pour démarrer le serveur sans terminal et ouvrir automatiquement le navigateur.

## Configuration prise en charge

* Mac Apple Silicon : M1, M2, M3, M4 ou génération ultérieure.
* macOS 12 ou plus récent.
* Détection préparée pour Windows 10 et 11 : `%APPDATA%\Ryujinx\bis\user\save` et installations portables identifiables.
* Python 3.10 ou plus récent, Python 3.12 recommandé.
* Ryujinx installé dans `/Applications/Ryujinx.app` pour bénéficier de l’arrêt automatique associé au jeu.
* Homebrew, SDL3 et les outils en ligne de commande Xcode pour compiler le serveur JoyConDSU sur le Mac cible.

### État du socle Windows

Cette version alpha détecte automatiquement le dossier standard `%APPDATA%\Ryujinx\bis\user\save`. Elle reconnaît aussi une installation portable lorsque l’exécutable Ryujinx est indiqué par `RYUJINX_EXECUTABLE` ou `RYUJINX_EXE`, présent dans le `PATH`, ou installé dans un emplacement Windows courant.

Deux variables permettent de forcer un emplacement particulier sans modifier le code :

* `RYUJINX_DATA_DIR` : dossier de données Ryujinx contenant `bis\user\save` ;
* `BOTW_COMPANION_DATA_DIR` : dossier persistant de BOTW Companion.

Le cœur du cycle de vie Windows reconnaît `Ryujinx.exe` et `Ryujinx.Ava.exe`, empêche une seconde instance du serveur pour le même utilisateur et ne dépend jamais du heartbeat d’un onglet. La surveillance ne déclenche un arrêt qu’après avoir réellement vu Ryujinx actif puis confirmé sa fermeture après un délai de grâce. Une reprise après veille réinitialise cette confirmation afin d’éviter un faux arrêt.

L’interface affiche automatiquement **Windows** ou **macOS**, utilise la consigne de relance adaptée et indique le nom ainsi que l’emplacement du journal du moteur natif correspondant. Le lanceur graphique Windows active automatiquement la surveillance de Ryujinx. Le moteur JoyConDSU se construit désormais nativement sous Windows avec Winsock 2.2 et SDL3 ; son pilotage par l’interface sera ajouté à l’étape suivante. Le comportement macOS existant reste inchangé.

Pour préparer le lanceur Windows depuis un clone, utiliser PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

La partie JoyConDSU inclut aussi un binaire Apple Silicon de secours. Une compilation locale reste préférable afin d’utiliser le SDK et la version de SDL3 présents sur la machine. La procédure de construction Windows du moteur est décrite dans `third_party/JoyConDSU/README_WINDOWS.md`.

## Installation depuis un clone Git

### 1. Cloner le dépôt

```bash
git clone https://github.com/Oxnight/BOTW_companion.git
cd BOTW_companion
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

Après avoir créé `.venv` avec les commandes PowerShell ci-dessus, ouvrir le dossier `windows` et double-cliquer sur `Installer BOTW Companion.cmd`. L’installeur ne demande pas de droits administrateur. Il crée un raccourci sur le Bureau et dans le menu Démarrer, puis conserve les réglages dans `%LOCALAPPDATA%\BOTW Companion`.

Le raccourci utilise `wscript.exe` et `pythonw.exe` : aucune fenêtre de terminal n’apparaît. Un runtime autonome placé dans `runtime\pythonw.exe` est utilisé en priorité lorsqu’il est fourni par un futur paquet ; un clone de développement utilise `.venv\Scripts\pythonw.exe`.

À chaque double-clic, le lanceur vérifie d’abord le serveur local. S’il fonctionne déjà, il tente de remettre la fenêtre BOTW Companion au premier plan ; Windows peut refuser cette opération selon ses règles de sécurité, auquel cas le navigateur par défaut ouvre ou réactive la page. Sinon, le serveur démarre puis le navigateur s’ouvre une seule fois. Après avoir vu Ryujinx actif, la surveillance vérifie son état toutes les 15 secondes et demande un arrêt propre après 30 secondes d’absence confirmée.

Le fichier `%LOCALAPPDATA%\BOTW Companion\launcher.json` permet de changer le port, d’indiquer une sauvegarde précise ou d’ajouter le nom d’un exécutable Ryujinx personnalisé. Les erreurs de lancement sont consignées dans `%LOCALAPPDATA%\BOTW Companion\launcher.log`.

## Configurer le gyroscope Joy-Con dans Ryujinx

1. Connecter les deux Joy-Con au Mac et les utiliser comme paire L/R.
2. Dans Ryujinx, activer la source de mouvement Cemuhook/DSU.
3. Utiliser l’hôte `127.0.0.1` et le port `26760`.
4. Sur BOTW Companion, cliquer sur **Activer** dans l’encadré du gyroscope.
5. Poser le grip immobile pendant la calibration.
6. Attendre l’état **Gyroscope Joy-Con prêt** avant de jouer.

Le serveur DSU reste désactivé par défaut. Il s’arrête avec BOTW Companion et reprend proprement après une reconnexion Bluetooth ou une sortie de veille. Le traitement n’ajoute ni filtre ni zone morte aux mouvements.

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

Le même test fonctionnel peut viser les trois navigateurs prévus :

```bash
node tools/browser_smoke.js http://127.0.0.1:8765 chrome
node tools/browser_smoke.js http://127.0.0.1:8765 edge
node tools/browser_smoke.js http://127.0.0.1:8765 firefox
```

Chrome, Microsoft Edge et Firefox doivent être installés sur la machine de test. Le script s’appuie sur leurs canaux officiels Playwright et vérifie notamment l’état initial des filtres, la carte, les fiches, la désélection et le planificateur masqué.

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

* Les fichiers `catalog_fr_compiled.json` et `nomenclature_audit_compiled.json` sont des ressources d’exécution nécessaires au démarrage rapide : ils doivent rester dans le dépôt.
* Les tuiles de `botw_companion/web/map-tiles/` sont nécessaires à la carte haute définition hors ligne.
* Le dossier `third_party/JoyConDSU/Sources/JoyConDSU/` est nécessaire à la compilation locale du serveur DSU.