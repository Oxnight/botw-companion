## Changements

- Le serveur local utilise désormais un jeton différent à chaque lancement pour protéger les actions sensibles.
- Les requêtes provenant d’un autre site, d’un hôte inattendu ou d’un contexte inter-origine sont refusées.
- L’arrêt du serveur, le contrôle de JoyConDSU, le suivi manuel, les imports et les préférences nécessitent une session valide.
- Les réponses incluent une politique de sécurité du contenu et des protections contre l’intégration en iframe et la détection incorrecte des types de fichiers.
- Les lanceurs Windows et macOS transmettent automatiquement la session et conservent l’arrêt propre de l’application.

Cette version ne modifie ni le calcul de progression, ni le suivi DSU, ni l’interface.

## Téléchargements

- Windows 10/11 x64 : télécharger le fichier `Setup.exe` et lancer l’installation.
- macOS 14 ou plus récent, Apple Silicon : ouvrir le DMG puis glisser BOTW Companion dans Applications.

Les applications sont autonomes et fonctionnent hors ligne. Elles ne sont pas signées avec un certificat commercial ; SmartScreen ou Gatekeeper peut demander une confirmation au premier lancement.
