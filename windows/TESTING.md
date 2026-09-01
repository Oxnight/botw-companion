# Validation Windows

Cette matrice relie chaque risque Windows à un contrôle automatique reproductible. Les essais matériels restent séparés, car un runner GitHub ne possède ni Joy-Con ni installation Ryujinx réelle.

| Domaine | Validation automatique |
| --- | --- |
| APPDATA, LOCALAPPDATA, chemins Unicode et installation portable | `tests/test_platforms.py` |
| Verrouillage de fichiers, écritures partielles, slots normal et Expert | `tests/test_synchronization.py` |
| Persistance, sauvegardes, restauration et migrations | `tests/test_persistence.py`, `tests/test_manual_tracking.py`, `tests/test_route_sessions.py` |
| Détection de Ryujinx, instance unique et arrêt propre | `tests/test_platforms.py`, `tests/test_lifecycle.py`, `tests/test_windows_launcher.py` |
| API et cycle de vie JoyConDSU | `tests/test_dsu.py`, `tests/test_dsu_windows_build.py` |
| Protocole DSU, CRC32, calibration, timestamps et télémétrie | `tests/native/*.c`, lancés par `tests/test_dsu_native.py` |
| Interface Chrome, Edge, Firefox et affichage responsive | `tools/browser_test_server.py`, `tools/browser_smoke.js` |
| Paquet autonome sans Python, Git, uv, compilateur ou SDL externes | `tools/test_windows_installation.ps1` : auto-test, chargement DSU et véritable démarrage HTTP |
| Contenu hors ligne du paquet et installateur sans privilèges | `tests/test_windows_package.py`, `tools/build_windows_app.ps1` |
| Cohérence de version, somme SHA-256 et publication GitHub Release | `tools/check_version_consistency.py`, `.github/workflows/windows-release.yml` |

Le workflow `.github/workflows/windows-release.yml` exécute ces contrôles sur Windows Server 2022. Il ne publie une préversion qu'après la réussite de toute la chaîne et uniquement pour le tag exact `v0.40.0-alpha.23`. Une validation matérielle finale sur Windows 10 et Windows 11 demeure nécessaire pour les Joy-Con, Ryujinx et les sanctuaires gyroscopiques.
