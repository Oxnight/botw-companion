# Application Windows

## Application autonome

La distribution recommandée est une application PyInstaller one-folder entourée d'un installateur Inno Setup par utilisateur. Elle embarque Python, toutes les données hors ligne, le moteur `JoyConDSU.exe` et `SDL3.dll`.

Pour construire l'ensemble sous Windows x64 :

```powershell
.\tools\build_windows_app.ps1
```

Prérequis de construction uniquement : Python 3.12, Visual Studio 2022 Build Tools avec C++ et CMake, ainsi qu'Inno Setup 6. Les utilisateurs de l'application produite n'ont besoin d'aucun de ces outils.

Livrables :

```text
dist\BOTW Companion\BOTW Companion.exe
dist\installer\BOTW_Companion_0.40.0-alpha.18_Setup.exe
```

L'installateur cible `%LOCALAPPDATA%\Programs\BOTW Companion`, crée le menu Démarrer, propose le raccourci Bureau et laisse toutes les données personnelles dans `%LOCALAPPDATA%\BOTW Companion`.

Le workflow Windows teste aussi une installation silencieuse dans un dossier contenant des espaces, retire Python, Git, uv, les compilateurs et SDL du `PATH`, exécute l’auto-test du paquet, désinstalle l’application et vérifie que les données personnelles sont conservées. La matrice complète se trouve dans `windows/TESTING.md`.

## Lanceur d'un clone

Le lanceur installe deux raccourcis, sur le Bureau et dans le menu Démarrer. Il ne demande pas de droits administrateur et ne copie pas le projet : le clone doit donc rester à son emplacement actuel.

## Installation

Depuis la racine du clone, préparer Python une seule fois :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Double-cliquer ensuite sur `Installer BOTW Companion.cmd` dans ce dossier.

## Fonctionnement

Le raccourci utilise `wscript.exe` et `pythonw.exe`, donc aucun terminal n'apparaît. Le lanceur recherche d'abord un éventuel runtime embarqué, puis `.venv`. Il vérifie l'instance locale sur le port 8765, remet sa fenêtre au premier plan lorsque Windows l'autorise ou ouvre le navigateur, et ne démarre jamais un second serveur identique.

Le serveur est lancé avec la surveillance sobre de l’émulateur. Après avoir vu Ryujinx ou Cemu actif, il vérifie son état toutes les 15 secondes et s’arrête proprement après 30 secondes d’absence confirmée. L'arrêt du Companion arrête également JoyConDSU.

Les réglages et le journal se trouvent dans `%LOCALAPPDATA%\BOTW Companion`. Le fichier `launcher.json` permet notamment d’ajouter des noms d’exécutables Ryujinx ou Cemu :

```json
{
  "schema_version": 1,
  "project_root": "C:\\chemin\\vers\\BOTW_companion",
  "port": 8765,
  "ryujinx_process_names": [
    "Ryujinx.exe",
    "Ryujinx.Ava.exe",
    "MonRyujinx.exe"
  ],
  "cemu_process_names": [
    "Cemu.exe"
  ]
}
```

## Gyroscope universel

Construire une fois le moteur natif depuis la racine du clone :

```powershell
.\tools\build_joycon_dsu_windows.ps1
```

Le script installe `JoyConDSU.exe` et `SDL3.dll` dans les ressources locales du Companion. Le site détecte les manettes SDL3 en USB ou Bluetooth, permet de choisir une source possédant gyro + accéléromètre, puis le bouton **Activer** lance le même moteur sans console. La paire Joy-Con reste combinée en mode grip. Le moteur conserve calibration, reconnexion et arrêt propre ; le port Cemuhook/DSU reste `127.0.0.1:26760` pour Ryujinx comme pour Cemu.