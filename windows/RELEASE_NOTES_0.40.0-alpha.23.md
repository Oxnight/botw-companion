# BOTW Companion 0.40.0 alpha 23 — Windows autonome

Cette préversion conserve à l'identique les fonctions, l'interface, les données hors ligne et le moteur gyroscopique de l'alpha 22. Le changement porte uniquement sur l'installation et la distribution Windows.

## Installation

1. Télécharger `BOTW_Companion_0.40.0-alpha.23_Setup.exe` et `SHA256SUMS.txt` ci-dessous.
2. Vérifier l'empreinte SHA-256 de l'installateur.
3. Lancer l'installateur, puis ouvrir **BOTW Companion** depuis le Bureau ou le menu Démarrer.

Le paquet inclut le runtime Python, toutes les données et cartes hors ligne, `JoyConDSU.exe`, `SDL3.dll`, le manifeste DSU, les licences et les icônes. Il ne nécessite ni Python, ni Git, ni clone du dépôt, ni Visual Studio, ni CMake, ni SDL3 séparé.

## Compatibilité et sécurité

- Windows 10 version 1809 ou ultérieure et Windows 11, processeur x64.
- Installation par utilisateur, sans privilèges administrateur, dans `%LOCALAPPDATA%\Programs\BOTW Companion`.
- Données personnelles conservées séparément dans `%LOCALAPPDATA%\BOTW Companion`, y compris après une désinstallation.
- Cette alpha n'est pas signée : SmartScreen peut demander une confirmation. Vérifier impérativement la provenance GitHub et l'empreinte fournie avant de l'exécuter.

La publication est créée seulement après compilation native, tests Python, parcours Chrome/Edge/Firefox, installation sur un runner Windows propre, chargement de JoyConDSU, démarrage réel du serveur et désinstallation contrôlée.
