# BOTW Companion

BOTW Companion est une application locale pour macOS qui analyse une sauvegarde Ryujinx de *The Legend of Zelda: Breath of the Wild* et accompagne une progression complète du jeu.

La version actuelle est **0.39.1**. Le projet vise les Mac Apple Silicon et fonctionne hors ligne après l’installation. Les liens externes éventuellement proposés dans certaines fiches restent naturellement soumis à une connexion Internet.

## Sommaire

* [Fonctions principales](#fonctions-principales).
* [Configuration prise en charge](#configuration-prise-en-charge).
* [Installation depuis un clone Git](#installation-depuis-un-clone-git).

  * [1. Cloner le dépôt](#1-cloner-le-dépôt).
  * [2. Installer les prérequis macOS](#2-installer-les-prérequis-macos).
  * [3. Créer l’environnement Python](#3-créer-lenvironnement-python).
  * [4. Premier lancement dans le terminal](#4-premier-lancement-dans-le-terminal).
* [Installer le lanceur macOS](#installer-le-lanceur-macos).
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
* Serveur gyroscopique Joy-Con compatible Cemuhook/DSU pour Ryujinx.
* Interface Web locale accessible sur `http://127.0.0.1:8765`.
* Lanceur macOS pour démarrer le serveur sans terminal et ouvrir automatiquement le navigateur.

## Configuration prise en charge

* Mac Apple Silicon : M1, M2, M3, M4 ou génération ultérieure.
* macOS 12 ou plus récent.
* Python 3.10 ou plus récent, Python 3.12 recommandé.
* Ryujinx installé dans `/Applications/Ryujinx.app` pour bénéficier de l’arrêt automatique associé au jeu.
* Homebrew, SDL3 et les outils en ligne de commande Xcode pour compiler le serveur JoyConDSU sur le Mac cible.

La partie JoyConDSU inclut aussi un binaire Apple Silicon de secours. Une compilation locale reste préférable afin d’utiliser le SDK et la version de SDL3 présents sur la machine.

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

## Mise à jour du clone

Après un `git pull`, resynchroniser l’environnement :

```bash
uv sync
```

ou, sans `uv` :

```bash
.venv/bin/python -m pip install -e .
```

Le lanceur macOS vérifie la version du serveur déjà ouvert. Lorsqu’une nouvelle version du code est installée, il ferme l’ancienne instance locale avant de lancer la nouvelle.

## Remarques

* Les fichiers `catalog_fr_compiled.json` et `nomenclature_audit_compiled.json` sont des ressources d’exécution nécessaires au démarrage rapide : ils doivent rester dans le dépôt.
* Les tuiles de `botw_companion/web/map-tiles/` sont nécessaires à la carte haute définition hors ligne.
* Le dossier `third_party/JoyConDSU/Sources/JoyConDSU/` est nécessaire à la compilation locale du serveur DSU.