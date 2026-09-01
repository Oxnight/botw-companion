# Construction Windows de JoyConDSU

Le moteur conserve exactement le protocole DSU 1001, le port local `127.0.0.1:26760`, les événements SDL horodatés, la calibration robuste, la correction du biais, l'absence de filtre et la télémétrie du moteur macOS.

La couche réseau choisit automatiquement les API natives : sockets POSIX sous macOS et Winsock 2.2 sous Windows. Le CRC32 est inclus dans le moteur et contrôlé avec les mêmes vecteurs octet par octet que l'implémentation antérieure ; aucune DLL zlib n'est nécessaire.

## Construire sur Windows x64

Prérequis : Windows 10 ou 11, Visual Studio 2022 Build Tools avec les outils C++ et CMake.

Depuis la racine du dépôt :

```powershell
.\tools\build_joycon_dsu_windows.ps1
```

CMake télécharge la source officielle SDL 3.4.14 dont l'empreinte SHA-256 est verrouillée, compile le moteur, puis produit :

```text
windows\native-dsu\JoyConDSU.exe
windows\native-dsu\SDL3.dll
windows\native-dsu\manifest.json
```

L'utilisateur final n'aura pas à installer SDL3 : la DLL sera placée à côté de l'exécutable dans le paquet Windows.

Le script copie également ces trois fichiers dans `botw_companion\dsu\windows`. Le gestionnaire DSU les détecte automatiquement, lance `JoyConDSU.exe` sans console avec la DLL placée à côté, puis utilise un événement Windows local nommé pour demander un arrêt coopératif. Le bouton et les états visibles sont les mêmes que sous macOS.