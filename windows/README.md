# Lanceur Windows

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

Le serveur est lancé avec la surveillance sobre de Ryujinx. Après avoir vu Ryujinx actif, il vérifie son état toutes les 15 secondes et s'arrête proprement après 30 secondes d'absence confirmée. L'arrêt du Companion arrête également JoyConDSU.

Les réglages et le journal se trouvent dans `%LOCALAPPDATA%\BOTW Companion`. Le fichier `launcher.json` permet notamment d'ajouter un nom d'exécutable Ryujinx :

```json
{
  "schema_version": 1,
  "project_root": "C:\\chemin\\vers\\BOTW_companion",
  "port": 8765,
  "ryujinx_process_names": [
    "Ryujinx.exe",
    "Ryujinx.Ava.exe",
    "MonRyujinx.exe"
  ]
}
```

L'activation du moteur JoyConDSU natif sous Windows appartient à l'étape suivante de la feuille de route.