# Distribution Windows

Les joueurs téléchargent uniquement `BOTW_Companion_0.40.0-alpha.24_Setup.exe` depuis [GitHub Releases](https://github.com/Oxnight/botw-companion/releases). L’installateur x64 embarque le runtime Python, les ressources hors ligne, JoyConDSU et SDL3, puis crée les raccourcis Bureau et menu Démarrer.

## Construction

La construction officielle s’exécute sur le runner `windows-2022` du workflow `release.yml`. Pour la reproduire sous Windows x64 :

```powershell
.\tools\build_windows_app.ps1
.\tools\test_windows_installation.ps1
```

Le résultat se trouve dans :

```text
dist\installer\BOTW_Companion_0.40.0-alpha.24_Setup.exe
```

L’installateur est installé par utilisateur dans `%LOCALAPPDATA%\Programs\BOTW Companion`. Les données personnelles restent séparées dans `%LOCALAPPDATA%\BOTW Companion`.

Les scripts `Installer BOTW Companion.cmd`, `Installer BOTW Companion.ps1` et `BOTW Companion.vbs` restent disponibles uniquement pour le développement depuis un clone et un environnement `.venv`.
